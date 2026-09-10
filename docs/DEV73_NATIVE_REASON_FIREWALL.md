# Élise Investigator dev.73 — terminal native reason firewall

## Terrain trigger

Dev.72 failed on a real Home Assistant case where the final answer contained the raw provider sentence:

`triggered by state of binary_sensor.salle_de_bain_mouvement`

The structured result showed `reason_code = ha_2026_9_activity_native`.

## Root cause

The Activity reader lineage stores Home Assistant `context_message` directly in `record.reason` as `ha_2026_9_activity_native`. Exact trace semantics may replace it when they produce a stronger proven reason, but when they cannot, the raw provider sentence survives to the presentation layer.

Dev.71 guarded only one reason code (`ha_2026_9_activity_source_hint`), so an equivalent native provider sentence under another reason code escaped the guard.

## dev.73 correction

Dev.73 adds one terminal semantic firewall in `activity_reader_dev73.py`, after all dev.72 exact-trace work has completed and before the record reaches the answer renderer.

- Raw provider text beginning with `triggered by` is never exposed as final `record.reason` for an automation/script.
- Matching is on the provider text itself, not on one fragile reason code.
- The suppressed provider text and its original reason code remain in structured evidence under `record.trigger`.
- Proven exact-trace reasons are untouched.
- If exact trace cannot produce a semantic reason, the reader fails closed; the presentation layer may identify the automation/script but must not invent a stronger cause.

## Invariants

- No Home Assistant modification.
- No causal graph.
- No broad temporal correlation.
- unavailable/unknown handling unchanged.
- cover episode handling unchanged.
- dev.72 guard semantics unchanged.
- delay/wait/timeout semantics unchanged.
- generic Dockerfile + `/run.sh`; no dedicated `run_dev73.sh` or Dockerfile.
- dev.54 remains the official safe fallback.

CI and image publication do not constitute terrain validation.
