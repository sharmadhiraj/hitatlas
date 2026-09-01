import json
import logging
import random
import time

from sse import broadcast

logger = logging.getLogger(__name__)

DEMO_LOCATIONS = [
    ("New York", "US", 40.7128, -74.0060),
    ("Los Angeles", "US", 34.0522, -118.2437),
    ("London", "GB", 51.5074, -0.1278),
    ("Paris", "FR", 48.8566, 2.3522),
    ("Berlin", "DE", 52.5200, 13.4050),
    ("Tokyo", "JP", 35.6762, 139.6503),
    ("Sydney", "AU", -33.8688, 151.2093),
    ("Sao Paulo", "BR", -23.5505, -46.6333),
    ("Mumbai", "IN", 19.0760, 72.8777),
    ("Singapore", "SG", 1.3521, 103.8198),
    ("Toronto", "CA", 43.6511, -79.3470),
    ("Cairo", "EG", 30.0444, 31.2357),
    ("Moscow", "RU", 55.7558, 37.6173),
    ("Seoul", "KR", 37.5665, 126.9780),
    ("Mexico City", "MX", 19.4326, -99.1332),
    ("Johannesburg", "ZA", -26.2041, 28.0473),
    ("Jakarta", "ID", -6.2088, 106.8456),
    ("Amsterdam", "NL", 52.3676, 4.9041),
    ("Buenos Aires", "AR", -34.6037, -58.3816),
    ("Dubai", "AE", 25.2048, 55.2708),
]


def _random_ip() -> str:
    return ".".join(str(random.randint(1, 254)) for _ in range(4))


def _jitter(value: float, spread: float = 0.5) -> float:
    return value + random.uniform(-spread, spread)


def run_demo(min_interval: float = 0.5, max_interval: float = 2.5) -> None:
    logger.info("demo mode: generating random hits every %.1f-%.1fs", min_interval, max_interval)
    while True:
        city, country, lat, lng = random.choice(DEMO_LOCATIONS)
        hit = {
            "ip": _random_ip(),
            "lat": _jitter(lat),
            "lng": _jitter(lng),
            "city": city,
            "country": country,
        }
        payload = json.dumps(hit)
        print(payload, flush=True)
        broadcast(payload)
        time.sleep(random.uniform(min_interval, max_interval))
