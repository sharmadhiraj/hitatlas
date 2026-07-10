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

## Work in Progress
