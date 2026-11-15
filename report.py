"""Builds the text report sent to the user's own chat."""
from __future__ import annotations

from .i18n import t


def build_report(meta: dict, w: int, h: int, size: int, mime: str, lang: str, detailed: bool) -> str:
    def g(k, default=None):
        v = meta.get(k)
        return (default if default is not None else t(lang, "rep_na")) if v in (None, "", []) else str(v)

    nosup = t(lang, "rep_nosup")
    lines = [t(lang, "rep_title"), "━━━━━━━━━━━━━━━━━━━━",
             f"{t(lang, 'rep_captured')}: {g('capturedAt')}"]
    if detailed:
        lines += [
            f"{t(lang, 'rep_platform')}: {g('platform')}",
            f"{t(lang, 'rep_browser')}: {g('userAgent')}",
            f"{t(lang, 'rep_lang')}: {g('language')}",
            f"{t(lang, 'rep_tz')}: {g('timezone')}",
            f"{t(lang, 'rep_screen')}: {g('screenWidth')} × {g('screenHeight')}",
            f"{t(lang, 'rep_viewport')}: {g('viewportWidth')} × {g('viewportHeight')}",
            f"{t(lang, 'rep_dpr')}: {g('pixelRatio')}",
            f"{t(lang, 'rep_cpu')}: {g('hardwareConcurrency')}",
            f"{t(lang, 'rep_mem')}: {g('deviceMemory')}",
            f"{t(lang, 'rep_batt')}: {g('batteryLevel', nosup)}",
            f"{t(lang, 'rep_chg')}: {g('batteryCharging', nosup)}",
        ]
    lines += [
        "━━━━━━━━━━━━━━━━━━━━",
        f"{t(lang, 'rep_img')}: {w} × {h}",
        f"{t(lang, 'rep_fmt')}: {mime}",
        f"{t(lang, 'rep_size')}: {size / 1024:.1f} KB",
        f"{t(lang, 'rep_cam')}: {g('cameraFacing')}",
        t(lang, "rep_foot") if detailed else t(lang, "rep_min"),
    ]
    return "\n".join(lines)[:3900]
