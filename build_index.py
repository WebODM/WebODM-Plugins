import os
import sys
import json
import hashlib
import shutil
import zipfile

root = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))
dist_dir = os.path.join(root, "dist")

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def read_manifest(path):
    with zipfile.ZipFile(path) as z:
        manifests = [n for n in z.namelist() if n.count("/") == 1 and n.endswith("/manifest.json")]
        if len(manifests) != 1:
            raise Exception("expected one <root>/manifest.json, found %s" % len(manifests))
        return json.loads(z.read(manifests[0]))

plugins = []
for f in sorted(os.listdir(dist_dir)):
    if not f.endswith(".zip"):
        continue
    path = os.path.join(dist_dir, f)
    try:
        meta = read_manifest(path)
    except Exception as e:
        print("ERROR: %s: %s" % (f, e))
        sys.exit(1)
    meta["url"] = "/" + f
    meta["sha256"] = sha256(path)
    plugins.append(meta)
    print("A\t" + f)

with open(os.path.join(dist_dir, "index.json"), "w") as f:
    json.dump({"plugins": plugins}, f, indent=4)

print("Wrote %s plugins to %s" % (len(plugins), os.path.join(dist_dir, "index.json")))

shutil.copy(os.path.join(root, "index.html"), os.path.join(dist_dir, "index.html"))
print("Copied index.html")
