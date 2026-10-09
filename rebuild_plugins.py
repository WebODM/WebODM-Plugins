import os
import sys
import shutil
import glob
import json
import subprocess
import zipfile
from concurrent.futures import ThreadPoolExecutor

root = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))
plugins_dir = os.path.join(root, "plugins")
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

print("Cleaning up...")

if os.path.isdir(dist_dir):
    shutil.rmtree(dist_dir)
    print("R\t" + dist_dir)

for folder in ["node_modules", "build"]:
    for d in glob.glob(os.path.join(plugins_dir, "**", "public", folder)):
        shutil.rmtree(d)
        print("R\t" + d)

print("Rebuilding...")

uid_gid = "%s:%s" % (os.getuid(), os.getgid())
cmd = [
    "docker", "run", "--rm",
    "-v", plugins_dir + ":/webodm/coreplugins",
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

plugins = sorted(p for p in os.listdir(plugins_dir) if os.path.isfile(os.path.join(plugins_dir, p, "manifest.json")))

for p in plugins:
    public = os.path.join(plugins_dir, p, "public")
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

def package(p):
    src = os.path.join(plugins_dir, p)
    out = os.path.join(dist_dir, p + ".zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for dirpath, dirnames, filenames in os.walk(src):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            rel = os.path.relpath(dirpath, plugins_dir)
            z.write(dirpath, rel)
            for f in filenames:
                if f.endswith(".pyc"):
                    continue
                z.write(os.path.join(dirpath, f), os.path.join(rel, f))
    return out

with ThreadPoolExecutor(max_workers=os.cpu_count()) as ex:
    for out in ex.map(package, plugins):
        print("W\t" + out)

print("Done!")
