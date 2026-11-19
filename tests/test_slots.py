from datetime import datetime

import pytest

from bt_steamos_sync.slots import SlotState, choose_slot, parse_last_mount_time

EARLY = datetime(2026, 10, 10, 0, 0)
LATE = datetime(2026, 11, 19, 14, 0)


def slot(
    label: str,
    mount: datetime | None,
    record: datetime | None,
    has_adapter: bool = True,
) -> SlotState:
    return SlotState(label, mount, record, has_adapter)


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (
            "Last mount time:          Wed Nov 19 14:03:12 2026",
            datetime(2026, 11, 19, 14, 3, 12),
        ),
        (
            "Last mount time:          Fri Oct  9 23:59:01 2026",
            datetime(2026, 10, 9, 23, 59, 1),
        ),
        ("Last mount time:          n/a", None),
    ],
)
def test_parse_last_mount_time(line: str, expected: datetime | None) -> None:
    header = f"Filesystem volume name:   var\n{line}\nLast write time:          Wed Nov 19 14:03:12 2026\n"
    assert parse_last_mount_time(header) == expected


def test_parse_last_mount_time_missing_field() -> None:
    assert parse_last_mount_time("Filesystem volume name:   var\n") is None


def test_agreeing_markers_pick_slot_without_question() -> None:
    choice = choose_slot([slot("var-A", LATE, LATE), slot("var-B", EARLY, EARLY)])
    assert choice.slot is not None and choice.slot.label == "var-A"
    assert not choice.needs_confirmation


def test_disagreeing_markers_ask_and_suggest_mount_time() -> None:
    choice = choose_slot([slot("var-A", LATE, EARLY), slot("var-B", EARLY, LATE)])
    assert choice.needs_confirmation
    assert choice.slot is not None and choice.slot.label == "var-A", (
        "mount time is the primary marker"
    )


def test_missing_marker_asks() -> None:
    choice = choose_slot([slot("var-A", None, LATE), slot("var-B", None, EARLY)])
    assert choice.needs_confirmation
    assert choice.slot is not None and choice.slot.label == "var-A"


def test_no_markers_at_all_still_asks() -> None:
    choice = choose_slot([slot("var-A", None, None), slot("var-B", None, None)])
    assert choice.needs_confirmation
    assert choice.slot is not None, "usable slots must stay selectable without markers"


def test_slot_without_adapter_is_ignored() -> None:
    choice = choose_slot(
        [slot("var-A", LATE, LATE, has_adapter=False), slot("var-B", EARLY, EARLY)]
    )
    assert choice.slot is not None and choice.slot.label == "var-B"
    assert not choice.needs_confirmation


def test_no_usable_slot() -> None:
    choice = choose_slot([slot("var-A", LATE, LATE, has_adapter=False)])
    assert choice.slot is None
