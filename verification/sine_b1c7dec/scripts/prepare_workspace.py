#!/usr/bin/env python3
"""Unpack generated evidence and obtain unchanged RTL from the source checkout."""
import argparse,hashlib,json,shutil,zipfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--results-zip',type=Path,required=True);p.add_argument('--source-root',type=Path);a=p.parse_args()
root=Path(__file__).resolve().parents[1];source=a.source_root.resolve() if a.source_root else root.parents[1]
with zipfile.ZipFile(a.results_zip) as z:
 for name in z.namelist():
  if not (root/name).resolve().is_relative_to(root):raise SystemExit('Unsafe archive member')
 z.extractall(root)
audit=root/'macro_evidence';expected={r['path']:r['sha256'] for r in json.loads((audit/'source_provenance.json').read_text())}
for path in ['src/project.v','src/pulse_width_tdc.v','test/tdc_tb.sv']:
 src=source/path
 if hashlib.sha256(src.read_bytes()).hexdigest()!=expected[path]:raise SystemExit('Audited source mismatch: '+path)
 dst=audit/path;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
gds=audit/'tt_submission/tt_um_armohamed_tdc12.gds'
if hashlib.sha256(gds.read_bytes()).hexdigest()!='2c66650721f9d8c3d54b18e39038064a20b95f048d1b69d987ed50766105bd40':raise SystemExit('GDS mismatch')
print('Prepared exact source and generated macro evidence. Run the README commands to recreate local timing models.')
