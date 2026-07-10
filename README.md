# HitAtlas

Tails your web server's access logs, resolves visitor IPs to a city, and shows them as live pings on a world map.

## TLDR

- A Python backend tails Nginx/Apache/Caddy access logs, extracts real visitor IPs, and looks up their city/country from
  a local database (no external API calls).
- Each hit is pushed to a browser in real time over Server-Sent Events.
- A small static frontend renders those hits as animated pings on a 2D world map.

## Components

| Path          | What it is                                                            |
|---------------|-----------------------------------------------------------------------|
| `main.py`     | Entry point, wires everything together                                |
| `config.py`   | Parses `config.toml`                                                  |
| `tailer.py`   | Follows log files, extracts and filters IPs                           |
| `geo.py`      | IP → city/country/lat/lng lookup (MaxMind GeoLite2)                   |
| `sse.py`      | Broadcasts hits to connected browsers over SSE                        |
| `config.toml` | Which log file(s) to watch, and their format                          |
| `frontend/`   | Static site: world map + live feed (plain HTML/CSS/JS, no build step) |

## Setup

1. **Install dependencies**
   ```
   pip install -r requirements.txt
   ```

2. **Get a GeoIP database.** Create a free account at https://www.maxmind.com/en/geolite2/signup, generate a license
   key, and download `GeoLite2-City.mmdb` into the project root (or point `HITATLAS_GEOIP_DB` at it, see
   `.env.example`).

3. **Configure `config.toml`** with the log file(s) to watch:
   ```toml
   [[source]]
   path = "/var/log/nginx/access.log"
   format = "nginx-combined"
   ```
   Or auto-discover every vhost on a shared server without listing each one:
   ```toml
   [[source]]
   path_glob = "/home/*/logs/nginx/access.log"
   format = "nginx-combined"
   ```
   Supported `format` values: `nginx-combined`, `apache-combined`, `caddy-json`, or `custom_regex` (with a `regex` key
   using a named `ip` group).

4. **Run the backend**
   ```
   python3 main.py
   ```
   To keep it running permanently (survives crashes/reboots), see the systemd unit below.

5. **Serve the frontend.** `frontend/` is a plain static site, serve it with any web server. Put it behind the same
   reverse proxy as your backend's `/events` endpoint (see below), so the browser can reach both from one origin.

### Running as a systemd service

```ini
[Unit]
Description=HitAtlas backend
After=network.target

[Service]
Type=simple
WorkingDirectory = /path/to/hitatlas
ExecStart = /path/to/hitatlas/venv/bin/python3 /path/to/hitatlas/main.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```
systemctl daemon-reload
systemctl enable --now hitatlas
journalctl -u hitatlas -f
```

### Reverse-proxying `/events`

The backend serves Server-Sent Events on `127.0.0.1:8765` (plain HTTP, no CORS, deliberately not exposed to the internet
directly). Point your reverse proxy's `/events` location at it, `proxy_buffering off` is required or the stream won't
arrive in real time:

```nginx
location /events {
    proxy_pass http://127.0.0.1:8765;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_read_timeout 24h;
}
```

## How it works

```
access.log --tail--> extract IP --filter--> dedupe --> GeoIP lookup --> SSE broadcast --> frontend map
```

1. **Tail**: each configured log file is followed like `tail -f`, handling log rotation automatically. `path_glob`
   entries are re-scanned periodically to pick up newly added sites without a restart.
2. **Extract & filter**: the client IP is pulled out with a regex (or JSON parsing for `caddy-json`), then
   private/loopback/reserved IPs are dropped.
3. **Dedupe**: consecutive repeats of the same IP are collapsed, so one browser loading several assets doesn't look like
   several visitors.
4. **Geolocate**: each IP is looked up in a local MaxMind GeoLite2 City database, sub-millisecond, no network
   round-trip.
5. **Broadcast**: each hit is printed as a JSON line and pushed to every connected browser over a Server-Sent Events
   endpoint (`/events`).
6. **Render**: the frontend draws a world map (a fixed-projection SVG, not map tiles) and animates a ping at each hit's
   coordinates, alongside a live feed and running stats.
