import glob
import os
from multiprocessing.pool import ThreadPool
from pathlib import Path

import numpy as np
from PIL import Image
from tqdm import tqdm


def scan(files, max_wh=2000, remove=False, multi_thread=True):  # filelist, maximum image wh, remove corrupted/duplicate
    img_formats = ['.bmp', '.jpg', '.jpeg', '.png', '.tif', '.tiff', '.dng']  # valid image formats from YOLOv5

    def scan_one_file(f):
        try:
            # Rename (remove wildcard characters)
            src = f  # original name
            f = f.replace('%20', '_').replace('%', '_').replace('*', '_').replace('~', '_')
            f = f[:f.index('?')] if '?' in f else f  # new name
            if src != f:
                os.rename(src, f)  # rename

            # Add suffix (if missing)
            if Path(f).suffix == '':
                src = f  # original name
                f += '.' + Image.open(f).format.lower()  # append PIL format
                os.rename(src, f)  # rename

            # Check suffix
            if Path(f).suffix not in img_formats:
                print('Invalid suffix %s' % f)
                os.remove(f) if remove else None
                return None

            # Check image
            Image.open(f).verify()  # PIL verify
            img = Image.open(f)  # open after verify
            assert min(img.size) > 9, 'image size <10 pixels'

            # Downsize
            r = max_wh / max(img.size)  # ratio (width, height = img.size)
            if r < 1:  # resize
                print('Resizing %s' % f)
                img = img.resize((round(x * r) for x in img.size), Image.ANTIALIAS)  # resize(width, height)

            # Resave
            img.save(f)

            # Hash for duplicate detection
            img = np.array(img)  # to numpy
            img = np.repeat(img[:, :, None], 3, axis=2) if len(img.shape) == 2 else img  # greyscale to rgb
            img = img[:, :, :3] if img.shape[2] == 4 else img  # rgba to rgb (for pngs)
            hash = list(img.reshape(-1, 3).mean(0)) + list(img.reshape(-1, 3).std(0))  # unique to each image
            return [f, hash]

        # Remove corrupted
        except Exception as e:
            print('WARNING: %s: %s' % (f, e))
            os.remove(f) if remove else None
            return None

    # Scan all images
    a = []  # list of good filenames, hashes
    nf = len(files)
    if multi_thread:
        results = ThreadPool(20).imap_unordered(scan_one_file, files)  # 20 threads
        for r in tqdm(results, desc='Scanning images', total=nf):
            a.append(r) if r else None
    else:  # single-thread
        for f in tqdm(files, desc='Scanning images', total=nf):
            r = scan_one_file(f)
            a.append(r) if r else None

    # Remove duplicates
    f, x = list(zip(*a))  # files, hashes
    x = np.array(x)
    thres = 0.5  # threshold for declaring images identical (tunable parameter)
    removed = []  # removed items
    for i in range(len(f)):
        if i not in removed:  # if not removed
            duplicates = list(
                (((x[i] - x) ** 2).sum(1) < thres).nonzero()[0])  # list of duplicate images (including self)
            duplicates.remove(i)  # remove self from duplicate list
            if any(duplicates):
                for j in duplicates:
                    removed.append(j)
                    if remove and os.path.exists(f[j]):
                        os.remove(f[j])
                print('Duplicate images %s %s' % (f[i], [f[j] for j in duplicates]))
    print('Found %g duplicates.' % len(removed))


if __name__ == '__main__':
    files = sorted(glob.iglob('../images/**/*.*', recursive=True))
    assert len(files), 'No files found'
    scan(files, max_wh=1920, remove=True, multi_thread=True)
