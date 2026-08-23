from __future__ import annotations

from copy import deepcopy
from typing import Any


class DigitalTwinHA:
    """In-memory, read-only Home Assistant double for Investigator tests.

    The twin deliberately implements only the read methods used by Investigator.
    It never calls Home Assistant and exposes no mutating service.
    """

    def __init__(
        self,
        *,
        states: list[dict[str, Any]],
        histories: dict[str, list[dict[str, Any]]] | None = None,
        logbooks: dict[str, list[dict[str, Any]]] | None = None,
        registries: dict[str, dict[str, Any]] | None = None,
        automation_configs: dict[str, dict[str, Any]] | None = None,
        script_configs: dict[str, dict[str, Any]] | None = None,
        scene_configs: dict[str, dict[str, Any]] | None = None,
        trace_summaries: dict[tuple[str, str], list[dict[str, Any]]] | None = None,
        trace_details: dict[tuple[str, str, str], dict[str, Any] | None] | None = None,
        time_zone: str = "Europe/Paris",
        ha_version: str = "2026.8.2",
    ):
        self.states = deepcopy(states)
        self.histories = deepcopy(histories or {})
        self.logbooks = deepcopy(logbooks or {})
        self.registries = deepcopy(registries or {})
        self.automation_configs = deepcopy(automation_configs or {})
        self.script_configs = deepcopy(script_configs or {})
        self.scene_configs = deepcopy(scene_configs or {})
        self.trace_summaries = deepcopy(trace_summaries or {})
        self.trace_details = deepcopy(trace_details or {})
        self.time_zone = time_zone
        self.ha_version = ha_version

    async def get_config(self) -> dict[str, Any]:
        return {"time_zone": self.time_zone, "version": self.ha_version}

    async def get_state(self, entity_id: str) -> dict[str, Any]:
        for state in self.states:
            if state.get("entity_id") == entity_id:
                return deepcopy(state)
        raise KeyError(f"Unknown digital-twin entity: {entity_id}")

    async def get_all_states(self) -> list[dict[str, Any]]:
        return deepcopy(self.states)

    async def get_entity_registry(self, entity_id: str) -> dict[str, Any] | None:
        registry = self.registries.get(entity_id)
        if registry is not None:
            return deepcopy(registry)
        return {
            "entity_id": entity_id,
            "unique_id": f"digital-twin::{entity_id}",
            "platform": "digital_twin",
        }

    async def get_history(self, entity_id: str, *_args, **_kwargs) -> list[dict[str, Any]]:
        return deepcopy(self.histories.get(entity_id, []))

    async def get_logbook(self, entity_id: str, *_args, **_kwargs) -> list[dict[str, Any]]:
        return deepcopy(self.logbooks.get(entity_id, []))

    async def list_traces(self, domain: str, item_id: str) -> list[dict[str, Any]]:
        return deepcopy(self.trace_summaries.get((domain, str(item_id)), []))

    async def get_trace(self, domain: str, item_id: str, run_id: str) -> dict[str, Any] | None:
        return deepcopy(self.trace_details.get((domain, str(item_id), str(run_id))))

    async def get_automation_config(self, item_id: str) -> dict[str, Any] | None:
        value = self.automation_configs.get(str(item_id))
        return deepcopy(value) if value is not None else None

    async def get_script_config(self, slug: str) -> dict[str, Any] | None:
        value = self.script_configs.get(str(slug))
        return deepcopy(value) if value is not None else None

    async def get_scene_config(self, slug: str) -> dict[str, Any] | None:
        value = self.scene_configs.get(str(slug))
        return deepcopy(value) if value is not None else None
