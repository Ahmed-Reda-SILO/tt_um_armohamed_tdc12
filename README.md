# 12-bit pulse-width TDC for Tiny Tapeout SKY130

[![GDS and physical checks](https://github.com/Ahmed-Reda-SILO/tt_um_armohamed_tdc12/actions/workflows/gds.yaml/badge.svg?branch=main&event=push)](https://github.com/Ahmed-Reda-SILO/tt_um_armohamed_tdc12/actions/workflows/gds.yaml)
[![RTL tests](https://github.com/Ahmed-Reda-SILO/tt_um_armohamed_tdc12/actions/workflows/test.yaml/badge.svg?branch=main&event=push)](https://github.com/Ahmed-Reda-SILO/tt_um_armohamed_tdc12/actions/workflows/test.yaml)
[![Documentation](https://github.com/Ahmed-Reda-SILO/tt_um_armohamed_tdc12/actions/workflows/docs.yaml/badge.svg?branch=main&event=push)](https://github.com/Ahmed-Reda-SILO/tt_um_armohamed_tdc12/actions/workflows/docs.yaml)

Author: Ahmed Reda Mohamed. Top module: `tt_um_armohamed_tdc12`.

This counter-based time-to-digital converter measures each positive input pulse
independently. With a 1 MHz reference clock, one output code unit represents
1 microsecond. The 12-bit code saturates at 4095 and reports overflow.

The input passes through a two-stage synchronizer. A complete pulse starts a
fresh working count. Its falling edge captures the result and asserts
DATA_VALID for one clock cycle. The previous result stays available during
the next measurement. A startup guard ignores an input already high through
reset until it goes low and a complete new pulse arrives.

## Pin mapping

| Tiny Tapeout port | Function |
| --- | --- |
| clk | 1 MHz reference clock, rising edge |
| rst_n | Synchronous active-low reset |
| ena | Project selection |
| ui_in[0] | Digital pulse input |
| ui_in[7:1] | Unused |
| uo_out[7:0] | Stored width code bits 7:0 |
| uio_out[3:0] | Stored width code bits 11:8 |
| uio_out[4] | DATA_VALID, high for one clock |
| uio_out[5] | BUSY, after input synchronization |
| uio_out[6] | OVERFLOW for the stored result |
| uio[7] | Unused, input mode |

The uio output-enable word is 0x7F while selected and 0x00 otherwise.
The nominal user-tile core supply is 1.8 V. External signal levels must follow
the selected Tiny Tapeout board/pad interface.

## Operating requirements

- Hold rst_n low across at least two reference-clock rising edges after
  selecting the project. Reset again after reselecting it; an inactive
  project's clock can stop.
- Provide high widths and low gaps of at least two reference periods with
  timing margin. At 1 MHz this means at least 2 us plus margin. Shorter events
  can be missed or merged.
- The startup guard waits for low before measuring. A high input through
  reset release does not produce a partial-pulse code.
- Capture the code synchronously while DATA_VALID is high. On the same
  reference clock, the receiver samples the following rising edge so the code
  has a full cycle to settle. There is no FIFO or acknowledge interface.
- DATA_VALID normally arrives two to three reference periods after the raw
  falling edge. BUSY also includes synchronization delay.
- The result and OVERFLOW remain at the output until the next completed
  pulse. Longer than 4095 sampled high cycles saturates the code at 4095.
- Timing resolution is one reference period. Synchronization reduces
  metastability propagation risk; clock jitter and metastability MTBF require
  separate characterization.

## Sine-wave example

An external PWM or voltage-to-time encoder must first encode the analog
amplitude as a digital pulse width. At a 20 kHz pulse rate, a 1 kHz sine has
20 measurements per cycle. A 5-45 us width span gives 41 nominal code levels
at a 1 us timing step. The 12-bit word specifies the available count range;
it does not provide 12-bit amplitude precision over that short span.

## Tests and build

`test/test.py` is the portable cocotb test used for RTL and the official
gate-level build. It checks pulse conversion, result retention, startup guard,
reset, overflow and all wrapper outputs. `test/tdc_tb.sv` contains the longer
standalone test with 1,064 conversions, fractional phases and a sine pulse train.

The source was verified locally before upload: 131,508 clock checks and 1,064
conversions at both RTL and routed netlist, clean DRC/LVS/antenna checks,
Tiny Tapeout precheck, nine extracted PVT/RC timing cases, and five short
transistor-level nominal/comparison/PVT-stress runs. GitHub Actions rebuilds
the source in the official shuttle environment; its artifacts and results are
the submission version and can differ from the local layout.

Direct tile-output tests at 5 pF passed functional voltage checks but exceeded
core-cell characterized capacitance/slew limits. The full shared Tiny Tapeout
mux/pad/board path with 5 pF has not been verified. No silicon measurement or
fabrication submission is claimed here.

See [Actions](https://github.com/Ahmed-Reda-SILO/tt_um_armohamed_tdc12/actions)
for the official build, test, documentation and precheck status.
