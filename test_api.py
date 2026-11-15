import json, time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import create_api
from app.config import Settings
from tests.test_core import TOKEN, png_bytes, sign

S = Settings(bot_token=TOKEN, database_url="x", webapp_url="https://x.example", daily_limit=2, minute_limit=50)


class FakeDB:
    def __init__(self): self.rows = []; self.detailed = True
    async def ping(self): return True
    async def upsert_user(self, *a): return {"lang": "en", "detailed": self.detailed}
    async def today_count(self, uid): return len(self.rows)
    async def add_capture(self, uid, fid, mime, size, meta, pm, rm):
        self.rows.append((uid, fid, meta)); return len(self.rows)


class FakeBot:
    def __init__(self): self.sent = []
    async def send_photo(self, uid, f, caption=None):
        self.sent.append(("photo", f.data))
        return SimpleNamespace(message_id=1, photo=[SimpleNamespace(file_id="FID")])
    async def send_message(self, uid, text):
        self.sent.append(("msg", text)); return SimpleNamespace(message_id=2)


@pytest.fixture
def env():
    db, bot = FakeDB(), FakeBot()
    return TestClient(create_api(S, db, bot)), db, bot


def post(client, meta=None, img=None, ctype="image/png", init=None):
    return client.post("/api/capture",
                       files={"photo": ("c.png", img or png_bytes(), ctype)},
                       data={"metadata": json.dumps(meta or {"platform": "Android", "capturedAt": "now"})},
                       headers={"X-Telegram-Init-Data": init if init is not None else sign()})


def test_health_and_headers(env):
    c, *_ = env
    r = c.get("/healthz"); assert r.status_code == 200
    assert "frame-ancestors" in r.headers["content-security-policy"]
    assert c.get("/").status_code == 200
    assert c.get("/static/app.js").status_code == 200

def test_requires_auth(env):
    c, *_ = env
    assert post(c, init="").status_code == 401
    assert post(c, init="hash=bad").status_code == 401

def test_happy_path(env):
    c, db, bot = env
    r = post(c); assert r.status_code == 200, r.text
    assert r.json()["remaining"] == 1
    assert bot.sent[0][0] == "photo" and bot.sent[0][1][:2] == b"\xff\xd8"   # JPEG re-encoded
    assert "Android" in bot.sent[1][1]

def test_minimal_pref(env):
    c, db, bot = env; db.detailed = False
    assert post(c).status_code == 200
    assert "Android" not in bot.sent[1][1] and "platform" not in db.rows[0][2]

def test_daily_limit(env):
    c, *_ = env
    assert post(c).status_code == 200 and post(c).status_code == 200
    assert post(c).status_code == 429

def test_bad_type_and_image(env):
    c, *_ = env
    assert post(c, ctype="text/plain").status_code == 415
    assert post(c, img=b"garbage").status_code == 400

def test_config_endpoint(env):
    c, *_ = env
    r = c.get("/api/config", headers={"X-Telegram-Init-Data": sign()})
    assert r.status_code == 200 and r.json()["remaining"] == 2
