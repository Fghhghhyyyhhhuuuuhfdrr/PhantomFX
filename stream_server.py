"""
bot/utils/stream_server.py
Lightweight aiohttp web-server that proxies Telegram file chunks
to the client's browser, enabling in-browser streaming and fast
direct-download links without downloading the file to the VPS.

Works with files up to 4 GB via the local Telegram Bot API server,
or up to 2 GB via the standard Bot API (which supports chunked transfers).

Route:
  GET /stream/<token>         → HTML5 video player page
  GET /dl/<token>             → force-download (Content-Disposition: attachment)
  GET /file/<token>?r=<range> → raw bytes proxy (used by both above)
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Optional

from aiohttp import web, ClientSession, ClientTimeout
import aiohttp

from config.config import (
    BOT_TOKEN, STREAM_BASE_URL, PORT,
    USE_LOCAL_API, LOCAL_API_URL,
)

log = logging.getLogger(__name__)

# ── Simple HMAC-based token so only the bot can mint links ──────────────────
_SECRET = BOT_TOKEN.encode() if BOT_TOKEN else b"changeme"


def _make_token(file_id: str, file_size: int) -> str:
    payload = json.dumps({"fid": file_id, "sz": file_size, "ts": int(time.time())})
    b64 = base64.urlsafe_b64encode(payload.encode()).decode()
    sig = hmac.new(_SECRET, b64.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{b64}.{sig}"


def _verify_token(token: str) -> Optional[dict]:
    try:
        b64, sig = token.rsplit(".", 1)
        expected = hmac.new(_SECRET, b64.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected):
            return None
        return json.loads(base64.urlsafe_b64decode(b64 + "=="))
    except Exception:
        return None


def make_stream_url(file_id: str, file_size: int) -> str:
    return f"{STREAM_BASE_URL}/stream/{_make_token(file_id, file_size)}"


def make_download_url(file_id: str, file_size: int) -> str:
    return f"{STREAM_BASE_URL}/dl/{_make_token(file_id, file_size)}"


# ── Telegram API base ────────────────────────────────────────────────────────
def _api_base() -> str:
    if USE_LOCAL_API:
        return LOCAL_API_URL
    return "https://api.telegram.org"


async def _get_file_path(file_id: str) -> Optional[str]:
    url = f"{_api_base()}/bot{BOT_TOKEN}/getFile?file_id={file_id}"
    async with ClientSession(timeout=ClientTimeout(total=10)) as session:
        async with session.get(url) as r:
            data = await r.json()
            if data.get("ok"):
                return data["result"]["file_path"]
    return None


# ── Route handlers ───────────────────────────────────────────────────────────

async def _proxy_file(request: web.Request, download: bool = False) -> web.StreamResponse:
    token = request.match_info["token"]
    payload = _verify_token(token)
    if not payload:
        raise web.HTTPForbidden(reason="Invalid or expired link")

    file_id   = payload["fid"]
    file_size = payload["sz"]

    file_path = await _get_file_path(file_id)
    if not file_path:
        raise web.HTTPNotFound(reason="Could not resolve file")

    if USE_LOCAL_API:
        # Local API returns an absolute path
        file_url = f"{LOCAL_API_URL}/file/bot{BOT_TOKEN}/{file_path}"
    else:
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"

    range_header = request.headers.get("Range", "")
    req_headers  = {}
    if range_header:
        req_headers["Range"] = range_header

    disposition = "attachment" if download else "inline"
    filename    = file_path.split("/")[-1]

    async with ClientSession() as session:
        async with session.get(file_url, headers=req_headers) as upstream:
            status = upstream.status  # 200 or 206

            resp = web.StreamResponse(
                status=status,
                headers={
                    "Content-Type":        upstream.headers.get("Content-Type", "video/mp4"),
                    "Content-Length":      upstream.headers.get("Content-Length", str(file_size)),
                    "Content-Range":       upstream.headers.get("Content-Range", ""),
                    "Accept-Ranges":       "bytes",
                    "Content-Disposition": f'{disposition}; filename="{filename}"',
                    "Cache-Control":       "no-cache",
                },
            )
            await resp.prepare(request)

            # Stream in 512 KB chunks
            async for chunk in upstream.content.iter_chunked(524288):
                await resp.write(chunk)

            await resp.write_eof()
            return resp


async def handle_stream(request: web.Request) -> web.StreamResponse:
    return await _proxy_file(request, download=False)


async def handle_download(request: web.Request) -> web.StreamResponse:
    return await _proxy_file(request, download=True)


async def handle_player(request: web.Request) -> web.Response:
    """Serve a minimal HTML5 video player page."""
    token = request.match_info["token"]
    raw_url = f"{STREAM_BASE_URL}/file/{token}"
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>MovieBot Player</title>
  <style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{background:#0d0d0d;display:flex;align-items:center;justify-content:center;min-height:100vh}}
    video{{max-width:100%;max-height:100vh;outline:none;border-radius:8px}}
  </style>
</head>
<body>
  <video controls autoplay preload="metadata">
    <source src="{raw_url}" type="video/mp4">
    Your browser does not support HTML5 video.
  </video>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html")


async def health(request: web.Request) -> web.Response:
    return web.Response(text="OK")


# ── App factory ──────────────────────────────────────────────────────────────

def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/stream/{token}",  handle_player)
    app.router.add_get("/dl/{token}",      handle_download)
    app.router.add_get("/file/{token}",    handle_stream)
    app.router.add_get("/health",          health)
    return app


async def start_server():
    app   = build_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    log.info(f"Stream server running on port {PORT}")
