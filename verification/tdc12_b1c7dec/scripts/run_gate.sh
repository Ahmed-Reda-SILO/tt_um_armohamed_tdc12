#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
: "${PDK_ROOT:?Set PDK_ROOT to a directory containing sky130A}"
mkdir -p build reports/gate
iverilog -g2012 -DWAVE_WINDOW -DFUNCTIONAL -DPOWER_PINS -DUSE_POWER_PINS -DSIM '-DUNIT_DELAY=#1' \
  -s tdc_tb -o build/tdc_gate.vvp \
  "$PDK_ROOT/sky130A/libs.ref/sky130_fd_sc_hd/verilog/primitives.v" \
  "$PDK_ROOT/sky130A/libs.ref/sky130_fd_sc_hd/verilog/sky130_fd_sc_hd.v" \
  deliverables/pnl/tt_um_armohamed_tdc12.pnl.v test/tdc_tb.sv
cd reports/gate
vvp ../../build/tdc_gate.vvp | tee simulation.log
