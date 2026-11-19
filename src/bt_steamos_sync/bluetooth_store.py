import io
import re
import tarfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath

from bt_steamos_sync.bluez_info import DeviceRecord
from bt_steamos_sync.errors import BtSyncError
from bt_steamos_sync.privileged import Sudo

LOCAL_STORE = PurePosixPath("/var/lib/bluetooth")
MAC_PATTERN = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")


class StoreError(BtSyncError):
    pass


@dataclass(frozen=True)
class StoreSnapshot:
    adapters: set[str]
    devices: list[DeviceRecord]
    newest_mtime: dict[str, datetime]


def is_mac(value: str) -> bool:
    return bool(MAC_PATTERN.match(value))


def device_info_path(member_name: str) -> tuple[str, str] | None:
    parts = PurePosixPath(member_name).parts
    parts = parts[1:] if parts and parts[0] == "." else parts
    if len(parts) == 3 and parts[2] == "info" and is_mac(parts[0]) and is_mac(parts[1]):
        return parts[0], parts[1]
    return None


def adapter_dir(member_name: str) -> str | None:
    parts = [part for part in PurePosixPath(member_name).parts if part != "."]
    return parts[0] if len(parts) == 1 and is_mac(parts[0]) else None


def snapshot_from_tar(archive: bytes) -> StoreSnapshot:
    try:
        return _snapshot_from_valid_tar(archive)
    except tarfile.TarError as error:
        raise StoreError(f"cannot read Bluetooth store archive: {error}") from error


def _snapshot_from_valid_tar(archive: bytes) -> StoreSnapshot:
    adapters: set[str] = set()
    devices: list[DeviceRecord] = []
    newest: dict[str, datetime] = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            if member.isdir() and (adapter := adapter_dir(member.name)):
                adapters.add(adapter)
            location = device_info_path(member.name) if member.isfile() else None
            if location is None:
                continue
            adapter, address = location
            text = tar.extractfile(member).read().decode()  # type: ignore[union-attr]
            devices.append(DeviceRecord(adapter, address, text))
            mtime = datetime.fromtimestamp(member.mtime)
            newest[adapter] = max(newest.get(adapter, mtime), mtime)
    return StoreSnapshot(adapters, devices, newest)


def read_store(sudo: Sudo, store: PurePosixPath) -> StoreSnapshot:
    if not sudo.succeeds(["test", "-d", str(store)]):
        return StoreSnapshot(set(), [], {})
    return snapshot_from_tar(sudo.run(["tar", "-C", str(store), "-cf", "-", "."]))
