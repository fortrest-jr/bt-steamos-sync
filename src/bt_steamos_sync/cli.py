import argparse
import os
import sys
from datetime import datetime

from bt_steamos_sync import ui
from bt_steamos_sync.apply import apply_plan, list_backups, restore_backup
from bt_steamos_sync.bluetooth_store import LOCAL_STORE, StoreSnapshot, read_store
from bt_steamos_sync.errors import BtSyncError
from bt_steamos_sync.plan import PlanItem, build_plan
from bt_steamos_sync.privileged import Sudo
from bt_steamos_sync.services import bluetooth_stopped, known_devices
from bt_steamos_sync.slots import SlotState, choose_slot
from bt_steamos_sync.steamos import available_slots, read_slot


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="bt-sync",
        description="Copy Bluetooth pairings from SteamOS to this system.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="show the plan and change nothing"
    )
    parser.add_argument(
        "--keys-only",
        action="store_true",
        help="replace only keys, keep local names and settings",
    )
    parser.add_argument(
        "--slot",
        choices=["A", "B"],
        help="read SteamOS slot var-A or var-B instead of guessing",
    )
    parser.add_argument(
        "--no-blueman",
        action="store_true",
        help="do not pause blueman-applet while bluetooth is stopped",
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("restore", help="undo an earlier sync")
    return parser.parse_args(argv)


def refuse_root() -> None:
    if os.geteuid() == 0:
        sys.exit("Run bt-sync as your normal user: it asks for sudo itself.")


def read_slots(
    sudo: Sudo, local_adapters: set[str]
) -> dict[str, tuple[SlotState, StoreSnapshot]]:
    labels = available_slots()
    if not labels:
        sys.exit("No SteamOS var-A / var-B partitions found.")
    return {label: read_slot(sudo, label, local_adapters) for label in labels}


def pick_slot(
    slots: dict[str, tuple[SlotState, StoreSnapshot]], forced: str | None
) -> str:
    states = [state for state, _ in slots.values()]
    if forced:
        label = f"var-{forced}"
        if label not in slots:
            sys.exit(f"Partition {label} not found.")
        return label
    choice = choose_slot(states)
    for state in states:
        print(ui.describe_slot(state))
    if choice.slot is None:
        sys.exit(f"Nothing to copy: {choice.reason}.")
    if not choice.needs_confirmation:
        print(f"Using {choice.slot.label}: {choice.reason}.")
        return choice.slot.label
    picked = ui.confirm_slot(choice, states)
    if picked is None:
        sys.exit("Cancelled.")
    return picked.label


def report_unloaded(items: list[PlanItem]) -> None:
    loaded = known_devices()
    missing = [item for item in items if item.source.address not in loaded]
    for item in missing:
        print(f"WARNING: bluez did not load {item.source.name} ({item.source.address})")
    if not missing:
        print(f"All {len(items)} device(s) are loaded by bluez.")


def run_sync(args: argparse.Namespace, sudo: Sudo) -> None:
    sudo.authenticate()
    local = read_store(sudo, LOCAL_STORE)
    slots = read_slots(sudo, local.adapters)
    _, source = slots[pick_slot(slots, args.slot)]
    shared = source.adapters & local.adapters
    plan = build_plan([d for d in source.devices if d.adapter in shared], local.devices)
    if not plan:
        sys.exit("Nothing to copy: SteamOS has no pairings for this adapter.")
    if args.dry_run:
        ui.print_plan(plan)
        return
    selected = ui.select_items(plan)
    if not selected or not ui.confirm_apply(selected):
        sys.exit("Nothing changed.")
    sudo.authenticate()
    with bluetooth_stopped(sudo, manage_blueman=not args.no_blueman):
        backup_dir = apply_plan(sudo, selected, args.keys_only, datetime.now())
    print(f"Backup: {backup_dir}  (undo with: bt-sync restore)")
    report_unloaded(selected)


def run_restore(args: argparse.Namespace, sudo: Sudo) -> None:
    backups = list_backups()
    if not backups:
        sys.exit("No backups found.")
    backup_dir = ui.select_backup(backups)
    if backup_dir is None or not ui.confirm_restore(backup_dir):
        sys.exit("Nothing changed.")
    sudo.authenticate()
    with bluetooth_stopped(sudo, manage_blueman=not args.no_blueman):
        restored = restore_backup(sudo, backup_dir)
    print(f"Restored {len(restored)} device(s) from {backup_dir.name}.")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    refuse_root()
    sudo = Sudo()
    try:
        if args.command == "restore":
            run_restore(args, sudo)
        else:
            run_sync(args, sudo)
    except BtSyncError as error:
        sys.exit(f"Error: {error}")
    except KeyboardInterrupt:
        sys.exit("Cancelled.")
