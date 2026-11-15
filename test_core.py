import hashlib, hmac, json, time
from io import BytesIO
from urllib.parse import urlencode

import pytest
from PIL import Image

from app.imaging import ImageError, process_image
from app.report import build_report
from app.security import AuthError, MetaError, RateLimiter, safe_meta, verify_init_data

TOKEN = "123:TESTTOKEN"


def sign(user=None, auth_date=None, token=TOKEN):
    d = {"auth_date": str(int(auth_date or time.time())), "query_id": "AAA",
         "user": json.dumps(user or {"id": 42, "first_name": "T", "language_code": "bn"})}
    check = "\n".join(f"{k}={v}" for k, v in sorted(d.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    d["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(d)


def png_bytes(size=(64, 48), fmt="PNG"):
    b = BytesIO(); Image.new("RGB", size, (10, 120, 80)).save(b, fmt); return b.getvalue()


# ---- auth
def test_auth_ok():
    assert verify_init_data(sign(), TOKEN)["id"] == 42

def test_auth_bad_signature():
    with pytest.raises(AuthError): verify_init_data(sign(token="9:OTHER"), TOKEN)

def test_auth_tampered():
    with pytest.raises(AuthError): verify_init_data(sign().replace("42", "43"), TOKEN)

def test_auth_expired():
    with pytest.raises(AuthError): verify_init_data(sign(auth_date=time.time() - 7200), TOKEN, 3600)

def test_auth_missing():
    with pytest.raises(AuthError): verify_init_data("", TOKEN)


# ---- metadata
def test_meta_filters_unknown_and_types():
    m = safe_meta(json.dumps({"language": "bn", "evil": "x", "pixelRatio": 2, "languages": ["a"] * 9,
                              "userAgent": "u" * 999, "deviceMemory": {"x": 1}}))
    assert "evil" not in m and "deviceMemory" not in m
    assert len(m["languages"]) == 5 and len(m["userAgent"]) == 300

def test_meta_rejects_bad():
    for raw in ("not json", "[1]", "x" * 9000):
        with pytest.raises(MetaError): safe_meta(raw)

def test_meta_nan_dropped():
    assert "pixelRatio" not in safe_meta('{"pixelRatio": NaN}')


# ---- rate limit
def test_rate_limiter():
    r = RateLimiter(2, 60)
    assert r.allow(1, 0) and r.allow(1, 1) and not r.allow(1, 2)
    assert r.allow(2, 2) and r.allow(1, 61)


# ---- images
def test_image_reencoded_and_resized():
    out, size, orig = process_image(png_bytes((4000, 1000)), 1000)
    assert max(size) == 1000 and orig == (4000, 1000)
    assert Image.open(BytesIO(out)).format == "JPEG"

def test_image_exif_stripped():
    im = Image.new("RGB", (50, 50)); ex = Image.Exif(); ex[0x010F] = "SecretCam"
    b = BytesIO(); im.save(b, "JPEG", exif=ex)
    out, *_ = process_image(b.getvalue())
    assert not Image.open(BytesIO(out)).getexif()

def test_image_invalid():
    with pytest.raises(ImageError): process_image(b"not an image")
    with pytest.raises(ImageError): process_image(png_bytes(fmt="BMP"))


# ---- report
def test_report_modes():
    meta = {"capturedAt": "t", "platform": "Android", "userAgent": "UA"}
    full = build_report(meta, 10, 20, 2048, "image/jpeg", "en", True)
    mini = build_report(meta, 10, 20, 2048, "image/jpeg", "en", False)
    assert "Android" in full and "Android" not in mini and "10 × 20" in mini
    assert "রিপোর্ট" in build_report(meta, 1, 1, 1, "image/jpeg", "bn", True)
