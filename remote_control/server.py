"""PC側で動かすリモートコントロールサーバー。

画面をJPEGでWebSocket配信し、スマホ/別PCのブラウザから届いた
マウス・キーボード操作をこのPCに反映する。
"""

from __future__ import annotations

import argparse
import asyncio
import hmac
import io
import json
import logging
import sys
import threading
from pathlib import Path

from aiohttp import WSMsgType, web

log = logging.getLogger("remote_control")
if getattr(sys, "frozen", False):  # PyInstaller で exe 化されたとき
    STATIC_DIR = Path(sys._MEIPASS) / "remote_control" / "static"
else:
    STATIC_DIR = Path(__file__).parent / "static"


# --------------------------------------------------------------------------
# 画面キャプチャ / 入力 (重いライブラリは遅延 import してテストしやすくする)
# --------------------------------------------------------------------------
class Screen:
    def __init__(self, monitor: int, max_width: int, quality: int):
        import mss  # noqa: WPS433

        self._sct = mss.mss()
        self.monitor = self._sct.monitors[monitor]
        self.max_width = max_width
        self.quality = quality

    def grab_jpeg(self) -> bytes:
        from PIL import Image

        shot = self._sct.grab(self.monitor)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        if img.width > self.max_width:
            h = round(img.height * self.max_width / img.width)
            img = img.resize((self.max_width, h), Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=self.quality)
        return buf.getvalue()


class Input:
    """ブラウザから来た正規化座標 (0..1) を実画面座標に変換して操作する。"""

    def __init__(self, monitor: dict):
        import pyautogui

        pyautogui.FAILSAFE = False  # 角をタップしても止まらないように
        pyautogui.PAUSE = 0
        self.g = pyautogui
        # pyautogui は論理座標(Retina等のスケーリング後)で動くので比率で合わせる
        sw, sh = pyautogui.size()
        self.sx = sw / self._phys_size(monitor)[0]
        self.sy = sh / self._phys_size(monitor)[1]
        self.mon = monitor

    @staticmethod
    def _phys_size(m: dict) -> tuple[int, int]:
        return m["width"], m["height"]

    def _xy(self, ev: dict) -> tuple[int, int]:
        x = self.mon["left"] + float(ev["x"]) * self.mon["width"]
        y = self.mon["top"] + float(ev["y"]) * self.mon["height"]
        return round(x * self.sx), round(y * self.sy)

    def handle(self, ev: dict) -> None:
        t = ev.get("t")
        btn = ev.get("button", "left")
        if btn not in ("left", "right", "middle"):
            return
        if t == "move":
            self.g.moveTo(*self._xy(ev))
        elif t == "click":
            self.g.click(*self._xy(ev), button=btn, clicks=int(ev.get("n", 1)))
        elif t == "down":
            self.g.mouseDown(*self._xy(ev), button=btn)
        elif t == "up":
            self.g.mouseUp(*self._xy(ev), button=btn)
        elif t == "scroll":
            self.g.scroll(int(ev.get("dy", 0)))
        elif t == "key":
            key = str(ev.get("key", ""))
            mods = [m for m in ev.get("mods", []) if m in ("ctrl", "alt", "shift", "win", "command")]
            if key in self.g.KEYBOARD_KEYS:
                self.g.hotkey(*mods, key) if mods else self.g.press(key)
        elif t == "text":
            text = str(ev.get("text", ""))[:1000]
            if text.isascii():
                self.g.write(text)
            else:
                # 日本語などはクリップボード経由で貼り付け
                _paste_text(self.g, text)


def _paste_text(g, text: str) -> None:
    try:
        import pyperclip

        pyperclip.copy(text)
        g.hotkey("command" if sys.platform == "darwin" else "ctrl", "v")
    except Exception:  # pragma: no cover - 環境依存
        log.warning("非ASCII文字の入力には pyperclip が必要です")


# --------------------------------------------------------------------------
# Web サーバー
# --------------------------------------------------------------------------
def create_app(
    token: str, screen_factory, input_factory, fps: float, on_clients_changed=None
) -> web.Application:
    """on_clients_changed(n): 接続数が変わるたびにイベントループのスレッドで呼ばれる。"""
    app = web.Application()
    clients = [0]

    def changed(delta: int) -> None:
        clients[0] += delta
        if on_clients_changed:
            try:
                on_clients_changed(clients[0])
            except Exception as e:  # noqa: BLE001
                log.warning("on_clients_changed エラー: %s", e)

    def authorized(request: web.Request) -> bool:
        given = request.query.get("token", "")
        return hmac.compare_digest(given.encode(), token.encode())

    async def index(request: web.Request) -> web.StreamResponse:
        return web.FileResponse(STATIC_DIR / "index.html")

    async def ws_handler(request: web.Request) -> web.StreamResponse:
        if not authorized(request):
            raise web.HTTPUnauthorized(text="invalid token")
        ws = web.WebSocketResponse(heartbeat=20, max_msg_size=64 * 1024)
        await ws.prepare(request)
        log.info("接続: %s", request.remote)
        changed(+1)

        screen = screen_factory()
        inp = input_factory(screen.monitor)
        ready = asyncio.Event()
        ready.set()
        loop = asyncio.get_running_loop()

        async def sender() -> None:
            interval = 1.0 / fps
            while not ws.closed:
                await ready.wait()  # 前フレームが描画されるまで待つ(遅延蓄積防止)
                ready.clear()
                frame = await loop.run_in_executor(None, screen.grab_jpeg)
                await ws.send_bytes(frame)
                await asyncio.sleep(interval)

        task = asyncio.create_task(sender())
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    ev = json.loads(msg.data)
                except ValueError:
                    continue
                if ev.get("t") == "ack":
                    ready.set()
                    continue
                try:
                    await loop.run_in_executor(None, inp.handle, ev)
                except Exception as e:  # 不正な入力で落ちないように
                    log.warning("入力エラー %s: %s", ev, e)
        finally:
            task.cancel()
            changed(-1)
            log.info("切断: %s", request.remote)
        return ws

    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_static("/static", STATIC_DIR)
    return app


class ServerThread:
    """別スレッドでサーバーを動かす (GUIアプリ用)。"""

    def __init__(self, app: web.Application, host: str, port: int):
        self.app, self.host, self.port = app, host, port
        self.loop = asyncio.new_event_loop()
        self.started = threading.Event()
        self.error: BaseException | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self, timeout: float = 10) -> None:
        self._thread.start()
        self.started.wait(timeout)
        if self.error:
            raise self.error

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        runner = web.AppRunner(self.app)
        try:
            self.loop.run_until_complete(runner.setup())
            site = web.TCPSite(runner, self.host, self.port)
            self.loop.run_until_complete(site.start())
        except BaseException as e:  # noqa: BLE001 (ポート使用中など)
            self.error = e
            self.started.set()
            return
        self.started.set()
        self.loop.run_forever()
        self.loop.run_until_complete(runner.cleanup())

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=5)


def print_qr(url: str) -> None:
    try:
        import qrcode

        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.print_ascii(invert=True)
    except ImportError:
        print("(pip install qrcode で、ここにQRコードが表示されます)")


def main() -> None:
    """コマンドライン版 (python -m remote_control)。"""
    from . import netinfo, system
    from .config import Config, new_token

    cfg = Config.load()
    p = argparse.ArgumentParser(description="スマホ/PCからこのPCを操作するリモートコントロール")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=cfg.port)
    p.add_argument("--token", help="合言葉を一時的に上書き")
    p.add_argument("--new-token", action="store_true", help="合言葉を作り直して保存")
    p.add_argument("--monitor", type=int, default=cfg.monitor, help="モニタ番号 (1=メイン)")
    p.add_argument("--fps", type=float, default=cfg.fps)
    p.add_argument("--max-width", type=int, default=cfg.max_width, help="配信画像の最大幅")
    p.add_argument("--quality", type=int, default=cfg.quality, help="JPEG品質 (1-95)")
    p.add_argument("--show-url", action="store_true", help="接続URLを表示して終了")
    p.add_argument("--install-autostart", action="store_true", help="PC起動時に自動起動 (アプリ版)")
    p.add_argument("--uninstall-autostart", action="store_true", help="自動起動を解除")
    a = p.parse_args()

    if a.new_token:
        cfg.token = new_token()
        cfg.save()
        print("合言葉を作り直しました。古いURLはもう使えません。")
    if a.install_autostart or a.uninstall_autostart:
        system.set_autostart(a.install_autostart)
        print("自動起動を" + ("登録しました" if a.install_autostart else "解除しました"))
    token = a.token or cfg.token

    lan = netinfo.make_url(netinfo.lan_ip(), a.port, token)
    ts_ip = netinfo.tailscale_ip()
    ts = netinfo.make_url(ts_ip, a.port, token) if ts_ip else None
    print("=" * 64)
    print(f" 家のWi-Fi : {lan}")
    print(f" 外出先    : {ts}" if ts else " 外出先    : (Tailscale 未検出)")
    print("=" * 64)
    print_qr(ts or lan)
    if a.show_url or a.install_autostart or a.uninstall_autostart:
        return

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    awake = system.KeepAwake()
    app = create_app(
        token,
        screen_factory=lambda: Screen(a.monitor, a.max_width, a.quality),
        input_factory=Input,
        fps=a.fps,
        on_clients_changed=(lambda n: awake.set(n > 0)) if cfg.keep_awake else None,
    )
    web.run_app(app, host=a.host, port=a.port, print=None)


if __name__ == "__main__":
    main()
