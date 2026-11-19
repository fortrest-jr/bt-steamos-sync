import subprocess
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path, PurePosixPath

from bt_steamos_sync.bluetooth_store import StoreSnapshot, read_store
from bt_steamos_sync.privileged import Sudo
from bt_steamos_sync.slots import SlotState, parse_last_mount_time

SLOT_LABELS = ("var-A", "var-B")
BLUETOOTH_IN_VAR = "lib/bluetooth"


def partition_path(label: str) -> Path:
    return Path("/dev/disk/by-partlabel") / label


def existing_mountpoint(device: Path) -> PurePosixPath | None:
    result = subprocess.run(
        ["findmnt", "-n", "-o", "TARGET", "--source", str(device.resolve())],
        capture_output=True,
        text=True,
        check=False,
    )
    targets = result.stdout.split()
    return PurePosixPath(targets[0]) if targets else None


@contextmanager
def readonly_mount(sudo: Sudo, device: Path) -> Generator[PurePosixPath]:
    if (mounted := existing_mountpoint(device)) is not None:
        yield mounted
        return
    with tempfile.TemporaryDirectory(prefix="bt-sync-") as mountpoint:
        sudo.run(["mount", "-o", "ro,noload", str(device), mountpoint])
        try:
            yield PurePosixPath(mountpoint)
        finally:
            sudo.run(["umount", mountpoint])


def slot_state(
    label: str,
    last_mount: datetime | None,
    snapshot: StoreSnapshot,
    local_adapters: set[str],
) -> SlotState:
    shared = snapshot.adapters & local_adapters
    record_times = [
        snapshot.newest_mtime[a] for a in shared if a in snapshot.newest_mtime
    ]
    return SlotState(
        label=label,
        last_mount=last_mount,
        newest_record=max(record_times, default=None),
        has_adapter=bool(shared),
    )


def read_slot(
    sudo: Sudo, label: str, local_adapters: set[str]
) -> tuple[SlotState, StoreSnapshot]:
    device = partition_path(label)
    header = sudo.run(["dumpe2fs", "-h", str(device)]).decode(errors="replace")
    with readonly_mount(sudo, device) as root:
        snapshot = read_store(sudo, root / BLUETOOTH_IN_VAR)
    return slot_state(
        label, parse_last_mount_time(header), snapshot, local_adapters
    ), snapshot


def available_slots() -> list[str]:
    return [label for label in SLOT_LABELS if partition_path(label).exists()]
