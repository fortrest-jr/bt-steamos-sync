from conftest import classic_info, le_info

from bt_steamos_sync.bluez_info import (
    DeviceRecord,
    extract_keys,
    replace_keys,
    same_keys,
)


def test_name_is_read_from_general_section(headphones_source: DeviceRecord) -> None:
    assert headphones_source.name == "LE_Headphones"


def test_name_falls_back_to_address_when_missing() -> None:
    record = DeviceRecord(
        "AA:AA:AA:AA:AA:AA", "BB:BB:BB:BB:BB:BB", "[LinkKey]\nKey=1\n"
    )
    assert record.name == "BB:BB:BB:BB:BB:BB"


def test_extract_keys_returns_only_key_sections() -> None:
    keys = extract_keys(le_info("KB", "ltk", "irk"))
    assert set(keys) == {"IdentityResolvingKey", "LongTermKey"}, (
        f"unexpected sections: {set(keys)}"
    )
    assert keys["LongTermKey"]["Key"] == "ltk"


def test_same_keys_ignores_name_and_other_metadata() -> None:
    assert same_keys(classic_info("Old name", "KEY"), classic_info("New name", "KEY"))


def test_same_keys_detects_different_link_key() -> None:
    assert not same_keys(classic_info("X", "KEY1"), classic_info("X", "KEY2"))


def test_replace_keys_keeps_local_name_and_takes_source_keys() -> None:
    merged = replace_keys(
        classic_info("Local name", "OLD"), classic_info("Source name", "NEW")
    )
    record = DeviceRecord("AA:AA:AA:AA:AA:AA", "BB:BB:BB:BB:BB:BB", merged)
    assert record.name == "Local name", "keys-only mode must keep the local name"
    assert record.keys["LinkKey"]["Key"] == "NEW", (
        "keys-only mode must take the source key"
    )


def test_replace_keys_drops_local_key_sections_absent_in_source() -> None:
    merged = replace_keys(le_info("KB", "ltk", "irk"), classic_info("KB", "LINK"))
    assert set(extract_keys(merged)) == {"LinkKey"}


def test_replace_keys_output_has_no_spaces_around_equals() -> None:
    merged = replace_keys(classic_info("A", "OLD"), classic_info("B", "NEW"))
    assert "Key=NEW" in merged
