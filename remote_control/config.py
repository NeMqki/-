"""設定ファイル (合言葉・ポート・画質など) の読み書き。"""

from __future__ import annotations

import json
import os
import secrets
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path


def config_dir() -> Path:
    if sys.platform == "win32" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "PocketDesk"
    return Path.home() / ".pocketdesk"


def new_token() -> str:
    return secrets.token_urlsafe(16)


@dataclass
class Config:
    token: str = ""
    port: int = 8765
    fps: float = 15
    max_width: int = 1280
    quality: int = 60
    monitor: int = 1
    keep_awake: bool = True

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        path = path or config_dir() / "config.json"
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
        known = {f.name for f in fields(cls)}
        cfg = cls(**{k: v for k, v in data.items() if k in known})
        if not cfg.token:
            cfg.token = new_token()
            cfg.save(path)
        return cfg

    def save(self, path: Path | None = None) -> None:
        path = path or config_dir() / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
