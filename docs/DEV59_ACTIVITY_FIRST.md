# dev.59 — Activity-first simplification

The normal Investigator path is intentionally simple and read-only:

1. Read Home Assistant Activity / Logbook over the configured window (12 h by default).
2. Ignore only technical `unknown` / `unavailable` noise when selecting the useful event.
3. Reuse Home Assistant's native attribution (`context_*`) as the causal source.
4. If Activity identifies one automation/script but does not provide enough detail, inspect only that exact execution trace.
5. Do not run broad reverse searches, causal graphs, or domain-specific causal engines in the normal Why path.

This document records the terrain-approved architecture and also provides a fresh CI trigger after the dev.59 publisher workflow was registered on `main`.
