"""ダブルクリックで起動するアプリ版 (exe のエントリーポイント)。

窓にQRコードと接続URLを表示し、裏でサーバーを動かす。
"""

from __future__ import annotations

import argparse
import logging
import sys
import tkinter as tk
import tkinter.font
import urllib.request
from tkinter import messagebox, ttk

from . import netinfo, system
from .config import Config, config_dir, new_token
from .server import Input, Screen, ServerThread, create_app

QUALITY_PRESETS = {
    "高画質": dict(max_width=1920, quality=75, fps=20),
    "標準": dict(max_width=1280, quality=60, fps=15),
    "軽量 (モバイル回線向け)": dict(max_width=960, quality=45, fps=10),
}


def setup_logging() -> None:
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=d / "log.txt",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )


class App:
    def __init__(self, root: tk.Tk, cfg: Config):
        self.root, self.cfg = root, cfg
        self.clients = 0
        self.awake = system.KeepAwake()
        self.server: ServerThread | None = None

        root.title("PocketDesk")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        if sys.platform == "win32":
            for name in ("TkDefaultFont", "TkTextFont"):
                tkinter.font.nametofont(name).configure(family="Yu Gothic UI", size=10)

        pad = dict(padx=12, pady=4)
        self.status = ttk.Label(root, text="起動中…", font=("", 12, "bold"))
        self.status.pack(**pad, anchor="w")

        # 接続先の切り替え
        self.target = tk.StringVar(value="ts")
        row = ttk.Frame(root)
        row.pack(**pad, anchor="w")
        ttk.Radiobutton(row, text="外出先 (Tailscale)", value="ts", variable=self.target,
                        command=self.refresh_url).pack(side="left")
        ttk.Radiobutton(row, text="家のWi-Fi", value="lan", variable=self.target,
                        command=self.refresh_url).pack(side="left", padx=8)

        self.qr_label = ttk.Label(root)
        self.qr_label.pack(padx=12, pady=6)
        self.hint = ttk.Label(root, text="スマホのカメラでQRコードを読み取ってください", foreground="#666")
        self.hint.pack()

        self.url_var = tk.StringVar()
        url_row = ttk.Frame(root)
        url_row.pack(fill="x", **pad)
        ttk.Entry(url_row, textvariable=self.url_var, state="readonly", width=46).pack(side="left", fill="x", expand=True)
        ttk.Button(url_row, text="コピー", command=self.copy_url).pack(side="left", padx=(6, 0))

        ttk.Separator(root).pack(fill="x", pady=8)

        # 設定
        opts = ttk.Frame(root)
        opts.pack(fill="x", **pad)
        self.autostart_var = tk.BooleanVar(value=self._safe(system.autostart_enabled, False))
        ttk.Checkbutton(opts, text="PCの起動時に自動で起動する", variable=self.autostart_var,
                        command=self.toggle_autostart).pack(anchor="w")
        self.awake_var = tk.BooleanVar(value=cfg.keep_awake)
        ttk.Checkbutton(opts, text="スマホ接続中はPCをスリープさせない", variable=self.awake_var,
                        command=self.toggle_awake).pack(anchor="w")

        qrow = ttk.Frame(opts)
        qrow.pack(anchor="w", pady=(6, 0))
        ttk.Label(qrow, text="画質:").pack(side="left")
        self.quality_var = tk.StringVar(value=self._current_preset())
        cb = ttk.Combobox(qrow, textvariable=self.quality_var, values=list(QUALITY_PRESETS),
                          state="readonly", width=22)
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self.change_quality())

        btns = ttk.Frame(root)
        btns.pack(fill="x", padx=12, pady=(8, 12))
        ttk.Button(btns, text="合言葉を作り直す", command=self.regen_token).pack(side="left")
        ttk.Button(btns, text="終了", command=self.on_close).pack(side="right")

        self.start_server()
        self.refresh_url()
        self.poll()

    # ---------------- サーバー ----------------
    def start_server(self) -> None:
        cfg = self.cfg
        app = create_app(
            cfg.token,
            # 画質は接続のたびに最新の設定を読む
            screen_factory=lambda: Screen(cfg.monitor, cfg.max_width, cfg.quality),
            input_factory=Input,
            fps=cfg.fps,
            on_clients_changed=self._on_clients,
        )
        self.server = ServerThread(app, "0.0.0.0", cfg.port)
        try:
            self.server.start()
        except OSError as e:
            logging.exception("サーバー起動失敗")
            messagebox.showerror(
                "PocketDesk",
                f"ポート {cfg.port} を使えませんでした。\nすでに起動していませんか？\n\n{e}",
            )
            self.root.destroy()
            raise SystemExit(1)

    def _on_clients(self, n: int) -> None:
        # サーバーのスレッドで呼ばれる (スリープ防止はこのスレッドで設定する必要がある)
        self.clients = n
        self.awake.set(n > 0 and self.cfg.keep_awake)

    def poll(self) -> None:
        if self.clients:
            self.status.configure(text=f"● 操作中 ({self.clients}台接続)", foreground="#16a34a")
        else:
            self.status.configure(text="○ 待機中 (接続を待っています)", foreground="#555")
        self.root.after(500, self.poll)

    # ---------------- URL / QR ----------------
    def current_url(self) -> str:
        ip = None
        if self.target.get() == "ts":
            ip = netinfo.tailscale_ip()
            if not ip:
                self.hint.configure(text="Tailscale が見つかりません。PCとスマホに入れて同じアカウントでログインしてください")
                return ""
        self.hint.configure(text="スマホのカメラでQRコードを読み取ってください")
        return netinfo.make_url(ip or netinfo.lan_ip(), self.cfg.port, self.cfg.token)

    def refresh_url(self) -> None:
        url = self.current_url()
        self.url_var.set(url)
        if not url:
            self.qr_label.configure(image="", text="(QRコードなし)")
            return
        try:
            import qrcode
            from PIL import ImageTk

            img = qrcode.make(url, box_size=6, border=2)
            pil = img.get_image() if hasattr(img, "get_image") else img
            self._qr_photo = ImageTk.PhotoImage(pil.convert("RGB"))
            self.qr_label.configure(image=self._qr_photo, text="")
        except Exception:  # noqa: BLE001
            logging.exception("QR生成失敗")
            self.qr_label.configure(image="", text="(QRコードを表示できませんでした)")

    def copy_url(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(self.url_var.get())

    # ---------------- 設定 ----------------
    def toggle_autostart(self) -> None:
        try:
            system.set_autostart(self.autostart_var.get())
        except OSError as e:
            messagebox.showerror("PocketDesk", f"自動起動の設定に失敗しました\n{e}")
            self.autostart_var.set(not self.autostart_var.get())

    def toggle_awake(self) -> None:
        self.cfg.keep_awake = self.awake_var.get()
        self.cfg.save()
        loop = self.server.loop
        loop.call_soon_threadsafe(lambda: self.awake.set(self.clients > 0 and self.cfg.keep_awake))

    def _current_preset(self) -> str:
        for name, p in QUALITY_PRESETS.items():
            if p["max_width"] == self.cfg.max_width and p["quality"] == self.cfg.quality:
                return name
        return "標準"

    def change_quality(self) -> None:
        for k, v in QUALITY_PRESETS[self.quality_var.get()].items():
            setattr(self.cfg, k, v)
        self.cfg.save()
        self.restart_server()  # FPS を反映するため (接続中のスマホは自動で再接続される)

    def regen_token(self) -> None:
        if not messagebox.askyesno(
            "PocketDesk",
            "合言葉を作り直すと、今までのURLでは接続できなくなります。\nスマホでもう一度QRコードを読み取る必要があります。\n\n作り直しますか？",
        ):
            return
        self.cfg.token = new_token()
        self.cfg.save()
        self.restart_server()
        self.refresh_url()

    def restart_server(self) -> None:
        if self.server:
            self.server.stop()
        self.start_server()

    def on_close(self) -> None:
        if self.clients and not messagebox.askyesno(
            "PocketDesk", "スマホが接続中です。終了すると操作できなくなります。終了しますか？"
        ):
            return
        if self.server:
            self.server.loop.call_soon_threadsafe(lambda: self.awake.set(False))
            self.server.stop()
        self.root.destroy()

    @staticmethod
    def _safe(fn, default):
        try:
            return fn()
        except Exception:  # noqa: BLE001
            return default


def selftest(out_path: str) -> int:
    """CI用: 窓を作ってサーバーを起動し、ページが取れるか確認して結果をファイルに書く。"""
    import tempfile
    from pathlib import Path

    from . import config as config_mod

    tmp = Path(tempfile.mkdtemp())
    config_mod.config_dir = lambda: tmp  # 本物の設定を汚さない
    result = "FAIL"
    try:
        root = tk.Tk()
        cfg = Config.load(tmp / "config.json")
        cfg.port = 8799
        app = App(root, cfg)
        root.update()
        html = urllib.request.urlopen(f"http://127.0.0.1:{cfg.port}/", timeout=5).read().decode()
        shot = Screen(1, 640, 50).grab_jpeg()
        ok = "PocketDesk" in html and shot[:2] == b"\xff\xd8"
        result = "OK" if ok else "FAIL: unexpected response"
        app.server.stop()
        root.destroy()
    except Exception as e:  # noqa: BLE001
        result = f"FAIL: {type(e).__name__}: {e}"
    Path(out_path).write_text(result, encoding="utf-8")
    return 0 if result == "OK" else 1


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--minimized", action="store_true", help="最小化して起動 (自動起動用)")
    p.add_argument("--selftest", metavar="OUT", help=argparse.SUPPRESS)
    a = p.parse_args()

    if a.selftest:
        raise SystemExit(selftest(a.selftest))

    setup_logging()
    root = tk.Tk()
    App(root, Config.load())
    if a.minimized:
        root.iconify()
    root.mainloop()


if __name__ == "__main__":
    main()
