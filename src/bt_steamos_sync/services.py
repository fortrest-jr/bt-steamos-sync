import shutil
import subprocess
import time
from collections.abc import Generator
from contextlib import contextmanager

from bt_steamos_sync.privileged import Sudo

BLUEMAN_APPLET = "blueman-applet"
BLUEMAN_PATTERN = rf"(^|/){BLUEMAN_APPLET}( |$)"
SETTLE_SECONDS = 3.0


def blueman_applet_running() -> bool:
    return (
        subprocess.run(
            ["pgrep", "-f", BLUEMAN_PATTERN], capture_output=True, check=False
        ).returncode
        == 0
    )


def stop_blueman_applet() -> None:
    subprocess.run(["pkill", "-f", BLUEMAN_PATTERN], check=False)
    for _ in range(20):
        if not blueman_applet_running():
            return
        time.sleep(0.1)


def start_blueman_applet() -> None:
    executable = shutil.which(BLUEMAN_APPLET)
    if executable is None:
        return
    subprocess.Popen(
        [executable],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def known_devices() -> set[str]:
    output = subprocess.run(
        ["bluetoothctl", "devices"], capture_output=True, text=True, check=False
    ).stdout
    return {
        line.split()[1] for line in output.splitlines() if line.startswith("Device ")
    }


@contextmanager
def blueman_paused(enabled: bool) -> Generator[None]:
    pause = enabled and blueman_applet_running()
    if pause:
        stop_blueman_applet()
    try:
        yield
    finally:
        if pause:
            start_blueman_applet()


@contextmanager
def bluetooth_stopped(sudo: Sudo, manage_blueman: bool) -> Generator[None]:
    with blueman_paused(manage_blueman):
        sudo.run(["systemctl", "stop", "bluetooth"])
        try:
            yield
        finally:
            sudo.run(["systemctl", "start", "bluetooth"])
            time.sleep(SETTLE_SECONDS)
