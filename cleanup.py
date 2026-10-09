import os
import shutil
import glob

root = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))
plugins_dir = os.path.join(root, "plugins")

for folder in ["node_modules", "build"]:
    for d in glob.glob(os.path.join(plugins_dir, "**", "public", folder)):
        shutil.rmtree(d)
        print("R\t" + d)