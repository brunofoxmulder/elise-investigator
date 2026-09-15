# RC12 — Restore the start trigger after exact command projection

## Scope and authorization

Continuation authorized by Bruno on 15 September 2026 after the read-only diagnosis
of two immediate ON effects with a confirmed automation source but no functional
reason. RC11 remains installed on the Test channel until a separate terrain step.
No Home Assistant mutation, Test manifest promotion, merge, or dev54 change is part
of this candidate.

Base: `candidate-v2-rc11`, commit `d271d1a204d4343de3c29adaf5d9f47bb1de5b0f`.
Stable fallback: `dev54-fallback-stable`, commit
`8fc625217dbc0284496ad435a2ea8d9e7fee46b9`.

## Evidence and root cause

Observed on 15 September: two device-controlled charging switches turn ON directly
after the same tariff-window device trigger. Their runtime ON nodes contain a
timestamp but no `result.params`. One execution subsequently waits for power to
fall; the other delays and turns OFF. RC11 logs confirm `reason=null` for both ON
effects, while the delay-based OFF remains explained.

`TargetedMemoryEnricherV2._result()` calls `complete_confirmed_trace_chain()` before
RC11 projects config-only device commands. `executed_trace_actions()` cannot find
an explicit runtime command for the target yet, so the chain stays empty. RC11
subsequently recovers the exact command but never completes that missing chain.
The V2 resolver therefore has no proven start trigger. RC9 local default/delay
causes can still succeed without that start-trigger chain, explaining the ON/OFF
asymmetry.

The RC11 tests primarily cover OFF from a default branch, completed wait, or
adjacent delay. Their success does not establish that the initial trigger survives
for an earlier ON effect.

## Minimal correction

1. Apply the unchanged RC11 command projection (runtime parameters have priority;
   config is consulted only at the executed path, with exact registry resolution).
2. Return any existing RC9/V2 cause unchanged.
3. If no cause exists, require a unique executed command matching the effect.
4. Detach the chain, then complete it from the projected runtime evidence.
5. Reuse the unchanged RC9/V2 resolver. It still blocks the initial trigger when a
   temporal barrier before the effect makes that trigger insufficient.

The trigger is read from the actual runtime trace, never invented from configuration.
Raw evidence and the caller's chain are unchanged. The RC12 reader inherits RC11
trace selection; all rendering and event-age formatting are reused unchanged.
No entity name, tariff schedule, device ID, threshold, or household-specific rule
is added to production code.

## Verification

- Exact RC11 baseline: 375 tests PASS before edits.
- New expected ON behavior first fails under RC11 (including both end-to-end paths),
  then passes under RC12.
- Candidate suite: 413 tests PASS, including 15 new start-trigger tests, 20 existing
  contracts replayed through RC12, and 3 candidate packaging tests.
- Coverage includes initial ON before running wait/completed delay; missing runtime
  trigger; missing executed action; child lock; missing/wrong registry; runtime
  parameter precedence; ambiguous ON; preservation of local OFF reasons; temporal
  barrier rejection; immutable evidence/chain; record, reason code, provider-text
  firewall, and relative event age.
- Existing contracts cover lights, covers, Tineco, user commands, and joint factors.
- Generic Dockerfile, RC11 engine modules, RC9/V2 resolver, renderer, and dev54 are
  unchanged. Historical launcher assertions are retained as RC11 wrapper checks;
  RC12 now owns the current launcher/version assertion.

The fixtures are anonymized reconstructions of the observed structural facts,
not raw trace exports. They restore State dictionaries flattened by the HA MCP
summary. Local results establish code behavior; HAOS startup and natural ON events
must still be validated after Bruno installs the candidate.

## Distribution and terrain acceptance

Candidate branch: `candidate-v2-rc12`; image:
`ghcr.io/brunofoxmulder/elise-investigator-v2-rc12-private:0.3.0-rc.12`.
Its workflow runs the complete suite before building with the existing Dockerfile.
The image's availability is established only by successful GitHub workflow results.

After a separately approved Test manifest promotion and manual installation:
validate startup/Ingress, then observe the two natural ON paths and their OFF
counterparts. Expected ON result: correct source and event time, nonempty reason
from the runtime tariff-window trigger, `cause_found=true`, and
`reason_code=ha_logbook+exact_trace`. Preserve all previously validated paths.
