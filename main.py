import ipaddress
import json
import os
import queue
import re
import sys
import threading
import time
from dataclasses import dataclass

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]

CONFIG_PATH = os.environ.get("HITATLAS_CONFIG", "config.toml")

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


def load_sources(config_path: str) -> list[Source]:
    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    sources = []
    for raw in config.get("source", []):
        fmt = raw["format"]
        if fmt == "custom_regex":
            regex = re.compile(raw["regex"])
        elif fmt in JSON_FORMATS:
            regex = None
        elif fmt in PRESET_PATTERNS:
            regex = PRESET_PATTERNS[fmt]
        else:
            raise ValueError(f"unknown format {fmt!r} for source {raw['path']!r}")
        sources.append(Source(path=raw["path"], format=fmt, regex=regex))
    return sources


def extract_ip(line: str, source: Source) -> str | None:
    if source.format in JSON_FORMATS:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return None
        return data.get("request", {}).get("remote_ip")

    assert source.regex is not None
    match = source.regex.match(line)
    return match.group("ip") if match else None


def is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def follow(path: str):
    while not os.path.exists(path):
        time.sleep(1)

    f = open(path, "r")
    f.seek(0, os.SEEK_END)
    inode = os.fstat(f.fileno()).st_ino

    while True:
        line = f.readline()
        if line:
            yield line
            continue

        time.sleep(0.5)
        try:
            if os.stat(path).st_ino != inode:
                f.close()
                f = open(path, "r")
                inode = os.fstat(f.fileno()).st_ino
        except FileNotFoundError:
            continue


def tail_source(source: Source, out_queue: "queue.Queue[str]") -> None:
    for line in follow(source.path):
        ip = extract_ip(line, source)
        if ip and is_public_ip(ip):
            out_queue.put(ip)


def main() -> None:
    sources = load_sources(CONFIG_PATH)
    if not sources:
        print(f"no sources configured in {CONFIG_PATH}", file=sys.stderr)
        sys.exit(1)

    out_queue: "queue.Queue[str]" = queue.Queue()
    for source in sources:
        threading.Thread(target=tail_source, args=(source, out_queue), daemon=True).start()

    try:
        while True:
            print(out_queue.get(), flush=True)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
