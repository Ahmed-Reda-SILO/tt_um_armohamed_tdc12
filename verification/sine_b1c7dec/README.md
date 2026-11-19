# Full-macro sine verification of TDC12

This extension tests the unchanged official GDS and its Tiny Tapeout digital
wrapper at a **1 MHz** clock with **1 kHz, 10 kHz and 0.1 kHz** sine references.
The complete generated **user macro** is covered. The final shared shuttle mux,
pad ring, package, board and physical analog encoder are separate integration work.

Read `output/TDC12_Verification_Report.pdf` in the generated evidence ZIP.

## Results

| Sine | Prior PWM encoding: 20 kHz carrier, width 25 +/- 20 us | Zero-crossing high half-cycle |
| --- | --- | --- |
| 1 kHz | 20 samples/cycle; codes 5-45 | 500 us -> code 500, overflow 0 |
| 10 kHz | 2 samples/cycle; this phase aliases to code 25 | 50 us -> code 50, overflow 0 |
| 0.1 kHz | 200 samples/cycle; codes 5-45 | 5000 us -> code 4095, overflow 1 |

An additional **10 kHz / 100 kHz PWM** scenario uses widths 5 +/- 2 us.
It gives ten samples/cycle and codes 3-7: the variation is visible, but amplitude
resolution is coarse. A 12-bit width register does not imply a 12-bit amplitude ADC.

294 expected-behavior runs pass: seven scenarios across RTL, ten cell-only
pre-layout PVT points, thirty post-layout PVT/RC combinations, and one routed
zero-delay control. They contain 1,876,728 clock checks, 19,740 conversions and
84 expected overflow captures. All 24 wrapper outputs are checked each clock;
all 19 inputs are present and unused input pins are varied independently.

The **210 post-layout runs** contain **14,100 conversions**. No incorrect
integer result was found for the specified guarded input phases. A correct
overflow or aliased PWM result is a functional pass, not usable conversion
performance outside the stated range or sample-rate limits.

## What pre-layout and post-layout mean here

Pre-layout uses the actual 108-cell pre-placement synthesis netlist, the exact
PDK cell logic and Liberty-derived cell timing, with zero wire parasitics.
Post-layout uses all 139 active cells of the exact routed macro, including its
wrapper, with cell timing from extracted STA and all 314 SDF interconnect delays.
The 4245 power-only physical cells stay in GDS/LVS and are omitted from the
event-driven timing model. Both tie cells are retained with correct power pins.

These **full-duration sine tests are event-driven timing simulations**, not
full-duration BSIM transient simulations. The earlier actual GDS-device +
intercell-RC transistor results are retained as separate supporting evidence.

Correction to the original audit: timing-enabled PDK `specify` models exist.
The original broad digital test selected FUNCTIONAL models and used unit delays.
This extension combines the unchanged functional cell body with its original
PDK specify I/O paths, so Icarus 12 can annotate I/O delays without unsupported
timing-check delayed-data/clock outputs. Setup/hold/width checks remain in STA.

## Simulator adaptation and its verification

Icarus 12 does not directly implement SDF INTERCONNECT. The verification adapter
adds explicit per-sink rise/fall delay assignments for every routed interconnect
entry. It retains the original signal-cell instances and their logical connections.
Cell I/O delays are applied with `$sdf_annotate` to the original PDK specify paths.

Eight non-unate pin pairs have duplicate unconditional IOPATH records in the
OpenSTA SDF. The adapter uses the per-transition maximum envelope for each pair
and applies it to all matching PDK conditional paths. Negative cell delays in
nine fast routed variants are clamped to zero for causal event simulation. The
original extracted STA retains its original timing values and supplies hold signoff.
This is an explicit timing approximation, not a commercial simulator signoff claim.

A VPI probe reads the delays actually stored in the simulator. All **40 timing
models**, **10,010 unique input/output pin paths** and **17,050 conditional path
records** match the prepared data. A same-topology zero-delay control also passes.
One TT capture has VALID delay **0.471238 ns pre-layout**, **0.761667 ns after
layout**, and **0 ns in the zero-delay control**. These are observed example
delays, not the maximum chip delay.

## Source and geometry provenance

- Source commit: `b1c7dec19f113eb7fe47a1986d12d9c465be0c28`
- GDS SHA256: `2c66650721f9d8c3d54b18e39038064a20b95f048d1b69d987ed50766105bd40`
- Open PDKs: `8afc8346a57fe1ab7934ba5a6056ea8b43078e71`
- Official run: https://github.com/Ahmed-Reda-SILO/tt_um_armohamed_tdc12/actions/runs/44509700612

GDS, production RTL and the main branch have not been redesigned. DRC=0,
seven LVS mismatch metrics=0, precheck=16/16 and 30-corner extracted STA evidence
are carried forward for this identical GDS hash. They are not rerun per stimulus.

## Reproduce

Use Icarus 12 with specify support, OpenROAD/OpenSTA, gcc with Icarus VPI headers,
Python 3.12, NumPy, Matplotlib, ReportLab and PyMuPDF. Use the exact PDK above.
For original device/DRC/LVS tests, consult the adjacent `tdc12_b1c7dec` audit.

From this directory in the verification-branch checkout:

```bash
python3 scripts/prepare_workspace.py --results-zip /path/TDC_Sine_FullMacro_Verification_b1c7dec.zip
export PDK_ROOT=/path/to/exact/pdk_root
python3 scripts/make_prelayout_sdf.py --audit-root macro_evidence --pdk-root "$PDK_ROOT"
python3 scripts/run_sine_tests.py --audit-root macro_evidence --pdk-root "$PDK_ROOT"
python3 scripts/check_annotation.py --vpi-include /usr/include/iverilog
python3 scripts/make_sine_report.py --audit-root macro_evidence
```

The exact baseline SDF, physical views and corrected earlier evidence report are
under `macro_evidence/` in the ZIP. Tracked RTL/testbench source stays in GitHub;
the workspace preparer copies it from the checkout after checking SHA256 hashes.
`run_sine_tests.py --nominal-only` is available for a smaller initial rerun.
The individual commands above were exercised during verification; the exact
fresh-unpack command sequence depends on the receiving machine's tools and paths.

## Stimulus assumptions and operating limits

The reference is 0.9 + 0.6 sin(2 pi f t) V. The external encoder is ideal and is
not part of the GDS. Zero-crossing threshold is 0.9 V; PWM is sampled at each
frame start. Each scenario lasts two complete sine periods. Start phase is a
quarter clock period; widths are rounded to ns and moved by at most 50 ns away
from a sampling aperture. Actual widths and adjustments are recorded in CSVs.

Reset for at least two active clock edges after selection. Use a low gap above
two clock periods with margin. DATA_VALID is one cycle; capture the code with
a clocked receiver, not ordinary software polling. Saturation is 4095 sampled
high cycles. Clock jitter, metastability MTBF, analog encoder error, statistical
mismatch, supply noise, aging and fabrication yield are not characterized here.
Direct 5 pF loading on tile output cells exceeds electrical limits; representative
GPIO pad models pass 5 pF, but the final integrated path still needs signoff.
