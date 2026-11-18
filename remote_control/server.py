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
import secrets
import socket
from pathlib import Path

from aiohttp import WSMsgType, web

log = logging.getLogger("remote_control")
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
        import sys

        g.hotkey("command" if sys.platform == "darwin" else "ctrl", "v")
    except Exception:  # pragma: no cover - 環境依存
        log.warning("非ASCII文字の入力には pyperclip が必要です")


# --------------------------------------------------------------------------
# Web サーバー
# --------------------------------------------------------------------------
def create_app(token: str, screen_factory, input_factory, fps: float) -> web.Application:
    app = web.Application()

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
            log.info("切断: %s", request.remote)
        return ws

    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_static("/static", STATIC_DIR)
    return app


def local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def print_qr(url: str) -> None:
    try:
        import qrcode

        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.print_ascii(invert=True)
    except ImportError:
        print("(pip install qrcode で、ここにQRコードが表示されます)")


def main() -> None:
    p = argparse.ArgumentParser(description="スマホ/PCからこのPCを操作するリモートコントロール")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--token", help="接続用トークン (省略時はランダム生成)")
    p.add_argument("--monitor", type=int, default=1, help="キャプチャするモニタ番号 (1=メイン)")
    p.add_argument("--fps", type=float, default=15)
    p.add_argument("--max-width", type=int, default=1280, help="配信画像の最大幅")
    p.add_argument("--quality", type=int, default=60, help="JPEG品質 (1-95)")
    a = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    token = a.token or secrets.token_urlsafe(16)
    url = f"http://{local_ip()}:{a.port}/#token={token}"

    print("=" * 60)
    print(" リモートコントロール起動")
    print(f" スマホ/別PCのブラウザで開く: {url}")
    print("=" * 60)
    print_qr(url)

    app = create_app(
        token,
        screen_factory=lambda: Screen(a.monitor, a.max_width, a.quality),
        input_factory=Input,
        fps=a.fps,
    )
    web.run_app(app, host=a.host, port=a.port, print=None)


if __name__ == "__main__":
    main()
