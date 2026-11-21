#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
: "${PDK_ROOT:?Set PDK_ROOT to the exact Open PDKs root containing sky130A}"
bash scripts/run_rtl.sh
bash scripts/run_gate.sh
python3 scripts/run_clock_stop.py --pdk-root "$PDK_ROOT"
python3 scripts/run_equivalence.py --pdk-root "$PDK_ROOT"
python3 scripts/prepare_native_sta_db.py --pdk-root "$PDK_ROOT"
python3 scripts/extract_gds_devices.py --pdk-root "$PDK_ROOT"
python3 scripts/run_device_lvs.py --pdk-root "$PDK_ROOT"
python3 scripts/run_extracted_sta.py --pdk-root "$PDK_ROOT" --state build/native_state.json --all-characterized
python3 scripts/check_connectivity.py --pdk-root "$PDK_ROOT"
python3 scripts/check_output_load_sta.py --pdk-root "$PDK_ROOT" --state build/native_state.json
python3 scripts/run_rc_spice.py --pdk-root "$PDK_ROOT" --prelayout
python3 scripts/run_rc_spice.py --pdk-root "$PDK_ROOT" --ideal-wire
python3 scripts/run_rc_spice.py --pdk-root "$PDK_ROOT"
python3 scripts/run_rc_spice.py --pdk-root "$PDK_ROOT" --corner ss --rc max --vdd 1.6 --temperature 100
python3 scripts/run_rc_spice.py --pdk-root "$PDK_ROOT" --corner ff --rc min --vdd 1.95 --temperature -40
python3 scripts/run_pad_load.py --pdk-root "$PDK_ROOT"
python3 scripts/make_audit_report.py
