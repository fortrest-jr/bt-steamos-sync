from datetime import datetime
from pathlib import Path

import pytest
from conftest import (
    ADAPTER,
    HEADPHONES,
    KEYBOARD,
    FakeSudo,
    classic_info,
    le_info,
    make_store_tar,
)

from bt_steamos_sync import apply
from bt_steamos_sync.bluetooth_store import (
    LOCAL_STORE,
    StoreError,
    read_store,
    snapshot_from_tar,
)
from bt_steamos_sync.bluez_info import DeviceRecord
from bt_steamos_sync.plan import build_plan
from bt_steamos_sync.steamos import slot_state


@pytest.fixture
def state_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    return tmp_path


def test_snapshot_reads_devices_and_ignores_cache() -> None:
    archive = make_store_tar(
        {
            f"{ADAPTER}/{HEADPHONES}/info": classic_info("WH", "K"),
            f"{ADAPTER}/settings": "[General]\n",
            f"{ADAPTER}/cache/{KEYBOARD}": "[General]\nName=KB\n",
        }
    )
    snapshot = snapshot_from_tar(archive)
    assert snapshot.adapters == {ADAPTER}
    assert [d.address for d in snapshot.devices] == [HEADPHONES]


def test_snapshot_tracks_newest_record_time() -> None:
    archive = make_store_tar(
        {
            f"{ADAPTER}/{HEADPHONES}/info": classic_info("WH", "K"),
            f"{ADAPTER}/{KEYBOARD}/info": le_info("KB", "L", "I"),
        },
        mtimes={
            f"{ADAPTER}/{HEADPHONES}/info": 1_000_000,
            f"{ADAPTER}/{KEYBOARD}/info": 2_000_000,
        },
    )
    snapshot = snapshot_from_tar(archive)
    assert snapshot.newest_mtime[ADAPTER] == datetime.fromtimestamp(2_000_000)


def test_slot_state_uses_only_local_adapters() -> None:
    snapshot = snapshot_from_tar(
        make_store_tar({f"{ADAPTER}/{HEADPHONES}/info": classic_info("WH", "K")})
    )
    assert slot_state("var-A", None, snapshot, {ADAPTER}).has_adapter
    assert not slot_state("var-A", None, snapshot, {"11:11:11:11:11:11"}).has_adapter


def test_apply_backs_up_replaced_and_writes_source(
    state_home: Path,
    headphones_source: DeviceRecord,
    headphones_local_stale: DeviceRecord,
    keyboard_source: DeviceRecord,
) -> None:
    sudo = FakeSudo()
    plan = build_plan([headphones_source, keyboard_source], [headphones_local_stale])
    backup_dir = apply.apply_plan(
        sudo, plan, keys_only=False, now=datetime(2026, 11, 19, 15, 0)
    )  # type: ignore[arg-type]

    saved = backup_dir / ADAPTER / HEADPHONES / "info"
    assert saved.read_text() == headphones_local_stale.info_text, (
        "replaced record must be backed up"
    )
    assert not (backup_dir / ADAPTER / KEYBOARD).exists(), (
        "new records have nothing to back up"
    )
    assert (
        sudo.installed[f"/var/lib/bluetooth/{ADAPTER}/{HEADPHONES}/info"]
        == headphones_source.info_text
    )
    actions = {c.address: c.action for c in apply.read_manifest(backup_dir)}
    assert actions == {HEADPHONES: "replace", KEYBOARD: "add"}


def test_apply_keys_only_keeps_local_name(
    state_home: Path,
    headphones_source: DeviceRecord,
    headphones_local_stale: DeviceRecord,
) -> None:
    sudo = FakeSudo()
    plan = build_plan([headphones_source], [headphones_local_stale])
    apply.apply_plan(sudo, plan, keys_only=True, now=datetime(2026, 11, 19, 15, 0))  # type: ignore[arg-type]
    written = sudo.installed[f"/var/lib/bluetooth/{ADAPTER}/{HEADPHONES}/info"]
    assert "Name=Headphones" in written and "Key=AAAA" in written


def test_restore_puts_back_replaced_and_removes_added(
    state_home: Path,
    headphones_source: DeviceRecord,
    headphones_local_stale: DeviceRecord,
    keyboard_source: DeviceRecord,
) -> None:
    plan = build_plan([headphones_source, keyboard_source], [headphones_local_stale])
    backup_dir = apply.apply_plan(
        FakeSudo(), plan, keys_only=False, now=datetime(2026, 11, 19, 15, 0)
    )  # type: ignore[arg-type]

    sudo = FakeSudo()
    apply.restore_backup(sudo, backup_dir)  # type: ignore[arg-type]

    assert (
        sudo.installed[f"/var/lib/bluetooth/{ADAPTER}/{HEADPHONES}/info"]
        == headphones_local_stale.info_text
    )
    assert ["rm", "-r", "--", f"/var/lib/bluetooth/{ADAPTER}/{KEYBOARD}"] in sudo.calls


def test_list_backups_newest_first(
    state_home: Path, keyboard_source: DeviceRecord
) -> None:
    plan = build_plan([keyboard_source], [])
    for hour in (10, 12, 11):
        apply.apply_plan(
            FakeSudo(), plan, keys_only=False, now=datetime(2026, 11, 19, hour, 0)
        )  # type: ignore[arg-type]
    assert [p.name for p in apply.list_backups()] == [
        "20261119-120000",
        "20261119-110000",
        "20261119-100000",
    ]


@pytest.mark.parametrize("bad", ["..", "../etc", "AA:BB", ""])
def test_device_dir_rejects_non_mac_paths(bad: str) -> None:
    with pytest.raises(ValueError):
        apply.device_dir(ADAPTER, bad)


def test_read_store_returns_empty_snapshot_when_directory_is_missing() -> None:
    sudo = FakeSudo(existing_directories=False)
    snapshot = read_store(sudo, LOCAL_STORE)  # type: ignore[arg-type]
    assert snapshot.adapters == set() and snapshot.devices == []
    assert not any(call[0] == "tar" for call in sudo.calls), (
        "tar must not run for a missing store"
    )


def test_corrupted_archive_raises_store_error() -> None:
    with pytest.raises(StoreError):
        snapshot_from_tar(b"not a tar archive")


@pytest.mark.parametrize("content", ["{broken", "[1, 2]", '[{"unexpected": 1}]'])
def test_unreadable_manifest_raises_backup_error(tmp_path: Path, content: str) -> None:
    (tmp_path / apply.MANIFEST).write_text(content)
    with pytest.raises(apply.BackupError):
        apply.read_manifest(tmp_path)


def test_restore_without_saved_record_raises_backup_error(
    state_home: Path,
    headphones_source: DeviceRecord,
    headphones_local_stale: DeviceRecord,
) -> None:
    plan = build_plan([headphones_source], [headphones_local_stale])
    backup_dir = apply.apply_plan(
        FakeSudo(),  # type: ignore[arg-type]
        plan,
        keys_only=False,
        now=datetime(2026, 11, 19, 15, 0),
    )
    (backup_dir / ADAPTER / HEADPHONES / "info").unlink()
    with pytest.raises(apply.BackupError):
        apply.restore_backup(FakeSudo(), backup_dir)  # type: ignore[arg-type]
