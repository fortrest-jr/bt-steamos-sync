import io
import tarfile
import time
from pathlib import Path

import pytest

from bt_steamos_sync.bluez_info import DeviceRecord

ADAPTER = "00:11:22:33:44:55"
HEADPHONES = "AA:BB:CC:DD:EE:01"
KEYBOARD = "AA:BB:CC:DD:EE:02"


def classic_info(name: str, link_key: str) -> str:
    return (
        "[General]\n"
        f"Name={name}\n"
        "SupportedTechnologies=BR/EDR;\n"
        "Trusted=true\n"
        "\n"
        "[LinkKey]\n"
        f"Key={link_key}\n"
        "Type=4\n"
        "PINLength=0\n"
    )


def le_info(name: str, ltk: str, irk: str) -> str:
    return (
        "[General]\n"
        f"Name={name}\n"
        "AddressType=static\n"
        "SupportedTechnologies=LE;\n"
        "\n"
        "[IdentityResolvingKey]\n"
        f"Key={irk}\n"
        "\n"
        "[LongTermKey]\n"
        f"Key={ltk}\n"
        "Authenticated=0\n"
        "EncSize=16\n"
        "EDiv=1234\n"
        "Rand=5678\n"
        "\n"
        "[ConnectionParameters]\n"
        "MinInterval=6\n"
    )


@pytest.fixture
def headphones_source() -> DeviceRecord:
    return DeviceRecord(ADAPTER, HEADPHONES, classic_info("LE_Headphones", "AAAA"))


@pytest.fixture
def headphones_local_stale() -> DeviceRecord:
    return DeviceRecord(ADAPTER, HEADPHONES, classic_info("Headphones", "BBBB"))


@pytest.fixture
def keyboard_source() -> DeviceRecord:
    return DeviceRecord(ADAPTER, KEYBOARD, le_info("Keyboard", "1111", "2222"))


def make_store_tar(
    files: dict[str, str], mtimes: dict[str, float] | None = None
) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        seen_dirs: set[str] = set()
        for path, text in files.items():
            for depth in range(1, len(path.split("/"))):
                directory = "./" + "/".join(path.split("/")[:depth])
                if directory not in seen_dirs:
                    seen_dirs.add(directory)
                    info = tarfile.TarInfo(directory)
                    info.type = tarfile.DIRTYPE
                    tar.addfile(info)
            data = text.encode()
            info = tarfile.TarInfo("./" + path)
            info.size = len(data)
            info.mtime = (mtimes or {}).get(path, time.time())
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


class FakeSudo:
    def __init__(self, existing_directories: bool = True) -> None:
        self.calls: list[list[str]] = []
        self.installed: dict[str, str] = {}
        self.authentications = 0
        self.existing_directories = existing_directories

    def authenticate(self) -> None:
        self.authentications += 1
        self.calls.append(["authenticate"])

    def succeeds(self, args: list[str]) -> bool:
        return self.existing_directories

    def run(self, args: list[str], stdin: bytes | None = None) -> bytes:
        self.calls.append(list(args))
        if args[0] == "install" and args[1] == "-m":
            self.installed[args[-1]] = Path(args[-2]).read_text()
        return b""
