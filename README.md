# HitAtlas

Tails web server access logs, resolves client IPs to lat/lng, and plots them on a world map.

## Usage

```
python3 main.py
```

Reads `config.toml` (or the path in `HITATLAS_CONFIG`). Each `[[source]]` is a log file to tail, either a single `path`, or a `path_glob` to auto-discover every matching file (e.g. every vhost on a shared VPS) without listing each one:

```toml
[[source]]
path_glob = "/home/*/logs/nginx/access.log"
format = "nginx-combined"
```

Supported `format` values: `nginx-combined`, `apache-combined`, `caddy-json`, or `custom_regex` (requires a `regex` key with a named `ip` group).

`path_glob` is re-scanned periodically (every 30s by default, set `HITATLAS_RESCAN_INTERVAL` to change) to pick up newly added sites without a restart.

## GeoIP setup

City-level lookups use MaxMind's GeoLite2 City database, looked up locally (no network calls per request):

1. Create a free account at https://www.maxmind.com/en/geolite2/signup
2. Generate a license key and download `GeoLite2-City.mmdb`.
3. Place it in the project root, or set `HITATLAS_GEOIP_DB` to its path.

Each matched request is printed as a JSON line and broadcast to any connected frontend:

```
{"ip": "8.8.8.8", "lat": 37.751, "lng": -97.822, "city": "Ashburn", "country": "US"}
```

## Live feed (backend)

`main.py` also serves a Server-Sent Events endpoint at `/events`, bound to `127.0.0.1:8765` by default (`HITATLAS_HTTP_HOST` / `HITATLAS_HTTP_PORT` to change). It only speaks plain HTTP with no CORS headers, since it's meant to sit behind an Nginx reverse proxy on the same origin as the frontend, not be exposed to the internet directly.

Example Nginx location block on the frontend's vhost, note `proxy_buffering off` is required, otherwise Nginx buffers the stream and the browser never sees events in real time:

```
location /events {
    proxy_pass http://127.0.0.1:8765;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_read_timeout 24h;
}
```

The frontend (a separate static site, see `frontend/`) connects with `new EventSource("/events")`.

## Work in Progress
