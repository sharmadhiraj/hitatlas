import http.server
import json
import logging
import os
import queue
import sys
import threading

import geoip2.database

from config import load_source_specs
from geo import geolocate
from sse import SSEHandler, broadcast
from tailer import rescan_globs, start_all

CONFIG_PATH = os.environ.get("HITATLAS_CONFIG", "config.toml")
GEOIP_DB_PATH = os.environ.get("HITATLAS_GEOIP_DB", "GeoLite2-City.mmdb")
HTTP_HOST = "127.0.0.1"
HTTP_PORT = int(os.environ.get("HITATLAS_HTTP_PORT", "8765"))

logging.basicConfig(
    level=os.environ.get("HITATLAS_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


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
    start_all(specs, out_queue, started)

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
