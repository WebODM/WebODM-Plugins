import os
import sys
import shutil
import json
import subprocess
import zipfile
from concurrent.futures import ThreadPoolExecutor

root = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))
plugins_dir = os.path.join(root, "plugins")
external_dir = os.path.join(root, "external")
build_dir = os.path.join(root, "build")
dist_dir = os.path.join(root, "dist")
image = "webodm/webodm_webapp"

error_markers = [
    "Traceback (most recent call last)",
    "ERROR in ",
    "npm ERR!",
    "npm error",
    "Module build failed",
    "is not installed",
    "Cannot generate webpack.config.js",
]

def fail(msg):
    print("ERROR: " + msg)
    sys.exit(1)

def ignore(dirpath, names):
    skip = {"node_modules", "__pycache__"}
    if os.path.basename(dirpath) == "public":
        skip.add("build")
    return [n for n in names if n in skip or n.endswith(".pyc")]

print("Cleaning up...")

for d in [dist_dir, build_dir]:
    if os.path.isdir(d):
        shutil.rmtree(d)
        print("R\t" + d)

print("Collecting...")

sources = {}
for src_dir in [plugins_dir, external_dir]:
    if not os.path.isdir(src_dir):
        continue
    for p in sorted(os.listdir(src_dir)):
        if not os.path.isfile(os.path.join(src_dir, p, "manifest.json")):
            continue
        if p.endswith("-prebuilt"):
            fail("%s: plugin names cannot end with -prebuilt" % p)
        if p in sources:
            fail("%s: defined in both %s and %s" % (p, sources[p], src_dir))
        sources[p] = src_dir

os.makedirs(build_dir)
for p, src_dir in sources.items():
    shutil.copytree(os.path.join(src_dir, p), os.path.join(build_dir, p), ignore=ignore)
    print("C\t" + os.path.join(src_dir, p))

plugins = sorted(sources)

print("Rebuilding...")

uid_gid = "%s:%s" % (os.getuid(), os.getgid())
cmd = [
    "docker", "run", "--rm",
    "-v", build_dir + ":/webodm/coreplugins",
    "--entrypoint", "/bin/bash",
    image,
    "-c", "python manage.py rebuildplugins; rc=$?; chown -R %s /webodm/coreplugins; exit $rc" % uid_gid,
]

proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
errors = []
for line in proc.stdout:
    sys.stdout.write(line)
    if any(m in line for m in error_markers):
        errors.append(line.rstrip())
proc.wait()

if proc.returncode != 0:
    fail("rebuildplugins exited with code %s" % proc.returncode)

for p in plugins:
    public = os.path.join(build_dir, p, "public")
    package_json = os.path.join(public, "package.json")
    if os.path.isfile(package_json):
        with open(package_json) as f:
            if json.load(f).get("dependencies") and not os.path.isdir(os.path.join(public, "node_modules")):
                errors.append("%s: public/node_modules missing" % p)
    if os.path.isfile(os.path.join(public, "webpack.config.js")) and not os.path.isdir(os.path.join(public, "build")):
        errors.append("%s: public/build missing" % p)

if errors:
    fail("rebuild failed:\n" + "\n".join(errors))

print("Packaging...")

os.makedirs(dist_dir)

def zip_info(name, mode):
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = mode << 16
    return info

def package(p, prebuilt):
    src = os.path.join(build_dir, p)
    out = os.path.join(dist_dir, p + ("-prebuilt.zip" if prebuilt else ".zip"))
    with zipfile.ZipFile(out, "w") as z:
        for dirpath, dirnames, filenames in os.walk(src):
            rel = os.path.relpath(dirpath, build_dir)
            skip = {"node_modules", "__pycache__"}
            if not prebuilt and rel == os.path.join(p, "public"):
                skip.add("build")
            dirnames[:] = sorted(d for d in dirnames if d not in skip)
            z.writestr(zip_info(rel + "/", 0o40755), b"")
            for f in sorted(filenames):
                if f.endswith(".pyc"):
                    continue
                path = os.path.join(dirpath, f)
                info = zip_info(os.path.join(rel, f), 0o100755 if os.access(path, os.X_OK) else 0o100644)
                info.compress_type = zipfile.ZIP_DEFLATED
                with open(path, "rb") as fin, z.open(info, "w") as fout:
                    shutil.copyfileobj(fin, fout, 1024 * 1024)
    return out

with ThreadPoolExecutor(max_workers=os.cpu_count()) as ex:
    jobs = [ex.submit(package, p, prebuilt) for p in plugins for prebuilt in (False, True)]
    for j in jobs:
        print("W\t" + j.result())

print("Done!")
