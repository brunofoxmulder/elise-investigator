# Behavioral digital twin test bench

The test suite can run the real Élise Investigator causal engine against an in-memory, read-only Home Assistant double.

`digital_twin.py` provides the reusable Home Assistant read surface. Scenario tests provide synthetic states, Recorder history, Logbook context, automation/script configuration and execution traces.

The twin never connects to a real Home Assistant instance and intentionally exposes no mutating service.

Real household data should not be committed to this public repository. Public regression scenarios must remain synthetic or anonymized while preserving the causal structure being tested.
