from conftest import ADAPTER, classic_info

from bt_steamos_sync.bluez_info import DeviceRecord
from bt_steamos_sync.plan import Change, build_plan, classify


def test_new_device_is_selected(keyboard_source: DeviceRecord) -> None:
    [item] = build_plan([keyboard_source], [])
    assert item.change is Change.NEW
    assert item.selected_by_default


def test_changed_keys_mean_replace(
    headphones_source: DeviceRecord, headphones_local_stale: DeviceRecord
) -> None:
    [item] = build_plan([headphones_source], [headphones_local_stale])
    assert item.change is Change.REPLACE
    assert item.local == headphones_local_stale
    assert item.selected_by_default


def test_same_keys_are_not_selected(headphones_source: DeviceRecord) -> None:
    renamed = DeviceRecord(
        ADAPTER, headphones_source.address, classic_info("Other name", "AAAA")
    )
    [item] = build_plan([headphones_source], [renamed])
    assert item.change is Change.SAME
    assert not item.selected_by_default


def test_local_only_devices_are_not_in_plan(
    keyboard_source: DeviceRecord, headphones_local_stale: DeviceRecord
) -> None:
    plan = build_plan([keyboard_source], [headphones_local_stale])
    assert [item.source.address for item in plan] == [keyboard_source.address]


def test_same_address_on_other_adapter_is_new(headphones_source: DeviceRecord) -> None:
    other_adapter = DeviceRecord(
        "11:11:11:11:11:11", headphones_source.address, headphones_source.info_text
    )
    assert classify(headphones_source, None) is Change.NEW
    [item] = build_plan([headphones_source], [other_adapter])
    assert item.change is Change.NEW
