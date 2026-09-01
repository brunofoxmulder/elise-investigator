from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_recorder import CausalRecord
from targeted_memory_enricher_dev45 import TargetedMemoryEnricher as Dev45TargetedMemoryEnricher
from targeted_memory_enricher_dev48 import TargetedMemoryEnricher


class FakeRecorder:
    def __init__(self, records):
        self.records = {record.record_id: record for record in records}

    def get(self, record_id):
        return self.records.get(record_id)


def causal_record(
    *,
    entity_id="light.salon",
    event_kind="turned_on",
    before="off",
    after="on",
    attribute=None,
    origin_type="automation",
    source_entity_id="automation.ambiance_du_soir",
    reason=None,
):
    return CausalRecord(
        record_id=1,
        entity_id=entity_id,
        entity_name=entity_id,
        event_time="2026-09-01T18:00:00+00:00",
        event_kind=event_kind,
        before_value=before,
        after_value=after,
        attribute=attribute,
        origin_type=origin_type,
        source_entity_id=source_entity_id,
        source_name="Ambiance du soir",
        reason=reason,
        confidence="confirmed",
    )


class TestDev48DelayedPrimaryReasonRetry(unittest.IsolatedAsyncioTestCase):
    async def _enricher(self, record):
        enricher = object.__new__(TargetedMemoryEnricher)
        enricher.recorder = FakeRecorder([record])
        return enricher

    async def test_unresolved_primary_automation_on_transition_retries_once(self):
        record = causal_record()
        enricher = await self._enricher(record)

        with patch.object(
            Dev45TargetedMemoryEnricher,
            "enrich",
            new=AsyncMock(side_effect=[True, True]),
        ) as parent_enrich, patch(
            "targeted_memory_enricher_dev48.asyncio.sleep", new=AsyncMock()
        ) as sleep:
            changed = await enricher.enrich([record])

        self.assertTrue(changed)
        self.assertEqual(parent_enrich.await_count, 2)
        sleep.assert_awaited_once()

    async def test_existing_reason_does_not_retry(self):
        record = causal_record(reason="sunset")
        enricher = await self._enricher(record)

        with patch.object(
            Dev45TargetedMemoryEnricher, "enrich", new=AsyncMock(return_value=True)
        ) as parent_enrich, patch(
            "targeted_memory_enricher_dev48.asyncio.sleep", new=AsyncMock()
        ) as sleep:
            await enricher.enrich([record])

        self.assertEqual(parent_enrich.await_count, 1)
        sleep.assert_not_awaited()

    async def test_cover_never_uses_dev48_retry(self):
        record = causal_record(
            entity_id="cover.volet_salon_2",
            event_kind="closed",
            before="closing",
            after="closed",
        )
        enricher = await self._enricher(record)

        with patch.object(
            Dev45TargetedMemoryEnricher, "enrich", new=AsyncMock(return_value=False)
        ) as parent_enrich, patch(
            "targeted_memory_enricher_dev48.asyncio.sleep", new=AsyncMock()
        ) as sleep:
            await enricher.enrich([record])

        self.assertEqual(parent_enrich.await_count, 1)
        sleep.assert_not_awaited()

    async def test_brightness_attribute_never_uses_dev48_retry(self):
        record = causal_record(
            event_kind="brightness_changed",
            before=10,
            after=80,
            attribute="brightness",
        )
        enricher = await self._enricher(record)

        with patch.object(
            Dev45TargetedMemoryEnricher, "enrich", new=AsyncMock(return_value=False)
        ) as parent_enrich, patch(
            "targeted_memory_enricher_dev48.asyncio.sleep", new=AsyncMock()
        ) as sleep:
            await enricher.enrich([record])

        self.assertEqual(parent_enrich.await_count, 1)
        sleep.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
