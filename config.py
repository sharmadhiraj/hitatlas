import re
from dataclasses import dataclass

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]

PRESET_PATTERNS = {
    "nginx-combined": re.compile(r'^(?P<ip>\S+) \S+ \S+ \[.+?\] "\S+ \S+ \S+" \d+ \d+'),
    "apache-combined": re.compile(r'^(?P<ip>\S+) \S+ \S+ \[.+?\] "\S+ \S+ \S+" \d+ \d+'),
}
JSON_FORMATS = {"caddy-json"}


@dataclass
class Source:
    path: str
    format: str
    regex: re.Pattern[str] | None


@dataclass
class SourceSpec:
    path: str | None
    path_glob: str | None
    format: str
    regex: re.Pattern[str] | None


def load_source_specs(config_path: str) -> list[SourceSpec]:
    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    specs = []
    for raw in config.get("source", []):
        fmt = raw["format"]
        if fmt == "custom_regex":
            regex = re.compile(raw["regex"])
        elif fmt in JSON_FORMATS:
            regex = None
        elif fmt in PRESET_PATTERNS:
            regex = PRESET_PATTERNS[fmt]
        else:
            raise ValueError(f"unknown format {fmt!r}")

        specs.append(
            SourceSpec(path=raw.get("path"), path_glob=raw.get("path_glob"), format=fmt, regex=regex)
        )
    return specs
