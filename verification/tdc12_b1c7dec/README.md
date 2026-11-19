# TDC12 verification audit of b1c7dec

This audit verifies the official Tiny Tapeout GDS for source commit
`b1c7dec19f113eb7fe47a1986d12d9c465be0c28`. It adds verification scripts and a
stopped-clock/reselection bench. Production RTL and the main branch are unchanged.

Read `output/TDC12_Verification_Report.pdf` for measured plots, scope and limits.
`output/verification_summary.json` is the machine-readable result.

## Results

| Check | Result |
| --- | --- |
| RTL and routed functional regression | 131,508 checks, 1,064 conversions, 2 overflow events each; identical conversion CSVs |
| Clock stop, deselect/reselect, reset-high pulse rejection | Pass in RTL and routed functional models |
| RTL/routed formal logical equivalence | 44 points proven, zero unproven |
| Actual GDS device DRC and LVS | Zero DRC errors; all seven LVS mismatch metrics zero |
| Official Tiny Tapeout precheck | 16/16 pass |
| Extracted STA and electrical limits | 30/30 PVT/RC cases pass |
| Actual pre-layout and extracted transistor simulation | Five cases pass; 21 samples and three conversions each; all 24 wrapper outputs checked |
| Representative GPIO pad, 5 pF | Six PVT/mode cases pass |
| 1 pF or 5 pF directly on data/status tile pins | Electrical-limit violations; these loads require a physical GPIO driver |

Nominal core supply is **1.8 V**. The representative pad test uses nominal
**3.3 V I/O**, separate from the core. Board/shuttle specifications determine
permitted external voltage and rail sequencing.

The tile wrapper is included. The final assembled shared mux, pad-ring routing,
package and PCB are not included in the tile extraction. No test can guarantee
every fabricated chip. Final integration and silicon acceptance remain required.

## Source, layout and PDK provenance

- Official workflow run: https://github.com/Ahmed-Reda-SILO/tt_um_armohamed_tdc12/actions/runs/44509700612
- GDS SHA256: `2c66650721f9d8c3d54b18e39038064a20b95f048d1b69d987ed50766105bd40`
- Exact Open PDKs: `8afc8346a57fe1ab7934ba5a6056ea8b43078e71`
- Official flow: LibreLane 3.0.14, Magic primary streamout.
- Source/blob and downloaded artifact digests: `source_provenance.json` and `artifact_provenance.json`.

Use the official GDS; an earlier locally routed GDS has different geometry and
must not be paired with this audit's results. New extracted device SPICE is in
`deliverables/spice/`; the original official export uses black-box cells and is
not a transistor-level simulation model. The independent device extraction
corrects that verification-model limitation.

## Reproduce

Install Magic, Netgen, OpenROAD with OpenSTA, Icarus Verilog 12, ngspice 44.2 with
KLU, Yosys 0.52 and Python 3.12. Python dependencies are NumPy, Matplotlib,
ReportLab, zstandard, and `openlane==2.2.9` for the Netgen metric parser.
Some OpenROAD database schemas differ; the native database is rebuilt from the
unchanged official routed DEF and exact LEFs before timing checks.

Clone the verification branch, then enter `verification/tdc12_b1c7dec` and run:

```bash
python3 scripts/prepare_workspace.py --results-zip /path/TDC12_Official_GDS_Verification_b1c7dec.zip
python3 scripts/fetch_exact_pdk.py
export PDK_ROOT="$(cd .. && pwd)/.tooling/pdk_8afc8346"
bash scripts/run_full_audit.sh
```

Alternatively point `PDK_ROOT` to an existing exact release. The PDK fetcher
checks SHA256 of all downloaded release assets. Reproduction depends on external
tools and models; the full aggregate command is provided as a rerun entry point.
Individual constituent checks were run in the audit; the aggregate shell command
itself was syntax checked, not rerun after packaging.

The ZIP contains generated views, reports, decks and simulation results. Tracked
RTL and testbench source remain in GitHub; `prepare_workspace.py` copies the
unchanged `src/project.v`, `src/pulse_width_tdc.v` and `test/tdc_tb.sv` from that
checkout. Keep the checkout on this audit branch or the audited base commit.

## Testbenches and models

- The repository's `test/tdc_tb.sv` is the broad black-box reference bench. It
  checks sampled raw pulse widths, all result bits, reset/deselection abort,
  startup guard, saturation, overflow, one-cycle VALID, 1000 fractional-phase
  random pulses and a 1 kHz sine encoded as PWM.
- `test/wrapper_clock_stop_tb.sv` adds stopped-clock deselection/reselection,
  reset after selection, rejection of an input already high, and fresh 10/6 us
  conversion checks.
- `scripts/run_rc_spice.py` generates actual transistor decks before placement,
  after layout, and a same-routed-topology ideal-intercell-wire control. It tests
  2, 3 and 4 us pulses at 1 MHz, all 24 wrapper output voltages and three PVT/RC
  points. Actual executed `.cir`, `.spiceinit`, input hashes and `transient.tsv`
  are in `reports/rc_spice/`.
- `scripts/run_pad_load.py` generates schematic GPIO decks for 5 pF, DM=110,
  both output and bidirectional modes, TT/SS/FF with separate core/I/O rails.
  One TT/output case uses UIC for numerical startup; no transistor model change.
- `scripts/run_extracted_sta.py --all-characterized` checks 10 available NLDM
  library points from 1.60 to 1.95 V against min/nom/max RC. It includes setup,
  hold, capacitance, slew and fanout. These are characterized points, not a full
  Cartesian grid of every process, voltage and temperature combination.

Routed digital simulation uses **unit-delay functional models**, not SDF.
Extracted transistor simulation uses GDS MOS geometry and cell metal capacitance
plus the official flow's OpenRCX intercell R/C. Intracell metal resistance is not
extracted. Supplies are ideal. Power-only filler/tap/decap cells are present in
GDS/LVS but omitted from transient simulation. Full randomized coverage is
digital; transistor PEX coverage is the directed 21 us train. SDF files are
provided for a compatible timing-aware model/simulator flow, but were not
backannotated into the public models, which lack specify timing arcs.

## Correct external use

Use a 1 MHz clock for a 1 us LSB. Reset for at least two rising edges after
selection/reselection. Leave the input low for more than two periods with margin
between conversions. Sample all 12 data bits with a clocked receiver at the next
clock edge while DATA_VALID is high. DATA_VALID is only one period; ordinary
software polling is insufficient to guarantee capture. There is no FIFO/ACK.
An analog sine requires a separate voltage-to-time or PWM stage.

The final shared-mux/pad/package/board path, power integrity, clock jitter,
synchronizer MTBF, silicon variation, aging and fabrication yield require their
own evidence. The standalone pad result is feasibility evidence for 5 pF; it is
not assembled-chip post-layout signoff.
