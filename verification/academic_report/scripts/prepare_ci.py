#!/usr/bin/env python3
"""Recover hash-verified original GDS artifacts into the existing audit tree."""
import hashlib,json,os,shutil,zipfile
from pathlib import Path
import requests
REPO='Ahmed-Reda-SILO/tt_um_armohamed_tdc12'
ROOT=Path(__file__).resolve().parents[2]/'tdc12_b1c7dec'
ROOT.mkdir(exist_ok=True)
ARTIFACTS=[
 ('tt_submission',14521327699,'d5417b65b4827be9a2c2a8a763c221e7418fede70537cc3a782a654100b07ce7'),
 ('GDS_logs',14521327696,'952a299af36d01275f855d8b7e26f49d5091e078681d8da6b15929eda6e263be')]
records=[]
for name,aid,want in ARTIFACTS:
 response=requests.get(f'https://api.github.com/repos/{REPO}/actions/artifacts/{aid}/zip',
  headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'},timeout=180)
 response.raise_for_status()
 data=response.content;digest=hashlib.sha256(data).hexdigest()
 assert digest==want,(name,digest)
 destination=ROOT if name=='tt_submission' else ROOT/'official_artifacts/GDS_logs'
 destination.mkdir(parents=True,exist_ok=True)
 zpath=ROOT/(name+'.zip');zpath.write_bytes(data)
 with zipfile.ZipFile(zpath) as z:
  for member in z.namelist():assert (destination/member).resolve().is_relative_to(destination.resolve())
  z.extractall(destination)
 records.append({'name':name,'artifact_id':aid,'sha256':digest})
gds=ROOT/'tt_submission/tt_um_armohamed_tdc12.gds'
assert hashlib.sha256(gds.read_bytes()).hexdigest()=='2c66650721f9d8c3d54b18e39038064a20b95f048d1b69d987ed50766105bd40'
shutil.copytree(ROOT/'official_artifacts/GDS_logs/runs/wokwi/final',ROOT/'deliverables',dirs_exist_ok=True)
(ROOT/'recovered_provenance.json').write_text(json.dumps(records,indent=2)+'\n')
print('Recovered official GDS, netlists and min/nom/max SPEF; every archive digest matches.')
