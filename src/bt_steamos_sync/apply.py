import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath

from bt_steamos_sync.bluetooth_store import LOCAL_STORE, is_mac
from bt_steamos_sync.bluez_info import replace_keys
from bt_steamos_sync.errors import BtSyncError
from bt_steamos_sync.plan import Change, PlanItem
from bt_steamos_sync.privileged import Sudo

MANIFEST = "manifest.json"


class BackupError(BtSyncError):
    pass


@dataclass(frozen=True)
class AppliedChange:
    adapter: str
    address: str
    name: str
    action: str


def backups_root() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state"
    return Path(state_home) / "bt-sync"


def device_dir(adapter: str, address: str) -> PurePosixPath:
    if not (is_mac(adapter) and is_mac(address)):
        raise ValueError(f"not a Bluetooth address: {adapter}/{address}")
    return LOCAL_STORE / adapter / address


def text_to_install(item: PlanItem, keys_only: bool) -> str:
    if keys_only and item.local is not None:
        return replace_keys(item.local.info_text, item.source.info_text)
    return item.source.info_text


def install_info(sudo: Sudo, adapter: str, address: str, text: str) -> None:
    target_dir = device_dir(adapter, address)
    sudo.run(
        ["install", "-d", "-m", "700", "-o", "root", "-g", "root", str(target_dir)]
    )
    with tempfile.NamedTemporaryFile(
        "w", prefix="bt-sync-", delete_on_close=False
    ) as staged:
        staged.write(text)
        staged.close()
        sudo.run(
            [
                "install",
                "-m",
                "600",
                "-o",
                "root",
                "-g",
                "root",
                staged.name,
                str(target_dir / "info"),
            ]
        )


def save_backup(backup_dir: Path, item: PlanItem) -> None:
    assert item.local is not None
    target = backup_dir / item.local.adapter / item.local.address / "info"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(item.local.info_text)
    target.chmod(0o600)


def write_manifest(backup_dir: Path, changes: list[AppliedChange]) -> None:
    (backup_dir / MANIFEST).write_text(
        json.dumps([asdict(c) for c in changes], indent=2)
    )


def apply_plan(
    sudo: Sudo, items: list[PlanItem], keys_only: bool, now: datetime
) -> Path:
    backup_dir = backups_root() / now.strftime("%Y%m%d-%H%M%S")
    backup_dir.mkdir(parents=True, mode=0o700)
    changes: list[AppliedChange] = []
    for item in items:
        if item.change is Change.REPLACE:
            save_backup(backup_dir, item)
        action = "add" if item.local is None else "replace"
        install_info(
            sudo,
            item.source.adapter,
            item.source.address,
            text_to_install(item, keys_only),
        )
        changes.append(
            AppliedChange(
                item.source.adapter, item.source.address, item.source.name, action
            )
        )
        write_manifest(backup_dir, changes)
    return backup_dir


def list_backups() -> list[Path]:
    root = backups_root()
    return (
        sorted((p for p in root.iterdir() if (p / MANIFEST).exists()), reverse=True)
        if root.exists()
        else []
    )


def read_manifest(backup_dir: Path) -> list[AppliedChange]:
    try:
        entries = json.loads((backup_dir / MANIFEST).read_text())
        return [AppliedChange(**entry) for entry in entries]
    except (OSError, ValueError, TypeError) as error:
        raise BackupError(
            f"backup {backup_dir.name} has an unreadable manifest: {error}"
        ) from error


def read_saved_info(backup_dir: Path, change: AppliedChange) -> str:
    try:
        return (backup_dir / change.adapter / change.address / "info").read_text()
    except OSError as error:
        raise BackupError(
            f"backup {backup_dir.name} has no saved record for {change.address}: {error}"
        ) from error


def restore_backup(sudo: Sudo, backup_dir: Path) -> list[AppliedChange]:
    changes = read_manifest(backup_dir)
    for change in changes:
        if change.action == "replace":
            saved = read_saved_info(backup_dir, change)
            install_info(sudo, change.adapter, change.address, saved)
        else:
            sudo.run(
                ["rm", "-r", "--", str(device_dir(change.adapter, change.address))]
            )
    return changes
