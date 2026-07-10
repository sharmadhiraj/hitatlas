# HitAtlas

Tails web server access logs, resolves client IPs to lat/lng, and plots them on a world map.

## Usage

```
python3 main.py
```

Reads `config.toml` (or the path in `HITATLAS_CONFIG`). Each `[[source]]` is a log file to tail:

```toml
[[source]]
path = "/var/log/nginx/access.log"
format = "nginx-combined"
```

Supported `format` values: `nginx-combined`, `apache-combined`, `caddy-json`, or `custom_regex` (requires a `regex` key with a named `ip` group).

## Work in Progress
