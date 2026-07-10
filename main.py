import glob
import ipaddress
import json
import logging
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

logging.basicConfig(
    level=os.environ.get("HITATLAS_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("hitatlas")

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
            raise ValueError(f"unknown format {fmt!r}")

        if "path_glob" in raw:
            paths = sorted(glob.glob(raw["path_glob"]))
            if not paths:
                logger.warning("path_glob %r matched no files yet", raw["path_glob"])
            for path in paths:
                sources.append(Source(path=path, format=fmt, regex=regex))
        else:
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
    if not os.path.exists(path):
        logger.warning("%s does not exist yet, waiting for it to appear", path)
        while not os.path.exists(path):
            time.sleep(1)

    logger.info("tailing %s", path)
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
                logger.info("%s rotated, reopening", path)
                f.close()
                f = open(path, "r")
                inode = os.fstat(f.fileno()).st_ino
        except FileNotFoundError:
            continue


def tail_source(source: Source, out_queue: "queue.Queue[str]") -> None:
    matched = 0
    for line in follow(source.path):
        ip = extract_ip(line, source)
        if ip and is_public_ip(ip):
            matched += 1
            out_queue.put(ip)
        elif matched == 0:
            logger.debug("%s: no ip matched line: %r", source.path, line.rstrip())


def main() -> None:
    logger.info("loading config from %s", CONFIG_PATH)
    sources = load_sources(CONFIG_PATH)
    if not sources:
        logger.error("no sources configured in %s", CONFIG_PATH)
        sys.exit(1)

    for source in sources:
        logger.info("configured source: %s (%s)", source.path, source.format)

    out_queue: "queue.Queue[str]" = queue.Queue()
    for source in sources:
        threading.Thread(target=tail_source, args=(source, out_queue), daemon=True).start()

    logger.info("started %d source thread(s), waiting for matching requests", len(sources))
    try:
        while True:
            print(out_queue.get(), flush=True)
    except KeyboardInterrupt:
        logger.info("stopping")


if __name__ == "__main__":
    main()
