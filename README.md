# bt-steamos-sync

**English** | [Русский](README.ru.md)

`bt-sync` copies Bluetooth pairings from SteamOS to a second Linux install on the same Steam Deck (dual-boot). Devices paired in SteamOS then work in the second system too, without pairing again.

## Why

Both systems share one Bluetooth adapter with one address. But each system creates its own key when pairing, and a device (headphones, keyboard, mouse) remembers only the latest key for that address. As a result:

- pair headphones in SteamOS — they no longer connect in Mint;
- pair them again in Mint — they stop connecting in SteamOS.

The fix is to pair devices only in SteamOS and copy the same keys to the second system. Both systems then look identical to the device, and you can switch systems without re-pairing.

`bt-sync` does this copy: it reads BlueZ records from SteamOS (`/var/lib/bluetooth/<adapter>/<device>/info`) and writes them to the local `/var/lib/bluetooth`.

There are no ready-made tools for SteamOS → Linux: existing ones only move keys between Windows and Linux.

## Install

Requires [uv](https://docs.astral.sh/uv/) and `sudo`; Python 3.12+ is fetched by uv if missing.

```bash
uv tool install git+https://github.com/fortrest-jr/bt-steamos-sync
```

The `bt-sync` command lands in `~/.local/bin`. Update with `uv tool upgrade bt-steamos-sync`, remove with `uv tool uninstall bt-steamos-sync`.

## Usage

```bash
bt-sync            # pick devices in a list, then copy
bt-sync --dry-run  # only show what would change
bt-sync restore    # undo one of the earlier syncs
```

Run it as your normal user: it asks for the sudo password at start (reading needs root) and checks sudo again right before writing, so a long pause in the list does not break the write. `restore` asks only before writing. It refuses to run as root.

Options:

| Option | What it does |
|---|---|
| `--dry-run` | reads partitions and prints the plan, changes nothing |
| `--keys-only` | replaces only key sections, keeps the local device name and settings |
| `--slot A\|B` | read `var-A` or `var-B` instead of choosing automatically |
| `--no-blueman` | do not stop `blueman-applet` while bluetooth is stopped |

## How it works

### 1. Reading

- The local store is read with `sudo tar` from `/var/lib/bluetooth`.
- SteamOS keeps Bluetooth data on the `var-A` and `var-B` partitions (A/B updates), under `lib/bluetooth`. Partitions are found via `/dev/disk/by-partlabel/`.
- A partition is mounted read-only with `ro,noload` (no ext4 journal replay) into a temporary directory and unmounted right after. An already mounted partition is read in place.
- **Nothing is ever written to SteamOS partitions.**
- A slot without `lib/bluetooth` counts as empty and does not stop the run.
- The `cache` directory is neither read nor copied.

### 2. Choosing the SteamOS slot

The tool has to find out which A/B slot SteamOS booted last. Two markers:

1. **Last mount time** from the ext4 superblock (`dumpe2fs -h`) — primary;
2. **newest device record time** for this adapter.

Rules:

- a slot without the local adapter is dropped;
- if one slot is left, it is used;
- if both markers point to the same slot, it is used without asking;
- if a marker is missing or the markers disagree, the tool asks and suggests the slot with the latest mount time;
- if no marker is available at all, the tool asks as well.

### 3. Plan

Each SteamOS device is matched to a local one by (adapter, device address):

| Label | Meaning | Selected by default |
|---|---|---|
| `NEW` | device is missing here | yes |
| `REPLACE` | device exists, keys differ | yes |
| `SAME` | keys match | no |

Only key sections are compared (`LinkKey`, `LongTermKey`, `PeripheralLongTermKey`, `SlaveLongTermKey`, `IdentityResolvingKey`, `LocalSignatureKey`, `RemoteSignatureKey`); a different name or setting does not make a record `REPLACE`.

Devices that exist only in this system are not listed and not touched: sync goes one way.

The list is interactive (`questionary` checkboxes), followed by a separate confirmation.

### 4. Writing

1. `bluetooth.service` is stopped, so the running daemon cannot overwrite the new records. If `blueman-applet` is running, it is stopped first and started again at the end: stopping the service while the applet runs can make the adapter toggle on and off in a loop (rfkill).
2. Replaced records are saved to `~/.local/state/bt-sync/<YYYYMMDD-HHMMSS>/` together with `manifest.json` (what was replaced and what was added).
3. The `info` file is written with `sudo install`, mode `600 root:root`. By default the whole file is copied; with `--keys-only` only the keys are put into the local file.
4. `bluetooth.service` is started again, even if writing failed.
5. `bluetoothctl devices` is used to check that bluez loaded every copied device. Devices that did not load are reported.

### Undo

`bt-sync restore` lists backups (newest first). For the chosen backup it puts replaced records back, removes added device directories; bluetooth is stopped for that time the same way as during sync.

## Limitations

- Only the SteamOS → current system direction is supported.
- Developed and used on Linux Mint. Of the desktop Bluetooth applets only `blueman-applet` is paused; other applets are left alone.
- No special handling for controllers: they appear in the common list; untick them if you don't need them.
- Verified on real hardware: reading both slots, slot choice and the plan (`--dry-run`). Not verified yet: writing and `restore`.

## Development

Requirements: [uv](https://docs.astral.sh/uv/), Python 3.12+.

```bash
uv sync                          # environment and dependencies
uv run pytest                    # tests
uvx ruff check .                 # linter
uv tool install --editable .     # bt-sync command in ~/.local/bin, picks up edits immediately
```

### Layout

```
src/bt_steamos_sync/
  cli.py              arguments, sync and restore flows, root check
  bluez_info.py       DeviceRecord, parsing and rendering info, comparing and replacing keys
  bluetooth_store.py  reading the store via sudo tar, StoreSnapshot
  steamos.py          var-A/var-B partitions, dumpe2fs, ro,noload mounting
  slots.py            SlotState and choosing a slot by markers
  plan.py             NEW / REPLACE / SAME classification, building the plan
  apply.py            backup, writing via sudo install, manifest, restore
  services.py         stopping bluetooth for the write, pausing blueman-applet, bluetoothctl
  privileged.py       sudo wrapper (sudo -v to authenticate, sudo -n for commands)
  errors.py           BtSyncError, base of all errors shown without a traceback
  ui.py               interactive list and confirmations (questionary)
tests/
  conftest.py              addresses, info builders (classic_info, le_info), make_store_tar, FakeSudo
  test_bluez_info.py       parsing and replacing keys
  test_plan.py             classification
  test_slots.py            dumpe2fs parsing and slot choice
  test_store_and_apply.py  snapshot from tar, apply/restore via FakeSudo, broken backups
  test_cli.py              root refusal, empty plan, order of sudo check, stop, write, start
```

### How the tests work

- All system calls go through the `Sudo` object (`privileged.py`). Tests replace it with `FakeSudo`, which records calls and remembers installed files without running anything.
- BlueZ stores are built in memory as tar archives with `make_store_tar`, the same shape `sudo tar` returns.
- The backup directory is redirected to a temporary folder by the `state_home` fixture (via `XDG_STATE_HOME`).
- Not covered by tests: real mounting (`steamos.py`), `blueman-applet` handling (`services.py`) and the interactive UI (`ui.py`).

## License

[MIT](LICENSE)
