from __future__ import annotations

from typing import Any

from causal_recorder import CausalRecord
from causal_utils import nodes, walk_contains
from targeted_memory_enricher_dev37 import _technical_reason
from targeted_memory_enricher_dev44 import TargetedMemoryEnricher as Dev44TargetedMemoryEnricher


class TargetedMemoryEnricher(Dev44TargetedMemoryEnricher):
    """Dev.45: keep cover episode causality when the trace proves a target command.

    Some cover automations compute the target position inside Jinja variables. The
    existing semantic cause selectors can then legitimately return no human reason
    even though the executed trace proves one unique ``cover.set_cover_position``
    command for the moving cover. Dev.45 keeps that proof as a conservative fallback:
    it never interprets the Jinja business rule and never invents which input was
    decisive. It only states the proven calculated target, then normal episode
    propagation can carry the source to the terminal state/current_position.
    """

    async def _nearest_source_detail(self, source: CausalRecord) -> tuple[dict[str, Any] | None, str | None]:
        bundle = None
        try:
            bundle = await self.trace_investigator._best_trace_for_source(
                source.source_entity_id, source.normalized_time()
            )
            self.trace_reads += 1
        except Exception:
            self.direct_trace_failures += 1

        if isinstance(bundle, dict) and isinstance(bundle.get("detail"), dict):
            detail = bundle["detail"]
            summary = bundle.get("summary") if isinstance(bundle.get("summary"), dict) else {}
            run_id = summary.get("run_id") or summary.get("id") or detail.get("run_id") or detail.get("id")
            self.last_trace_backend = "direct_ha"
            return detail, str(run_id) if run_id else None

        reader = self.mcp_trace_reader
        if reader is not None and source.source_entity_id:
            detail = await reader.nearest_detail(
                source.source_entity_id, source.normalized_time(), source.entity_id
            )
            if isinstance(detail, dict):
                self.last_trace_backend = "ha_mcp"
                run_id = detail.get("run_id") or detail.get("id")
                return detail, str(run_id) if run_id else None
        return None, None

    @staticmethod
    def _unique_set_position(detail: dict[str, Any], entity_id: str) -> dict[str, Any] | None:
        trace = detail.get("trace")
        if not isinstance(trace, dict):
            return None
        matches: list[dict[str, Any]] = []
        for path, raw_nodes in trace.items():
            if not str(path).startswith("action/"):
                continue
            for node in nodes(raw_nodes):
                result = node.get("result")
                params = result.get("params") if isinstance(result, dict) else None
                if not isinstance(params, dict):
                    continue
                if params.get("domain") != "cover" or params.get("service") != "set_cover_position":
                    continue
                if not walk_contains(params.get("target"), entity_id):
                    continue
                data = params.get("service_data") or params.get("data")
                position = data.get("position") if isinstance(data, dict) else None
                try:
                    position_num = float(position)
                except (TypeError, ValueError):
                    continue
                matches.append({"path": str(path), "position": position_num})
                break
        unique = {(item["path"], item["position"]) for item in matches}
        if len(unique) != 1:
            return None
        path, position = next(iter(unique))
        return {"path": path, "position": position}

    async def _recover_proven_target_reason(self, source: CausalRecord) -> CausalRecord | None:
        if (
            source.origin_type not in {"automation", "script"}
            or not source.source_entity_id
            or not source.entity_id.startswith("cover.")
        ):
            return None
        if source.reason and not _technical_reason(source.reason):
            return source

        detail, run_id = await self._nearest_source_detail(source)
        if not isinstance(detail, dict):
            return None
        command = self._unique_set_position(detail, source.entity_id)
        if command is None:
            return None

        current = self.recorder.get(source.record_id) if source.record_id is not None else None
        if current is None:
            return None
        position = command["position"]
        shown = str(int(position)) if float(position).is_integer() else str(position).replace(".", ",")
        current.reason = f"l'automatisation a calculé une position cible de {shown} % à partir de ses conditions"
        current.reason_code = "cover_episode_proven_set_position_target"
        current.trace_run_id = run_id or current.trace_run_id
        proof = dict(current.trigger) if isinstance(current.trigger, dict) else {}
        proof["effect_command"] = {
            "path": command["path"],
            "domain": "cover",
            "service": "set_cover_position",
            "position": position,
            "proven": True,
        }
        if self.last_trace_backend:
            proof["trace_backend"] = self.last_trace_backend
        current.trigger = proof
        current.factors = current.factors or [
            {
                "kind": "automation_target",
                "role": "cause",
                "proven": True,
                "relation": "target_position",
                "actual": position,
                "unit": "%",
                "label": "position cible calculée",
            }
        ]
        current.confidence = "confirmed"
        self.recorder.update(current)
        return current

    async def enrich(self, records: list[CausalRecord]) -> bool:
        records = [record for record in records if record.record_id is not None]
        if not records:
            return False
        primaries = [record for record in records if record.attribute is None]
        anchor = max(primaries or records, key=lambda item: item.normalized_time())
        start = self._raw_cover_episode_start(anchor) if anchor.attribute is None else None

        if start is not None:
            if start.origin_type == "unknown":
                await super().enrich([start])
            current_start = self.recorder.get(start.record_id) if start.record_id is not None else None
            if current_start is not None and current_start.origin_type in {"automation", "script"} and (
                not current_start.reason or _technical_reason(current_start.reason)
            ):
                await self._recover_proven_target_reason(current_start)

        return await super().enrich(records)
