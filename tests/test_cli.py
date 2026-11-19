from pathlib import Path

import pytest
from conftest import ADAPTER, HEADPHONES, FakeSudo, classic_info

from bt_steamos_sync import cli, services
from bt_steamos_sync.bluetooth_store import StoreSnapshot
from bt_steamos_sync.bluez_info import DeviceRecord
from bt_steamos_sync.slots import SlotState


@pytest.fixture
def state_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def no_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(services, "SETTLE_SECONDS", 0)
    monkeypatch.setattr(services, "blueman_applet_running", lambda: False)
    monkeypatch.setattr(cli, "known_devices", lambda: {HEADPHONES})


def stub_stores(
    monkeypatch: pytest.MonkeyPatch, source_devices: list[DeviceRecord]
) -> None:
    local = StoreSnapshot({ADAPTER}, [], {})
    source = StoreSnapshot({ADAPTER}, source_devices, {})
    state = SlotState("var-A", None, None, has_adapter=True)
    monkeypatch.setattr(cli, "read_store", lambda sudo, store: local)
    monkeypatch.setattr(
        cli, "read_slots", lambda sudo, adapters: {"var-A": (state, source)}
    )


def test_cli_refuses_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)
    with pytest.raises(SystemExit) as exit_info:
        cli.refuse_root()
    assert "normal user" in str(exit_info.value.code)


@pytest.mark.parametrize("argv", [[], ["--dry-run"]])
def test_empty_plan_exits_with_message(
    monkeypatch: pytest.MonkeyPatch, argv: list[str]
) -> None:
    stub_stores(monkeypatch, source_devices=[])
    with pytest.raises(SystemExit) as exit_info:
        cli.run_sync(cli.parse_args(argv), FakeSudo())  # type: ignore[arg-type]
    assert "Nothing to copy" in str(exit_info.value.code)


def test_sync_reauthenticates_and_writes_while_bluetooth_is_stopped(
    monkeypatch: pytest.MonkeyPatch, state_home: Path, no_side_effects: None
) -> None:
    device = DeviceRecord(ADAPTER, HEADPHONES, classic_info("Headphones", "AAAA"))
    stub_stores(monkeypatch, source_devices=[device])
    monkeypatch.setattr(cli.ui, "select_items", lambda plan: plan)
    monkeypatch.setattr(cli.ui, "confirm_apply", lambda items: True)
    sudo = FakeSudo()

    cli.run_sync(cli.parse_args([]), sudo)  # type: ignore[arg-type]

    steps = [
        "authenticate" if call == ["authenticate"] else " ".join(call[:3])
        for call in sudo.calls
    ]
    stop = steps.index("systemctl stop bluetooth")
    start = steps.index("systemctl start bluetooth")
    writes = [index for index, step in enumerate(steps) if step.startswith("install")]
    assert steps[stop - 1] == "authenticate", (
        f"sudo must be re-checked right before writing: {steps}"
    )
    assert writes and all(stop < index < start for index in writes), (
        f"records must be written while bluetooth is stopped: {steps}"
    )


def test_bluetooth_is_started_again_when_writing_fails(
    no_side_effects: None,
) -> None:
    sudo = FakeSudo()
    stopped = services.bluetooth_stopped(sudo, manage_blueman=False)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError), stopped:
        raise RuntimeError("write failed")
    assert sudo.calls[-1] == ["systemctl", "start", "bluetooth"]
