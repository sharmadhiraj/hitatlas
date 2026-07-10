import glob
import ipaddress
import json
import logging
import os
import queue
import threading
import time

from config import JSON_FORMATS, Source, SourceSpec

logger = logging.getLogger(__name__)

RESCAN_INTERVAL_SECONDS = float(os.environ.get("HITATLAS_RESCAN_INTERVAL", "30"))


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


def start_tailing(path: str, spec: SourceSpec, out_queue: "queue.Queue[str]", started: set[str]) -> None:
    if path in started:
        return
    started.add(path)
    logger.info("configured source: %s (%s)", path, spec.format)
    source = Source(path=path, format=spec.format, regex=spec.regex)
    threading.Thread(target=tail_source, args=(source, out_queue), daemon=True).start()


def start_all(specs: list[SourceSpec], out_queue: "queue.Queue[str]", started: set[str]) -> None:
    for spec in specs:
        if spec.path_glob:
            paths = sorted(glob.glob(spec.path_glob))
            if not paths:
                logger.warning("path_glob %r matched no files yet", spec.path_glob)
            for path in paths:
                start_tailing(path, spec, out_queue, started)
        else:
            assert spec.path is not None
            start_tailing(spec.path, spec, out_queue, started)


def rescan_globs(specs: list[SourceSpec], out_queue: "queue.Queue[str]", started: set[str]) -> None:
    glob_specs = [spec for spec in specs if spec.path_glob]
    if not glob_specs:
        return
    while True:
        time.sleep(RESCAN_INTERVAL_SECONDS)
        for spec in glob_specs:
            assert spec.path_glob is not None
            for path in sorted(glob.glob(spec.path_glob)):
                if path not in started:
                    logger.info("discovered new source via %s: %s", spec.path_glob, path)
                    start_tailing(path, spec, out_queue, started)
