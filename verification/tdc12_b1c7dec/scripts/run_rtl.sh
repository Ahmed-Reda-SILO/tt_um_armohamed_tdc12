#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
mkdir -p build reports/rtl
iverilog -g2012 -DWAVE_WINDOW -s tdc_tb -o build/tdc_rtl.vvp src/project.v src/pulse_width_tdc.v test/tdc_tb.sv
cd reports/rtl
vvp ../../build/tdc_rtl.vvp | tee simulation.log
