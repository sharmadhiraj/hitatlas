import glob
import http.server
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

import geoip2.database
import geoip2.errors

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]

CONFIG_PATH = os.environ.get("HITATLAS_CONFIG", "config.toml")
RESCAN_INTERVAL_SECONDS = float(os.environ.get("HITATLAS_RESCAN_INTERVAL", "30"))
GEOIP_DB_PATH = os.environ.get("HITATLAS_GEOIP_DB", "GeoLite2-City.mmdb")
HTTP_HOST = os.environ.get("HITATLAS_HTTP_HOST", "127.0.0.1")
HTTP_PORT = int(os.environ.get("HITATLAS_HTTP_PORT", "8765"))

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


def geolocate(reader: geoip2.database.Reader, ip: str) -> dict[str, object] | None:
    try:
        city = reader.city(ip)
    except geoip2.errors.AddressNotFoundError:
        return None

    if city.location.latitude is None or city.location.longitude is None:
        return None

    return {
        "ip": ip,
        "lat": city.location.latitude,
        "lng": city.location.longitude,
        "city": city.city.name,
        "country": city.country.iso_code,
    }


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


subscribers: list["queue.Queue[str]"] = []
subscribers_lock = threading.Lock()


def broadcast(payload: str) -> None:
    with subscribers_lock:
        for subscriber in subscribers:
            subscriber.put(payload)


class SSEHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/events":
            self.send_response(404)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        client_queue: "queue.Queue[str]" = queue.Queue()
        with subscribers_lock:
            subscribers.append(client_queue)
        logger.info("SSE client connected (%d total)", len(subscribers))

        try:
            while True:
                payload = client_queue.get()
                self.wfile.write(f"data: {payload}\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with subscribers_lock:
                subscribers.remove(client_queue)
            logger.info("SSE client disconnected (%d total)", len(subscribers))

    def log_message(self, format: str, *args: object) -> None:
        pass


def main() -> None:
    if not os.path.exists(GEOIP_DB_PATH):
        logger.error(
            "GeoIP database not found at %s. Download GeoLite2-City.mmdb from "
            "https://www.maxmind.com/en/accounts/current/geoip/downloads "
            "(requires a free MaxMind account) and set HITATLAS_GEOIP_DB to its path.",
            GEOIP_DB_PATH,
        )
        sys.exit(1)
    reader = geoip2.database.Reader(GEOIP_DB_PATH)

    logger.info("loading config from %s", CONFIG_PATH)
    specs = load_source_specs(CONFIG_PATH)
    if not specs:
        logger.error("no sources configured in %s", CONFIG_PATH)
        sys.exit(1)

    out_queue: "queue.Queue[str]" = queue.Queue()
    started: set[str] = set()

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

    threading.Thread(target=rescan_globs, args=(specs, out_queue, started), daemon=True).start()

    httpd = http.server.ThreadingHTTPServer((HTTP_HOST, HTTP_PORT), SSEHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    logger.info("SSE server listening on http://%s:%d/events", HTTP_HOST, HTTP_PORT)

    logger.info("started %d source thread(s), waiting for matching requests", len(started))
    last_ip = None
    try:
        while True:
            ip = out_queue.get()
            if ip == last_ip:
                continue
            last_ip = ip

            hit = geolocate(reader, ip)
            if hit is None:
                logger.debug("no geolocation found for %s", ip)
                continue
            payload = json.dumps(hit)
            print(payload, flush=True)
            broadcast(payload)
    except KeyboardInterrupt:
        logger.info("stopping")
    finally:
        reader.close()


if __name__ == "__main__":
    main()
