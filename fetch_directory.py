import os
import sys
import re
import shutil
import json
import zipfile
import tempfile
import hashlib
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

root = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))
plugins_dir = os.path.join(root, "plugins")
external_dir = os.path.join(root, "external")

def zip_root(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    roots = set(n.split("/", 1)[0] for n in names)
    if len(roots) != 1 or not all("/" in n for n in names):
        raise Exception("archive must contain a single root folder, found: %s" % ", ".join(sorted(roots)))
    name = roots.pop()
    if not re.match(r"^[A-Za-z0-9_-][A-Za-z0-9._-]*$", name):
        raise Exception("invalid root folder name: %s" % name)
    if name + "/manifest.json" not in names:
        raise Exception("missing %s/manifest.json" % name)
    return name

def fetch(entry):
    url = entry.get("url", "")
    expected = entry.get("sha256", "").lower()
    if not url:
        return "S\t(empty url)", None

    if not urllib.parse.urlparse(url).path.endswith(".zip"):
        return "E\t%s: not a .zip url" % url, None

    fd, tmp = tempfile.mkstemp(suffix=".part", dir=external_dir)
    os.close(fd)
    h = hashlib.sha256()
    try:
        with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
            for chunk in iter(lambda: r.read(1024 * 1024), b""):
                h.update(chunk)
                f.write(chunk)
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        return "E\t%s: %s" % (url, e), None

    actual = h.hexdigest()
    if actual != expected:
        os.remove(tmp)
        return "E\t%s: sha256 mismatch (expected %s, got %s)" % (url, expected or "<empty>", actual), None

    try:
        name = zip_root(tmp)
    except Exception as e:
        os.remove(tmp)
        return "E\t%s: %s" % (url, e), None

    return tmp, name

with open(os.path.join(root, "directory.json")) as f:
    entries = json.load(f)["plugins"]

if os.path.isdir(external_dir):
    shutil.rmtree(external_dir)
os.makedirs(external_dir)

failed = 0
with ThreadPoolExecutor(max_workers=8) as ex:
    for entry, (tmp, name) in zip(entries, ex.map(fetch, entries)):
        if name is None:
            print(tmp)
            if tmp.startswith("E"):
                failed += 1
            continue
        out = os.path.join(external_dir, name)
        if os.path.exists(out) or os.path.exists(os.path.join(plugins_dir, name)):
            os.remove(tmp)
            print("E\t%s: %s conflicts with an existing plugin" % (entry["url"], name))
            failed += 1
            continue
        with zipfile.ZipFile(tmp) as z:
            z.extractall(external_dir)
        os.remove(tmp)
        print("X\t" + out)

print("Done! %s fetched, %s failed" % (len(entries) - failed, failed))
