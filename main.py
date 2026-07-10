import subprocess

CMD = ["tcpdump", "-i", "any", "-n", "-l", "port 80 or port 443"]


def extract_src_ip(line: str) -> str | None:
    if " > " not in line:
        return None
    before_arrow = line.split(" > ", 1)[0]
    src_token = before_arrow.split()[-1]
    if "." not in src_token:
        return None
    src_ip = src_token.rsplit(".", 1)[0]
    return src_ip


proc = subprocess.Popen(CMD, stdout=subprocess.PIPE, text=True, bufsize=1)

assert proc.stdout is not None

try:
    for raw_line in proc.stdout:
        ip = extract_src_ip(raw_line)
        if ip:
            print(ip)
except KeyboardInterrupt:
    proc.terminate()