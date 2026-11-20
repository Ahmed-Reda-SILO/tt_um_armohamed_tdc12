# Exact 1000-cycle macro and wrapper bring-up

This verification branch reruns the full transistor-level pre-layout and
post-layout PEX test after the interactive execution environment became
unavailable. It uses the official GDS from source
b1c7dec19f113eb7fe47a1986d12d9c465be0c28, with SHA256
2c66650721f9d8c3d54b18e39038064a20b95f048d1b69d987ed50766105bd40.

The workflow compiles ngspice 44.2 with KLU/OpenMP, fetches the exact
Open PDKs 8afc8346a57fe1ab7934ba5a6056ea8b43078e71 with verified
release checksums, and reconstructs the actual GDS transistor extraction.
The original synthesized and powered routed netlists and SPEF come from
hash-verified official Actions artifacts. Production RTL and the layout
are inputs to this test.

Sequence: four reset clock edges, four more low-input clock edges,
1000 high periods at 1 MHz, read the held code 5 us after the falling edge.
Two later pulses of 10 and 20 periods demonstrate clocked capture of VALID.

Both stages use the same 1 ns input edges and TSTEP 2 ns / maximum timestep
20 ns at TT, 1.8 V and 25 C. All 24 wrapper outputs are checked at 1070
clock samples. No expected-value waveform replaces a simulated trace.
The workflow preserves actual failing data and plots it as a failure.

A coarse exploratory timestep gave an incorrect pre-layout carry at 31 to
32. The targeted finer-step test passed. This branch uses the finer
controls for the complete 1070 us runs.

The generated results, plots, compact analog records and CSVs appear
under results/ after the workflow completes. Full raw traces and executed
decks are retained as workflow artifacts. The external clocked receiver
is an ideal checker of the macro voltages, not a physical board model.
