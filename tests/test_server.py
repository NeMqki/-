import asyncio
import json

import pytest
from aiohttp.test_utils import TestClient, TestServer

from remote_control.server import create_app


class FakeScreen:
    monitor = {"left": 0, "top": 0, "width": 100, "height": 100}

    def grab_jpeg(self):
        return b"\xff\xd8fake"


class FakeInput:
    events = []

    def __init__(self, monitor):
        pass

    def handle(self, ev):
        FakeInput.events.append(ev)


@pytest.fixture
async def client():
    app = create_app("secret", FakeScreen, FakeInput, fps=100)
    async with TestClient(TestServer(app)) as c:
        yield c


async def test_rejects_bad_token(client):
    resp = await client.get("/ws?token=wrong")
    assert resp.status == 401


async def test_index(client):
    resp = await client.get("/")
    assert resp.status == 200
    assert "Remote Control" in await resp.text()


async def test_frames_and_input(client):
    FakeInput.events.clear()
    ws = await client.ws_connect("/ws?token=secret")
    msg = await ws.receive(timeout=2)
    assert msg.data == b"\xff\xd8fake"
    await ws.send_str(json.dumps({"t": "ack"}))
    msg = await ws.receive(timeout=2)
    assert msg.data.startswith(b"\xff\xd8")
    await ws.send_str(json.dumps({"t": "click", "x": 0.5, "y": 0.5}))
    await ws.send_str("not json")
    for _ in range(20):
        if FakeInput.events:
            break
        await asyncio.sleep(0.05)
    assert FakeInput.events == [{"t": "click", "x": 0.5, "y": 0.5}]
    await ws.close()
