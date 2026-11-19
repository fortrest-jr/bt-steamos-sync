import subprocess
from collections.abc import Sequence

from bt_steamos_sync.errors import BtSyncError


class SudoError(BtSyncError):
    pass


class Sudo:
    def authenticate(self) -> None:
        try:
            authenticated = subprocess.run(["sudo", "-v"], check=False).returncode == 0
        except FileNotFoundError as error:
            raise SudoError("sudo is not installed") from error
        if not authenticated:
            raise SudoError("sudo authentication failed")

    def succeeds(self, args: Sequence[str]) -> bool:
        result = subprocess.run(["sudo", "-n", *args], capture_output=True, check=False)
        return result.returncode == 0

    def run(self, args: Sequence[str], stdin: bytes | None = None) -> bytes:
        result = subprocess.run(
            ["sudo", "-n", "env", "LC_ALL=C", *args],
            input=stdin,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            message = result.stderr.decode(errors="replace").strip()
            raise SudoError(f"{' '.join(args)}: {message}")
        return result.stdout
