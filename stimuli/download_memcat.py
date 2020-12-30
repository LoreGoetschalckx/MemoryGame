import requests, zipfile, io
import os
from tqdm import tqdm
import shutil

dest_dir = "./memcat"
target_dir = os.path.join(dest_dir, "targets")
filler_dir = os.path.join(dest_dir, "fillers")
preview_dir = os.path.join(dest_dir, "preview") # we'll be leaving a few images out to use for mturk preview
os.makedirs(dest_dir, exist_ok=True)
os.makedirs(target_dir)
os.makedirs(filler_dir)
os.makedirs(preview_dir)

target_categories = ["animal", "food", "landscape", "sports", "vehicle"]

# Download
if not os.path.isfile(os.path.join(dest_dir, "memcat.zip")):
    print("downloading...")
    r = requests.get(
        "https://files.de-1.osf.io/v1/resources/kvghu/providers/osfstorage/5cfe61c646ad4d0016d775cf/?zip=%20GET")
    z = zipfile.ZipFile(io.BytesIO(r.content))
    z.extractall(dest_dir)

# Unzip further
print("unzipping...")
with zipfile.ZipFile(os.path.join(dest_dir, "memcat.zip")) as zf:
    for member in tqdm(zf.infolist(), desc='Extracting '):
        try:
            zf.extract(member, dest_dir)
        except zipfile.error as e:
            pass

# Reorganize target images
print("reorganizing...")
for category in target_categories:
    source_dir = os.path.join(dest_dir, "memcat", category)
    file_names = os.listdir(source_dir)
    for root, dirs, files in os.walk(source_dir):
        for file_name in files:
            shutil.move(os.path.join(root, file_name), target_dir)

# Reorganize filler images
source_dir = os.path.join(dest_dir, "memcat", "fillers")
file_names = os.listdir(source_dir)
count = 0
for file_name in file_names:
    if count < 200:
        shutil.move(os.path.join(source_dir, file_name), preview_dir)
    else:
        shutil.move(os.path.join(source_dir, file_name), filler_dir)
    count += 1

# Clean up empty folders
print("cleaning up ...")
shutil.rmtree(os.path.join(dest_dir, "memcat"))