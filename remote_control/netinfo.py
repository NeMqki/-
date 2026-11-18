"""接続用URLに使うIPアドレスの取得 (家のLAN / Tailscale)。"""

from __future__ import annotations

import ipaddress
import shutil
import socket
import subprocess
import sys
from pathlib import Path

TAILSCALE_NET = ipaddress.ip_network("100.64.0.0/10")


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _tailscale_cli() -> str | None:
    exe = shutil.which("tailscale")
    if exe:
        return exe
    candidates = [
        Path(r"C:\Program Files\Tailscale\tailscale.exe"),
        Path("/Applications/Tailscale.app/Contents/MacOS/Tailscale"),
    ]
    return next((str(p) for p in candidates if p.exists()), None)


def tailscale_ip() -> str | None:
    cli = _tailscale_cli()
    if cli:
        try:
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            out = subprocess.run(
                [cli, "ip", "-4"], capture_output=True, text=True, timeout=3, creationflags=flags
            ).stdout
            for line in out.split():
                if _is_tailscale(line):
                    return line
        except (OSError, subprocess.SubprocessError):
            pass
    # CLIが無い場合: このPCのアドレス一覧から 100.64.0.0/10 を探す
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addr = info[4][0]
            if _is_tailscale(addr):
                return addr
    except OSError:
        pass
    return None


def _is_tailscale(addr: str) -> bool:
    try:
        return ipaddress.ip_address(addr) in TAILSCALE_NET
    except ValueError:
        return False


def make_url(ip: str, port: int, token: str) -> str:
    return f"http://{ip}:{port}/#token={token}"
