"""OS依存の機能: PC起動時の自動起動 / スリープ防止。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

APP_NAME = "PocketDesk"


# --------------------------------------------------------------------------
# 自動起動
# --------------------------------------------------------------------------
def launch_command() -> list[str]:
    """自動起動で実行するコマンド (exe化されていればexe自身)。"""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--minimized"]
    py = sys.executable
    if sys.platform == "win32":
        pyw = Path(py).with_name("pythonw.exe")
        if pyw.exists():
            py = str(pyw)
    return [py, "-m", "remote_control.app", "--minimized"]


def _quote_win(args: list[str]) -> str:
    return subprocess.list2cmdline(args)


def _mac_plist() -> Path:
    return Path.home() / "Library/LaunchAgents/com.pocketdesk.app.plist"


def _linux_desktop() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "autostart/pocketdesk.desktop"


def autostart_enabled() -> bool:
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
                winreg.QueryValueEx(k, APP_NAME)
            return True
        except OSError:
            return False
    if sys.platform == "darwin":
        return _mac_plist().exists()
    return _linux_desktop().exists()


_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def set_autostart(enabled: bool) -> None:
    cmd = launch_command()
    if sys.platform == "win32":
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enabled:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, _quote_win(cmd))
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except FileNotFoundError:
                    pass
        return

    if sys.platform == "darwin":
        path = _mac_plist()
        if not enabled:
            path.unlink(missing_ok=True)
            return
        args = "".join(f"<string>{a}</string>" for a in cmd)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0"><dict>'
            "<key>Label</key><string>com.pocketdesk.app</string>"
            f"<key>ProgramArguments</key><array>{args}</array>"
            "<key>RunAtLoad</key><true/>"
            "</dict></plist>\n"
        )
        return

    path = _linux_desktop()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    exec_line = " ".join(f'"{a}"' for a in cmd)
    path.write_text(
        "[Desktop Entry]\nType=Application\nName=PocketDesk\n"
        f"Exec={exec_line}\nX-GNOME-Autostart-enabled=true\n"
    )


# --------------------------------------------------------------------------
# スリープ防止 (スマホが接続している間だけ)
# --------------------------------------------------------------------------
class KeepAwake:
    """set(True) でスリープ防止、set(False) で解除。

    Windows の SetThreadExecutionState は呼んだスレッド単位で効くため、
    常に同じスレッド (サーバーのイベントループ) から呼ぶこと。
    """

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self.active = False

    def set(self, on: bool) -> None:
        if on == self.active:
            return
        self.active = on
        if sys.platform == "win32":
            import ctypes

            ES_CONTINUOUS, ES_SYSTEM_REQUIRED, ES_DISPLAY_REQUIRED = 0x80000000, 0x1, 0x2
            flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED if on else 0)
            ctypes.windll.kernel32.SetThreadExecutionState(flags)
        elif sys.platform == "darwin":
            if on:
                self._proc = subprocess.Popen(["caffeinate", "-d", "-i"])
            elif self._proc:
                self._proc.terminate()
                self._proc = None
        # Linux はデスクトップ環境ごとに違うので未対応
