from datetime import datetime
from pathlib import Path

import questionary

from bt_steamos_sync.apply import BackupError, read_manifest
from bt_steamos_sync.plan import Change, PlanItem
from bt_steamos_sync.slots import SlotChoice, SlotState

CHANGE_LABELS = {
    Change.NEW: "NEW     ",
    Change.REPLACE: "REPLACE ",
    Change.SAME: "SAME    ",
}


def format_time(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else "unknown"


def describe_slot(slot: SlotState) -> str:
    return (
        f"{slot.label}: last mounted {format_time(slot.last_mount)}, "
        f"newest pairing {format_time(slot.newest_record)}"
    )


def describe_item(item: PlanItem) -> str:
    rename = ""
    if item.local is not None and item.local.name != item.source.name:
        rename = f"  (local name: {item.local.name})"
    return f"{CHANGE_LABELS[item.change]} {item.source.name:<28} {item.source.address}{rename}"


def confirm_slot(choice: SlotChoice, slots: list[SlotState]) -> SlotState | None:
    print(f"Cannot pick the SteamOS slot automatically: {choice.reason}")
    by_label = {describe_slot(slot): slot for slot in slots if slot.has_adapter}
    default = describe_slot(choice.slot) if choice.slot else None
    answer = questionary.select(
        "Copy pairings from which slot?", choices=list(by_label), default=default
    ).ask()
    return by_label.get(answer) if answer else None


def select_items(items: list[PlanItem]) -> list[PlanItem] | None:
    choices = [
        questionary.Choice(
            describe_item(item), value=index, checked=item.selected_by_default
        )
        for index, item in enumerate(items)
    ]
    picked = questionary.checkbox(
        "Devices to copy (space toggles, enter confirms):", choices=choices
    ).ask()
    return None if picked is None else [items[index] for index in picked]


def print_plan(items: list[PlanItem]) -> None:
    for item in items:
        marker = "[x]" if item.selected_by_default else "[ ]"
        print(f"{marker} {describe_item(item)}")


def confirm_apply(items: list[PlanItem]) -> bool:
    replaced = sum(item.change is Change.REPLACE for item in items)
    added = sum(item.change is Change.NEW for item in items)
    question = f"Write {len(items)} pairing(s): {added} new, {replaced} replaced, then restart bluetooth?"
    return bool(questionary.confirm(question, default=False).ask())


def describe_backup(backup_dir: Path) -> str:
    try:
        names = ", ".join(change.name for change in read_manifest(backup_dir))
    except BackupError:
        names = "unreadable manifest"
    return f"{backup_dir.name}: {names}"


def select_backup(backups: list[Path]) -> Path | None:
    by_label = {describe_backup(path): path for path in backups}
    answer = questionary.select("Restore which sync?", choices=list(by_label)).ask()
    return by_label.get(answer) if answer else None


def confirm_restore(backup_dir: Path) -> bool:
    question = f"Undo sync {backup_dir.name} and restart bluetooth?"
    return bool(questionary.confirm(question, default=False).ask())
