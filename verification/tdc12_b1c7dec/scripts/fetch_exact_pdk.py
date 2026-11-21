#!/usr/bin/env python3
"""Fetch the exact public Open PDKs release recorded in the official GDS."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request
import zstandard

REV = '8afc8346a57fe1ab7934ba5a6056ea8b43078e71'
ASSETS = {
    'common.tar.zst': 'ef8f48d8bfda17087fbae77a458fdee0fe5a0f0af714d96aff730467858724e2',
    'sky130_fd_pr.tar.zst': '2f6524e790e4cbbcc09918c505eeb7b7fc0f7f87bf8b12c493b4367fca45dbf5',
    'sky130_fd_sc_hd.tar.zst': 'c23904a5adb6f4a416591121122dbca83d826b748aca2267526691743972523a',
    'sky130_fd_io.tar.zst': '7e0e617ddce036b088711c8795d5e93696a1162ae0b4655eef0a9af62de7004c',
}
ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / '.tooling' / ('pdk_' + REV[:8])
DEST.mkdir(parents=True, exist_ok=True)

def download(item):
    name, expected = item
    target = DEST / name
    if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
        url = 'https://github.com/chipfoundry/volare/releases/download/sky130-' + REV + '/' + name
        with urllib.request.urlopen(url, timeout=120) as src, target.open('wb') as dst:
            while data := src.read(1024 * 1024):
                dst.write(data)
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != expected:
        raise RuntimeError('Public release checksum mismatch: ' + name)
    print('Verified download: ' + name, flush=True)
    return {'name': name, 'sha256': actual, 'bytes': target.stat().st_size}

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    records = list(pool.map(download, ASSETS.items()))
for record in records:
    with (DEST / record['name']).open('rb') as stream:
        with zstandard.ZstdDecompressor().stream_reader(stream) as decoded:
            with tarfile.open(fileobj=decoded, mode='r|') as archive:
                archive.extractall(DEST, filter='data')
    print('Extracted: ' + record['name'], flush=True)
(DEST / 'PDK_REVISION.txt').write_text('sky130-' + REV + '\n')
(DEST / 'release_checksums.json').write_text(json.dumps(records, indent=2) + '\n')
print('Exact PDK ready: ' + str(DEST), flush=True)
