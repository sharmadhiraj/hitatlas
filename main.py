import ipaddress
import subprocess

CMD = [
    "tcpdump",
    "-i", "any",
    "-n",
    "-l",
    "inbound and tcp[tcpflags] == tcp-syn and (dst port 80 or dst port 443)",
]


def extract_src_ip(line: str) -> str | None:
    if " > " not in line:
        return None
    before_arrow = line.split(" > ", 1)[0]
    src_token = before_arrow.split()[-1]
    if "." not in src_token:
        return None
    src_ip = src_token.rsplit(".", 1)[0]
    return src_ip


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


proc = subprocess.Popen(CMD, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)

assert proc.stdout is not None

try:
    for raw_line in proc.stdout:
        extracted_ip = extract_src_ip(raw_line)
        if extracted_ip and is_public_ip(extracted_ip):
            print(extracted_ip)
except KeyboardInterrupt:
    proc.terminate()