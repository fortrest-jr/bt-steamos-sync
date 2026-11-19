from dataclasses import dataclass
from datetime import datetime

DUMPE2FS_TIME_FORMAT = "%a %b %d %H:%M:%S %Y"


@dataclass(frozen=True)
class SlotState:
    label: str
    last_mount: datetime | None
    newest_record: datetime | None
    has_adapter: bool


@dataclass(frozen=True)
class SlotChoice:
    slot: SlotState | None
    reason: str
    needs_confirmation: bool


def parse_last_mount_time(dumpe2fs_header: str) -> datetime | None:
    for line in dumpe2fs_header.splitlines():
        field, _, value = line.partition(":")
        if field.strip() == "Last mount time":
            return _parse_ctime(value.strip())
    return None


def _parse_ctime(value: str) -> datetime | None:
    try:
        return datetime.strptime(" ".join(value.split()), DUMPE2FS_TIME_FORMAT)
    except ValueError:
        return None


def _latest(slots: list[SlotState], marker: str) -> SlotState | None:
    dated = [slot for slot in slots if getattr(slot, marker) is not None]
    return max(dated, key=lambda slot: getattr(slot, marker)) if dated else None


def choose_slot(slots: list[SlotState]) -> SlotChoice:
    usable = [slot for slot in slots if slot.has_adapter]
    if not usable:
        return SlotChoice(
            None, "no slot has pairings for this adapter", needs_confirmation=False
        )
    if len(usable) == 1:
        return SlotChoice(
            usable[0],
            "only slot with pairings for this adapter",
            needs_confirmation=False,
        )

    by_mount = _latest(usable, "last_mount")
    by_records = _latest(usable, "newest_record")
    if by_mount is not None and by_mount == by_records:
        return SlotChoice(
            by_mount,
            "mounted last and has the newest pairings",
            needs_confirmation=False,
        )
    if by_mount is None and by_records is None:
        return SlotChoice(usable[0], "no marker is available", needs_confirmation=True)
    if by_mount is None or by_records is None:
        guess = by_mount or by_records
        return SlotChoice(
            guess, "only one marker is available", needs_confirmation=True
        )
    return SlotChoice(
        by_mount,
        "markers disagree: mount time vs newest pairings",
        needs_confirmation=True,
    )
