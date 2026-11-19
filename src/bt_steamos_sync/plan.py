from dataclasses import dataclass
from enum import Enum

from bt_steamos_sync.bluez_info import DeviceRecord, same_keys


class Change(Enum):
    NEW = "new"
    REPLACE = "replace"
    SAME = "same"


@dataclass(frozen=True)
class PlanItem:
    source: DeviceRecord
    local: DeviceRecord | None
    change: Change

    @property
    def selected_by_default(self) -> bool:
        return self.change is not Change.SAME


def classify(source: DeviceRecord, local: DeviceRecord | None) -> Change:
    if local is None:
        return Change.NEW
    if same_keys(source.info_text, local.info_text):
        return Change.SAME
    return Change.REPLACE


def build_plan(source: list[DeviceRecord], local: list[DeviceRecord]) -> list[PlanItem]:
    local_by_key = {(record.adapter, record.address): record for record in local}
    items = []
    for record in sorted(source, key=lambda r: (r.adapter, r.name.lower())):
        match = local_by_key.get((record.adapter, record.address))
        items.append(PlanItem(record, match, classify(record, match)))
    return items
