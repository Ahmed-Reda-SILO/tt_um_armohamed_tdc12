#!/usr/bin/env python3
"""Run full-duration sine scenarios through RTL and complete timed macro views."""
import argparse,concurrent.futures,csv,hashlib,json,math,re,subprocess,time
from pathlib import Path
from prepare_timed_model import build

p=argparse.ArgumentParser();p.add_argument('--audit-root',type=Path,required=True);p.add_argument('--pdk-root',type=Path,required=True)
p.add_argument('--nominal-only',action='store_true');p.add_argument('--resume',action='store_true');a=p.parse_args()
root=Path(__file__).resolve().parents[1];audit=a.audit_root.resolve();pdk=a.pdk_root.resolve()/'sky130A'
reports=root/'reports';stimdir=root/'stimulus';stimdir.mkdir(exist_ok=True)
gds=audit/'tt_submission/tt_um_armohamed_tdc12.gds'
gds_hash=hashlib.sha256(gds.read_bytes()).hexdigest()
assert gds_hash=='2c66650721f9d8c3d54b18e39038064a20b95f048d1b69d987ed50766105bd40'
cases=[]
for f in [1000,10000,100]:
    period=round(1e9/f);width=period//2
    cases.append({'name':f'zero_cross_{f}Hz','sine_hz':f,'encoding':'zero_crossing','period_ns':period,'frames':2,
        'center_us':None,'amplitude_us':None,'pwm_hz':None,'cycles':2})
for f,rate,center,amplitude in [(1000,20000,25,20),(10000,20000,25,20),(100,20000,25,20),(10000,100000,5,2)]:
    cases.append({'name':f'pwm_{f}Hz_{rate}Hzcarrier','sine_hz':f,'encoding':'sampled_pwm','period_ns':round(1e9/rate),
        'frames':round(2*rate/f),'center_us':center,'amplitude_us':amplitude,'pwm_hz':rate,'cycles':2})
for c in cases:
    data=[]
    for n in range(c['frames']):
        start=8250+n*c['period_ns'];sine=math.sin(2*math.pi*n*c['sine_hz']*(c['period_ns']*1e-9))
        idealwidth=(c['period_ns']/2 if c['encoding']=='zero_crossing' else (c['center_us']+c['amplitude_us']*sine)*1000)
        width=round(idealwidth)
        # Guard against a deliberate exact first-stage aperture collision. This
        # changes the ideal encoder width by at most 50 ns, recorded per pulse.
        rem=(start+width-500)%1000
        if rem<25:width+=25-rem
        elif rem>975:width+=1025-rem
        count=math.ceil((start+width-500)/1000)-math.ceil((start-500)/1000)
        assert min(width,c['period_ns']-width)>=2000 if c['encoding']=='sampled_pwm' else width>0
        data.append({'sample':n,'start_ns':start,'width_ns':width,'ideal_width_ns':idealwidth,'phase_guard_ns':width-idealwidth,
            'sine_normalized':sine,'expected_raw_samples':count,'expected_code':min(4095,count),'expected_overflow':int(count>4095)})
    c['pulses']=data;c['finish_ns']=8250+c['frames']*c['period_ns']+4000
    with (stimdir/(c['name']+'.txt')).open('w') as f:
        for d in data:f.write(f"{d['start_ns']} {d['width_ns']} {d['expected_code']} {d['expected_overflow']}\n")
    (stimdir/(c['name']+'.json')).write_text(json.dumps(c,indent=2)+'\n')
    with (stimdir/(c['name']+'.csv')).open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
(stimdir/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')

pre=json.loads((reports/'prelayout_sta/summary.json').read_text())
post=json.loads((audit/'reports/sta/audited_summary.json').read_text())
if a.nominal_only:
    pre=[s for s in pre if s['corner']=='tt_025C_1v80'];post=[s for s in post if s['corner']=='nom_tt_025C_1v80']
variants=[{'name':'rtl','stage':'rtl'}]
variants += [{'name':'pre_'+s['corner'],'stage':'prelayout','sdf':str(root/'reports/prelayout_sta'/s['corner']/'tdc.sdf'),'corner':s['corner']} for s in pre]
variants += [{'name':'post_'+s['corner'],'stage':'postlayout','sdf':str(audit/'reports/sta'/s['corner']/'tdc.sdf'),'corner':s['corner']} for s in post]
variants += [{'name':'post_zero_control','stage':'zero_control','sdf':str(audit/'reports/sta/nom_tt_025C_1v80/tdc.sdf'),'corner':'nom_tt_025C_1v80'}]
def compile_one(v):
    folder=root/'build'/v['name'];folder.mkdir(exist_ok=True)
    if v['stage']=='rtl':
        sources=[audit/'src/project.v',audit/'src/pulse_width_tdc.v'];flags=[];metadata={'stage':'rtl'}
    else:
        net=(audit/'official_artifacts/GDS_logs/runs/wokwi/06-yosys-synthesis/tt_um_armohamed_tdc12.nl.v') if v['stage']=='prelayout' else audit/'deliverables/pnl/tt_um_armohamed_tdc12.pnl.v'
        metadata=build(root,audit,pdk,net,Path(v['sdf']),folder,prelayout=v['stage']=='prelayout',zero=v['stage']=='zero_control')
        sources=[folder/'cells.v',folder/'macro.v'];flags=['-gspecify','-DPOWER_PINS','-DTIMED_MODEL']
    cmd=['iverilog','-g2012','-Ttyp',*flags,'-s','sine_wave_tb','-o',str(folder/'simulation.vvp'),*[str(x) for x in sources],str(root/'test/sine_wave_tb.sv')]
    cp=subprocess.run(cmd,capture_output=True,text=True,timeout=40);(folder/'compile.log').write_text(cp.stdout+cp.stderr)
    if cp.returncode:raise RuntimeError(v['name']+' compile failed: '+cp.stderr[-2200:])
    return v,metadata
models=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
    for v,m in ex.map(compile_one,variants):models.append({'variant':v,**m})
def run(job):
    v,c=job;out=reports/'sine'/v['name']/c['name'];out.mkdir(parents=True,exist_ok=True)
    previous=out/'summary.json'
    if a.resume and previous.exists():
        saved=json.loads(previous.read_text())
        if saved.get('passed'):return saved
    cmd=['vvp',str(root/'build'/v['name']/'simulation.vvp'),'+stimulus='+str(stimdir/(c['name']+'.txt')),'+finish_ns='+str(c['finish_ns'])]
    if v['stage']!='rtl':cmd.append('+sdf='+str(root/'build'/v['name']/'cells.sdf'))
    waves=(v['name'] in ['rtl','pre_tt_025C_1v80','post_nom_tt_025C_1v80'] or (v['stage']=='zero_control' and c['name']=='zero_cross_10000Hz'))
    if waves:cmd.append('+waves')
    t=time.monotonic();rp=subprocess.run(cmd,capture_output=True,text=True,cwd=out,timeout=70)
    log=rp.stdout+rp.stderr;(out/'simulation.log').write_text(log)
    if rp.returncode or 'PASS:' not in log or re.search(r'SDF\s+(?:WARNING|ERROR)|Unable to match|not supported',log,re.I):
        raise RuntimeError(v['name']+' '+c['name']+' '+log[-2500:])
    with (out/'conversions.csv').open() as f:rows=list(csv.DictReader(f))
    assert len(rows)==len(c['pulses'])
    errors=[]
    for d,r in zip(c['pulses'],rows):
        if int(r['code_decimal'])!=d['expected_code'] or int(r['overflow'])!=d['expected_overflow']:errors.append([d,r])
    info=re.search(r'PASS: (\d+) clock checks; (\d+) conversions; (\d+) overflow captures',log)
    result={'variant':v['name'],'stage':v['stage'],'case':c['name'],'sine_hz':c['sine_hz'],'encoding':c['encoding'],
        'clock_checks':int(info[1]),'conversions':int(info[2]),'overflow_captures':int(info[3]),'passed':not errors,
        'code_min':min(int(r['code_decimal']) for r in rows),'code_max':max(int(r['code_decimal']) for r in rows),
        'runtime_seconds':time.monotonic()-t,'duration_ns':c['finish_ns'],'waves_saved':waves,'sdf_warnings_or_errors':0,
        'maximum_abs_width_error_us':max(abs(int(r['code_decimal'])-d['width_ns']/1000) for d,r in zip(c['pulses'],rows)) if not any(d['expected_overflow'] for d in c['pulses']) else None,
        'errors':errors}
    if c['encoding']=='sampled_pwm':
        decoded=[(int(r['code_decimal'])-c['center_us'])/c['amplitude_us'] for r in rows]
        result['decoded_sine_sample_rmse']=math.sqrt(sum((x-d['sine_normalized'])**2 for x,d in zip(decoded,c['pulses']))/len(rows))
        result['unique_codes']=len(set(int(r['code_decimal']) for r in rows))
    previous.write_text(json.dumps(result,indent=2)+'\n')
    if errors:raise RuntimeError('Unexpected conversion values: '+v['name']+' '+c['name'])
    return result
jobs=[(v,c) for v in variants for c in cases]
results=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
    for n,result in enumerate(ex.map(run,jobs),1):
        results.append(result)
        if n%14==0 or n==len(jobs):print(f'Passed {n}/{len(jobs)} simulation cases',flush=True)
summary={'source_commit':'b1c7dec19f113eb7fe47a1986d12d9c465be0c28','gds_sha256':gds_hash,
    'reference_clock_hz':1000000,'all_passed':all(r['passed'] for r in results),'simulation_cases':len(results),
    'postlayout_pvt_rc_variants':len(post),'prelayout_cell_pvt_variants':len(pre),'test_scenarios':len(cases),
    'postlayout_scope':'Complete user macro incl. digital wrapper, SDF cell I/O paths (maximum envelope for duplicate non-unate pin arcs) plus explicit SDF interconnect delay assignments; not BSIM transient or assembled-shuttle pad/package extraction',
    'setup_hold_verification':'Separate 30-corner extracted STA; SDF timing-check notifiers and metastability not modeled',
    'models':models,'results':results}
(reports/'sine_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
with (reports/'sine_results.csv').open('w') as f:
    keys=['variant','stage','case','sine_hz','encoding','clock_checks','conversions','overflow_captures','code_min','code_max','passed']
    w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(results)
print(json.dumps({k:v for k,v in summary.items() if k not in ['models','results']},indent=2))
