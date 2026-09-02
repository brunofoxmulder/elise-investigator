from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from digital_twin import DigitalTwinHA


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class VirtualHAScenario:
    """Timeline-driven Home Assistant double for Investigator experiments.

    This is deliberately *not* a Home Assistant emulator. It only materialises
    the read surfaces Investigator consumes: current states, Recorder history,
    Logbook context, automation/script configuration and traces.

    A scenario can therefore be replayed at several instants against different
    Investigator revisions without ever connecting to the real house.
    """

    def __init__(
        self,
        *,
        initial_states: list[dict[str, Any]],
        events: list[dict[str, Any]],
        registries: dict[str, dict[str, Any]] | None = None,
        automation_configs: dict[str, dict[str, Any]] | None = None,
        script_configs: dict[str, dict[str, Any]] | None = None,
        scene_configs: dict[str, dict[str, Any]] | None = None,
        trace_summaries: dict[tuple[str, str], list[dict[str, Any]]] | None = None,
        trace_details: dict[tuple[str, str, str], dict[str, Any] | None] | None = None,
        time_zone: str = "Europe/Paris",
        ha_version: str = "2026.8.2",
    ):
        self.initial_states = deepcopy(initial_states)
        self.events = sorted(deepcopy(events), key=lambda event: _dt(event["time"]))
        self.registries = deepcopy(registries or {})
        self.automation_configs = deepcopy(automation_configs or {})
        self.script_configs = deepcopy(script_configs or {})
        self.scene_configs = deepcopy(scene_configs or {})
        self.trace_summaries = deepcopy(trace_summaries or {})
        self.trace_details = deepcopy(trace_details or {})
        self.time_zone = time_zone
        self.ha_version = ha_version

    def at(self, observed_time: str) -> DigitalTwinHA:
        cutoff = _dt(observed_time)
        states_by_id = {
            state["entity_id"]: deepcopy(state) for state in self.initial_states
        }
        histories: dict[str, list[dict[str, Any]]] = {}
        logbooks: dict[str, list[dict[str, Any]]] = {}

        for state in self.initial_states:
            entity_id = state["entity_id"]
            histories.setdefault(entity_id, []).append(self._history_state(state))

        for event in self.events:
            if _dt(event["time"]) > cutoff:
                break

            entity_id = event["entity_id"]
            previous = states_by_id.get(entity_id, {
                "entity_id": entity_id,
                "state": event.get("state", "unknown"),
                "attributes": {},
                "last_changed": event["time"],
                "last_updated": event["time"],
            })
            current = deepcopy(previous)

            state_changed = "state" in event and event["state"] != previous.get("state")
            if "state" in event:
                current["state"] = event["state"]
            current.setdefault("attributes", {})
            current["attributes"].update(deepcopy(event.get("attributes", {})))
            current["last_updated"] = event["time"]
            if state_changed:
                current["last_changed"] = event["time"]

            states_by_id[entity_id] = current
            histories.setdefault(entity_id, []).append(self._history_state(current))

            if event.get("logbook", True):
                entry: dict[str, Any] = {
                    "entity_id": entity_id,
                    "when": event["time"],
                    "message": event.get("message", "state changed"),
                }
                for key in (
                    "context_entity_id",
                    "context_entity_id_name",
                    "context_user_id",
                    "context_id",
                    "context_parent_id",
                    "domain",
                ):
                    if key in event:
                        entry[key] = deepcopy(event[key])
                logbooks.setdefault(entity_id, []).append(entry)

        return DigitalTwinHA(
            states=list(states_by_id.values()),
            histories=histories,
            logbooks=logbooks,
            registries=self.registries,
            automation_configs=self.automation_configs,
            script_configs=self.script_configs,
            scene_configs=self.scene_configs,
            trace_summaries=self.trace_summaries,
            trace_details=self.trace_details,
            time_zone=self.time_zone,
            ha_version=self.ha_version,
        )

    @staticmethod
    def _history_state(state: dict[str, Any]) -> dict[str, Any]:
        return {
            "state": state.get("state"),
            "attributes": deepcopy(state.get("attributes", {})),
            "last_changed": state.get("last_changed"),
            "last_updated": state.get("last_updated"),
        }
