import json

from remote_control import netinfo
from remote_control.config import Config


def test_config_creates_and_reuses_token(tmp_path):
    path = tmp_path / "config.json"
    a = Config.load(path)
    assert a.token and path.exists()
    b = Config.load(path)
    assert b.token == a.token


def test_config_ignores_unknown_and_broken(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"token": "abc", "port": 9000, "junk": 1}))
    c = Config.load(path)
    assert (c.token, c.port) == ("abc", 9000)
    path.write_text("{broken")
    assert Config.load(path).token


def test_tailscale_range():
    assert netinfo._is_tailscale("100.101.102.103")
    assert not netinfo._is_tailscale("192.168.1.10")
    assert not netinfo._is_tailscale("100.200.0.1")


def test_make_url():
    assert netinfo.make_url("1.2.3.4", 8765, "t") == "http://1.2.3.4:8765/#token=t"
