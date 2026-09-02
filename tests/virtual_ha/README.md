# Virtual HA scenario lab

Purpose: replay realistic Home Assistant event timelines against Élise Investigator revisions **without running Home Assistant** and without touching the real house.

This lab extends the existing static `tests/digital_twin.py` read double with a timeline engine. A scenario contains only the surfaces Investigator actually consumes:

- current entity states and attributes;
- Recorder-like history;
- Logbook-like context;
- automation/script configuration;
- trace summaries and trace details.

It intentionally does **not** implement service calls, devices, integrations, networking, Zigbee, voice hardware or Home Assistant itself. The generated twin remains strictly read-only.

## Why

A single unit fixture can prove one instant while missing a regression that appears several minutes later. The timeline engine lets the same scenario be queried repeatedly as the simulated house evolves.

The first scenario reproduces the causal shape observed on 2026-09-02:

1. an automation starts a lamp brightness transition with confirmed automation context;
2. later brightness samples arrive with poor/no fresh causal context;
3. the same Investigator revision is queried at the start, middle and end of the transition;
4. a separate cover episode is kept beside it so a brightness experiment cannot silently break the validated cover behavior.

All committed scenarios must be synthetic or anonymised. Do not commit private household data.

## Files

- `scenario_engine.py`: timeline -> `DigitalTwinHA` snapshot materialiser.
- `scenarios.py`: reusable synthetic scenarios.
- `probe.py`: runs the checked-out Investigator implementation at several instants and prints its actual causal answers.
- `../test_virtual_ha_scenarios.py`: safety tests for timeline replay and read-only isolation.

## Comparing Investigator revisions

The scenario lab is branch-independent. Check out/copy it beside any Investigator revision, then run:

```bash
python tests/virtual_ha/probe.py
```

The output is JSON and shows the behavior of **that checked-out revision** at each probe instant. This makes it possible to compare dev revisions on the exact same virtual house chronology before publishing/installing them in Home Assistant.

The lab branch is deliberately separate from runtime development. No production or Test add-on manifest is changed by this work.
