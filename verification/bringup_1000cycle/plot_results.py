#!/usr/bin/env python3
"""Render the measured full-duration pre/post transistor results, including failures."""
from pathlib import Path
import csv,hashlib,json,os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results'
PLOTS=OUT/'plots'
PLOTS.mkdir(parents=True,exist_ok=True)
cases={s:json.loads((ROOT/'runs'/s/'summary.json').read_text()) for s in ['pre','post']}
data={s:np.load(ROOT/'runs'/s/'waveforms_for_plot.npz')['data'] for s in cases}
assert all(c['continuous_transient_us']>=1069.99 for c in cases.values())
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8.3,'axes.labelsize':9,
 'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42,'axes.linewidth':.7})
colors={'pre':'#176ba0','post':'#d45a33'}
styles={'pre':'-','post':'--'}
labels={'pre':'Pre-layout BSIM','post':'Post-layout PEX BSIM'}
figures=[]
def style(ax):
 ax.grid(alpha=.16);ax.tick_params(direction='in',length=3)
def signal(ax,stage,col,lo,hi):
 a=data[stage];t=a[:,0]*1e6;sel=(t>=lo)&(t<=hi)
 ax.plot(t[sel],a[sel,col],styles[stage],color=colors[stage],lw=1.2,label=labels[stage])
 ax.set_ylim(-.1,2);ax.set_yticks([0,.9,1.8])
def code(ax,stage,lo,hi):
 a=data[stage];t=a[:,0]*1e6;sel=(t>=lo)&(t<=hi)
 val=((a[sel,1:13]>.9)*(2**np.arange(12))).sum(axis=1)
 ax.step(t[sel],val,where='post',ls=styles[stage],color=colors[stage],lw=1.25,label=labels[stage])
def save(fig,name):
 fig.savefig(PLOTS/(name+'.png'),dpi=400,bbox_inches='tight',facecolor='white')
 fig.savefig(PLOTS/(name+'.pdf'),bbox_inches='tight',facecolor='white')
 figures.append(fig)
fig,axes=plt.subplots(5,1,figsize=(7.2,6),sharex=True)
for s in cases:
 signal(axes[0],s,26,0,1070)
 signal(axes[1],s,14,.7,1070)
 code(axes[2],s,.7,1070)
 signal(axes[3],s,13,.7,1070)
 signal(axes[4],s,15,.7,1070)
for ax,lab in zip(axes,['PULSE_IN (V)','BUSY (V)','Held code','VALID (V)','OVERFLOW (V)']):
 style(ax);ax.set_ylabel(lab);ax.set_xlim(0,1070)
axes[0].annotate('',xy=(8.25,1.5),xytext=(1008.25,1.5),arrowprops={'arrowstyle':'<->','lw':.8,'color':'#445566'})
axes[0].text(508.25,1.05,'1000 clock periods = 1000 us',ha='center',fontsize=9)
axes[0].legend(frameon=False,ncol=2,loc='upper left',bbox_to_anchor=(0,1.35))
axes[2].set_ylim(-30,1070);axes[2].set_yticks([0,500,1000])
axes[-1].set_xlabel('Time (us)')
fig.suptitle('Full macro + wrapper | 1 MHz | TT, 1.8 V, 25 C',fontsize=11,y=.995)
fig.tight_layout(rect=[0,0,1,.95],h_pad=.35)
save(fig,'01_1000cycle_pre_post_overview')
fig,axes=plt.subplots(4,1,figsize=(7.2,4.8),sharex=True)
for s in cases:
 for ax,col in zip(axes,[25,27,28,26]):signal(ax,s,col,0,12)
for ax,lab in zip(axes,['CLK (V)','RST_N (V)','ENA (V)','PULSE_IN (V)']):
 style(ax);ax.set_ylabel(lab);ax.set_xlim(0,12)
 ax.axvspan(0,4,color='#dce8f3',alpha=.5);ax.axvspan(4,8,color='#dcf0e4',alpha=.5)
axes[0].text(2,2.25,'4 reset edges',ha='center',fontsize=9)
axes[0].text(6,2.25,'4 further low-input edges',ha='center',fontsize=9)
axes[-1].set_xlabel('Time (us)')
fig.suptitle('Applied reset, idle and pulse-start sequence',fontsize=11,y=.995)
fig.tight_layout(rect=[0,0,1,.95],h_pad=.6)
save(fig,'02_four_reset_four_idle')
fig,axes=plt.subplots(6,1,figsize=(7.2,7),sharex=True)
lo,hi=1007.5,1014.5
for s in cases:
 signal(axes[0],s,25,lo,hi);signal(axes[1],s,26,lo,hi);code(axes[2],s,lo,hi)
 signal(axes[3],s,13,lo,hi);signal(axes[4],s,14,lo,hi);signal(axes[5],s,15,lo,hi)
for ax,lab in zip(axes,['CLK (V)','PULSE_IN (V)','Decoded code','VALID (V)','BUSY (V)','OVERFLOW (V)']):
 style(ax);ax.set_ylabel(lab);ax.set_xlim(lo,hi)
 ax.axvline(1011.5,color='#46916f',lw=.8);ax.axvline(1013.25,color='#9563a9',lw=.8)
axes[0].text(1011.5,2.28,'Clocked capture',ha='center',fontsize=8,color='#26704f')
axes[0].text(1013.25,2.28,'Read after 5 us',ha='center',fontsize=8,color='#7c4593')
axes[0].legend(frameon=False,ncol=2,loc='upper center',bbox_to_anchor=(.5,1.8))
axes[2].set_ylim(-30,1070);axes[2].set_yticks([0,500,1000])
axes[-1].set_xlabel('Time (us)')
pre=cases['pre']['conversions'][0];post=cases['post']['conversions'][0]
fig.suptitle(f"Measured initial result: pre {pre['captured_code']}, post {post['captured_code']} | expected 1000",fontsize=10.5,y=.995)
fig.tight_layout(rect=[0,0,1,.93],h_pad=.4)
save(fig,'03_1000count_capture_zoom')
fig,axes=plt.subplots(15,1,figsize=(7.2,9.6),sharex=True)
names=[f'uo[{i}] / b{i}' for i in range(8)]+[f'uio[{i}] / b{i+8}' for i in range(4)]+['uio[4] VALID','uio[5] BUSY','uio[6] OVF']
for s in cases:
 for ax,col in zip(axes,list(range(1,13))+[13,14,15]):signal(ax,s,col,1009.5,1013.7)
for ax,lab in zip(axes,names):
 style(ax);ax.set_ylabel(lab,rotation=0,ha='right',va='center',fontsize=8);ax.set_yticks([0,1.8]);ax.set_xlim(1009.5,1013.7)
axes[-1].set_xlabel('Time (us)')
fig.suptitle('Actual wrapper voltages | expected code 0x3E8 = 0011 1110 1000',fontsize=10,y=.999)
fig.tight_layout(rect=[0,0,1,.975],h_pad=.08)
save(fig,'04_wrapper_12bit_outputs')
fig,axes=plt.subplots(3,1,figsize=(7.2,4.7),sharex=True)
for s in cases:
 code(axes[0],s,1006,1070);signal(axes[1],s,13,1006,1070);signal(axes[2],s,26,1006,1070)
 for c in cases[s]['conversions']:axes[0].plot(c['capture_clock_us'],c['captured_code'],'o',color=colors[s],ms=4)
for ax,lab in zip(axes,['Captured / held code','VALID (V)','PULSE_IN (V)']):
 style(ax);ax.set_ylabel(lab);ax.set_xlim(1006,1070)
axes[0].set_ylim(-35,1130);axes[0].legend(frameon=False,ncol=2,loc='upper center',bbox_to_anchor=(.5,1.4))
axes[-1].set_xlabel('Time (us)');fig.suptitle('Successive captures | expected 1000, 10 and 20',fontsize=11,y=.995)
fig.tight_layout(rect=[0,0,1,.94],h_pad=.5)
save(fig,'05_successive_clocked_captures')
with PdfPages(OUT/'TDC12_1000cycle_Pre_Post_Plots.pdf') as pdf:
 for f in figures:pdf.savefig(f,bbox_inches='tight')
for f in figures:plt.close(f)
summary={'all_passed':all(c['passed'] for c in cases.values()),'pre':cases['pre'],'post':cases['post'],
 'pre_github_run_id':os.environ.get('TDC_PRE_RUN_ID',os.environ.get('GITHUB_RUN_ID')),'post_github_run_id':os.environ.get('GITHUB_RUN_ID'),'github_run_id':os.environ.get('GITHUB_RUN_ID'),'github_run_url':os.environ.get('GITHUB_SERVER_URL','https://github.com')+'/'+os.environ.get('GITHUB_REPOSITORY','Ahmed-Reda-SILO/tt_um_armohamed_tdc12')+'/actions/runs/'+os.environ.get('GITHUB_RUN_ID','')}
(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
rows=[{'stage':s,**c} for s in cases for c in cases[s]['conversions']]
with (OUT/'conversions.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
lines=['# Exact 1000-cycle TDC bring-up: measured BSIM/PEX results','',
'Source: b1c7dec19f113eb7fe47a1986d12d9c465be0c28.',
'GDS SHA256: 2c66650721f9d8c3d54b18e39038064a20b95f048d1b69d987ed50766105bd40.',
'','1 MHz, TT, 1.8 V core, 25 C. Both simulations run one continuous 1070 us transistor transient.',
'Numerics: TSTEP 2 ns, maximum timestep 20 ns, Gear, reltol 1e-4; no pause/resume or stitched counter states.',
'','| Check | Pre-layout | Post-layout PEX |','| --- | --- | --- |']
for label,key in [('Captured code','captured_code'),('Code read 5 us after falling edge','read_5us_code'),('Overflow','overflow'),('VALID width (us)','valid_width_us'),('uo at read','read_uo_hex'),('uio at read','read_uio_hex')]:
 lines.append(f"| {label} | {pre[key]} | {post[key]} |")
lines+=['',f"Overall test passed: **{summary['all_passed']}**. Actual measured values are preserved even when a run fails.",
'', 'Applied edges: reset low for 0.5, 1.5, 2.5, 3.5 us rising edges. Reset releases at 4 us; input stays low at 4.5, 5.5, 6.5, 7.5 us.',
'Input rises at 8.25 us and falls at 1008.25 us. Held result is read at 1013.25 us. Two further 10 and 20 us pulses check successive capture.',
'', 'All 24 wrapper outputs are checked at 1070 clock samples per model. Hardware capture is an ideal external sampling checker of actual analog node voltages, not a simulated physical board receiver.',
'', 'Scope: all 108 pre-layout or 139 routed active macro cells, including the wrapper. Post-layout uses actual GDS MOS geometry, cell metal capacitance and nominal OpenRCX intercell R/C. Supplies are ideal; power-only cells are omitted. Intracell metal resistance and assembled shared mux/pads/package/PCB are outside this extraction.',
'', 'An earlier exploratory coarse-timestep pre-layout run produced 1016. A targeted carry test passed with the original finer settings; this workflow therefore reruns both full models using those finer controls. The exploratory result is not a pass result or a confirmed silicon defect.',
'', f"Post-layout raw data and decks: {summary['github_run_url']} (artifact tdc12-post-raw).", f"Pre-layout raw data and decks: https://github.com/Ahmed-Reda-SILO/tt_um_armohamed_tdc12/actions/runs/{summary['pre_github_run_id']} (artifact tdc12-pre-raw).",
'', '![Full trace](plots/01_1000cycle_pre_post_overview.png)','',
'![Capture and readout](plots/03_1000count_capture_zoom.png)']
(OUT/'README.md').write_text('\n'.join(lines)+'\n')
# Commit compact, faithful measurement subsets while preserving full traces in artifacts.
(OUT/'data').mkdir(exist_ok=True)
for s,a in data.items():
 t=a[:,0]*1e6
 window=(t<=12)|((t>=1007.5)&(t<=1014.5))|((t>=1027.5)&(t<=1034.5))|((t>=1059.5)&(t<=1066.5))
 change=np.any((a[1:,1:29]>.9)!=(a[:-1,1:29]>.9),axis=1)
 ids=np.where(change)[0]
 mask=window.copy()
 for shift in [-1,0,1,2]:mask[np.clip(ids+shift,0,len(a)-1)]=True
 np.savez_compressed(OUT/'data'/f'{s}_plot_waveforms.npz',data=a[mask])
print(json.dumps({'all_passed':summary['all_passed'],'pre_code':pre['captured_code'],'post_code':post['captured_code'],'plots':str(PLOTS)},indent=2))
