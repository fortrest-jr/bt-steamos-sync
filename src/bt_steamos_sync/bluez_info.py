import configparser
import io
from dataclasses import dataclass

KEY_SECTIONS = (
    "LinkKey",
    "LongTermKey",
    "PeripheralLongTermKey",
    "SlaveLongTermKey",
    "IdentityResolvingKey",
    "LocalSignatureKey",
    "RemoteSignatureKey",
)


@dataclass(frozen=True)
class DeviceRecord:
    adapter: str
    address: str
    info_text: str

    @property
    def name(self) -> str:
        return _parse(self.info_text).get("General", "Name", fallback=self.address)

    @property
    def keys(self) -> dict[str, dict[str, str]]:
        return extract_keys(self.info_text)


def _parse(text: str) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str  # type: ignore[assignment]
    parser.read_string(text)
    return parser


def _render(parser: configparser.ConfigParser) -> str:
    buffer = io.StringIO()
    parser.write(buffer, space_around_delimiters=False)
    return buffer.getvalue()


def extract_keys(text: str) -> dict[str, dict[str, str]]:
    parser = _parse(text)
    return {
        section: dict(parser[section])
        for section in KEY_SECTIONS
        if parser.has_section(section)
    }


def same_keys(first: str, second: str) -> bool:
    return extract_keys(first) == extract_keys(second)


def replace_keys(local_text: str, source_text: str) -> str:
    local = _parse(local_text)
    for section in KEY_SECTIONS:
        local.remove_section(section)
    for section, values in extract_keys(source_text).items():
        local[section] = values
    return _render(local)
