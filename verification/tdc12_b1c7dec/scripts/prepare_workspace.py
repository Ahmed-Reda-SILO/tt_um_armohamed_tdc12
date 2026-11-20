#!/usr/bin/env python3
"""Prepare a reproducible audit workspace from its source checkout and results ZIP."""
import argparse, hashlib, json, shutil, zipfile
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--results-zip',type=Path,help='TDC12_Official_GDS_Verification_b1c7dec.zip')
p.add_argument('--source-root',type=Path,help='Repository checkout; defaults to three parents above the audit scripts')
a=p.parse_args()
root=Path(__file__).resolve().parents[1]
source=a.source_root.resolve() if a.source_root else root.parents[1]
if a.results_zip:
    with zipfile.ZipFile(a.results_zip) as z:
        for name in z.namelist():
            if not (root/name).resolve().is_relative_to(root):
                raise SystemExit('Unsafe ZIP member: '+name)
        z.extractall(root)
for directory,files in [('src',['project.v','pulse_width_tdc.v']),('test',['tdc_tb.sv'])]:
    (root/directory).mkdir(exist_ok=True)
    for name in files:
        src=source/directory/name
        if not src.is_file():raise SystemExit('Source file missing: '+str(src))
        shutil.copy2(src,root/directory/name)
expected='2c66650721f9d8c3d54b18e39038064a20b95f048d1b69d987ed50766105bd40'
gds=root/'tt_submission/tt_um_armohamed_tdc12.gds'
if not gds.is_file():raise SystemExit('Provide --results-zip with the generated evidence package.')
if hashlib.sha256(gds.read_bytes()).hexdigest()!=expected:raise SystemExit('GDS hash mismatch')
(root/'build').mkdir(exist_ok=True)
print('Prepared source, generated views, reports and testbench. Official GDS SHA256 matches.')
