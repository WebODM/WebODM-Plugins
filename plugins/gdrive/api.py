import os
import re

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.utils.translation import gettext as _
from guardian.shortcuts import get_objects_for_user
from rest_framework import exceptions
from rest_framework.response import Response

from app.api.common import check_project_perms
from app.models import Task
from app.plugins.views import TaskView
from app.plugins.worker import run_function_async
from nodeodm.models import ProcessingNode

ACCEPTED_FILES = "image/*,text/plain,.las,.laz,video/*,.srt,.dng,.nef,.gpx"

def is_accepted_file(name, mime_type):
    name = (name or "").lower()
    mime_type = (mime_type or "").lower()
    for rule in ACCEPTED_FILES.split(","):
        if rule.startswith("."):
            if name.endswith(rule):
                return True
        elif rule.endswith("/*"):
            if mime_type.startswith(rule[:-1]):
                return True
        elif mime_type == rule:
            return True
    return False

def get_max_images(user):
    nodes = get_objects_for_user(user, 'view_processingnode', ProcessingNode, accept_global_perms=False)
    max_images = None
    for node in nodes:
        if node.max_images is None:
            return None
        max_images = max(max_images or 0, node.max_images)
    return max_images


class ImportFiles(TaskView):
    def post(self, request, project_pk=None, pk=None):
        try:
            task = Task.objects.select_related('project').get(pk=pk, project=project_pk)
        except (ObjectDoesNotExist, ValidationError):
            raise exceptions.NotFound()

        check_project_perms(request, task.project, ('change_project', ))

        if not task.partial:
            raise exceptions.ValidationError(detail=_("This task is not accepting new files"))

        token = request.data.get('token')
        files = request.data.get('files')

        if not isinstance(token, str) or token == "":
            raise exceptions.ValidationError(detail=_("Missing Google Drive access token"))
        if not isinstance(files, list) or len(files) == 0:
            raise exceptions.ValidationError(detail=_("No files selected"))

        clean_files = []
        names = set()
        for f in files:
            if not isinstance(f, dict):
                raise exceptions.ValidationError(detail=_("Invalid file list"))

            file_id = f.get('id')
            name = f.get('name')
            mime_type = f.get('mimeType')
            size = f.get('size', 0)

            if not isinstance(file_id, str) or re.match(r'^[A-Za-z0-9_-]+$', file_id) is None:
                raise exceptions.ValidationError(detail=_("Invalid file list"))
            if not isinstance(name, str) or name != os.path.basename(name) or name in ("", ".", ".."):
                raise exceptions.ValidationError(detail=_("Invalid file list"))
            if name in names:
                raise exceptions.ValidationError(detail=_("Duplicate file name: %(name)s") % {'name': name})
            if not is_accepted_file(name, mime_type):
                raise exceptions.ValidationError(detail=_("%(name)s is not a valid file") % {'name': name})
            if not isinstance(size, int) or size < 0:
                size = 0

            names.add(name)
            clean_files.append({'id': file_id, 'name': name, 'size': size})

        max_images = get_max_images(request.user)
        if max_images is not None and len(clean_files) > max_images:
            raise exceptions.ValidationError(detail=_("You selected %(count)s files, but you can only process at most %(max)s images.") % {'count': len(clean_files), 'max': max_images})

        celery_task_id = run_function_async(download_drive_files, task.id, token, clean_files,
                                            with_progress=True, with_cancel=True).task_id

        return Response({'celery_task_id': celery_task_id})


def download_drive_files(task_id, token, files, progress_callback=None, should_cancel=None):
    import os
    import time
    import threading
    import requests
    from concurrent.futures import ThreadPoolExecutor, wait, FIRST_EXCEPTION
    from app.models import Task
    from app import pending_actions
    from worker import tasks as worker_tasks

    class DownloadError(Exception):
        pass

    task = Task.objects.get(pk=task_id)
    total_bytes = sum(f['size'] for f in files) or 1
    state = {'bytes': 0}
    lock = threading.Lock()
    canceled = threading.Event()

    def add_bytes(n):
        with lock:
            state['bytes'] += n

    def fetch(f):
        dst = task.get_image_path(f['name'])
        tmp = os.path.join(os.path.dirname(dst), ".{}.part".format(f['name']))
        url = "https://www.googleapis.com/drive/v3/files/{}?alt=media&supportsAllDrives=true".format(f['id'])
        attempts = 5

        for attempt in range(attempts):
            if canceled.is_set():
                return
            written = 0
            try:
                with requests.get(url, headers={'Authorization': 'Bearer {}'.format(token)}, stream=True, timeout=60) as r:
                    if r.status_code == 401:
                        raise DownloadError("Google Drive access expired, please select the files again")
                    if r.status_code == 404 or (r.status_code == 403 and "ateLimit" not in r.text):
                        raise DownloadError("Cannot access {} on Google Drive".format(f['name']))
                    r.raise_for_status()

                    with open(tmp, 'wb') as fd:
                        for chunk in r.iter_content(chunk_size=1024 * 1024):
                            if canceled.is_set():
                                return
                            fd.write(chunk)
                            written += len(chunk)
                            add_bytes(len(chunk))

                os.replace(tmp, dst)
                return
            except DownloadError:
                raise
            except Exception as e:
                add_bytes(-written)
                if attempt + 1 == attempts:
                    raise DownloadError("Cannot download {}: {}".format(f['name'], str(e)))
                time.sleep(2 ** attempt)
            finally:
                if os.path.isfile(tmp):
                    os.unlink(tmp)

    os.makedirs(task.task_path(), exist_ok=True)

    try:
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(fetch, f) for f in files]
            pending = futures
            while len(pending) > 0:
                done, pending = wait(pending, timeout=2, return_when=FIRST_EXCEPTION)
                for fut in done:
                    if fut.exception() is not None:
                        canceled.set()
                        raise fut.exception()

                if should_cancel is not None and should_cancel():
                    canceled.set()
                    return {'error': "Canceled"}

                if progress_callback is not None:
                    with lock:
                        progress_callback("Downloading", min(100.0, state['bytes'] / total_bytes * 100.0))
    except DownloadError as e:
        return {'error': str(e)}

    task.refresh_from_db()
    if not task.partial or task.pending_action == pending_actions.REMOVE:
        return {'error': "Canceled"}

    task.partial = False
    task.images_count = len(task.scan_images())
    if task.images_count < 1:
        return {'error': "No files were downloaded"}

    task.update_size()
    task.save()
    worker_tasks.process_task.delay(task.id)

    return {}
