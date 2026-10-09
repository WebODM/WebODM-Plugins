import os
import sys
import json
import hashlib
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

root = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))
dist_dir = os.path.join(root, "dist")

def fetch(entry):
    url = entry.get("url", "")
    expected = entry.get("sha256", "").lower()
    if not url:
        return "S\t(empty url)"

    name = os.path.basename(urllib.parse.urlparse(url).path)
    if not name.endswith(".zip"):
        return "E\t%s: not a .zip url" % url

    out = os.path.join(dist_dir, name)
    tmp = out + ".part"
    h = hashlib.sha256()
    try:
        with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
            for chunk in iter(lambda: r.read(1024 * 1024), b""):
                h.update(chunk)
                f.write(chunk)
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        return "E\t%s: %s" % (url, e)

    actual = h.hexdigest()
    if actual != expected:
        os.remove(tmp)
        return "E\t%s: sha256 mismatch (expected %s, got %s)" % (url, expected or "<empty>", actual)

    if os.path.exists(out):
        print("WARNING: overwriting " + out)
    os.replace(tmp, out)
    return "W\t" + out

with open(os.path.join(root, "directory.json")) as f:
    entries = json.load(f)["plugins"]

os.makedirs(dist_dir, exist_ok=True)

failed = 0
with ThreadPoolExecutor(max_workers=8) as ex:
    for res in ex.map(fetch, entries):
        print(res)
        if res.startswith("E"):
            failed += 1

print("Done! %s fetched, %s failed" % (len(entries) - failed, failed))
