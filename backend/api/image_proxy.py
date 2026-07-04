"""
Image proxy API — proxies external OG images to avoid CORS issues.
GET /api/image-proxy?url=<encoded_url>
"""

import ipaddress
import socket
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

router = APIRouter()

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB


def _is_public_host(host: str) -> bool:
    """Resolve host and reject if any address is private/loopback/link-local/reserved (SSRF guard)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


@router.get("/image-proxy")
async def proxy_image(url: str = Query(..., description="Image URL to proxy")):
    """Proxy an external image to avoid CORS issues."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise HTTPException(status_code=400, detail="Invalid URL")
    if not _is_public_host(parts.hostname):
        raise HTTPException(status_code=400, detail="Host not allowed")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "image/*",
    }

    try:
        # follow_redirects disabled: a redirect could point at an internal address, bypassing the SSRF guard.
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "").split(";")[0].strip()
            if content_type not in ALLOWED_CONTENT_TYPES:
                raise HTTPException(status_code=400, detail=f"Not an image: {content_type}")

            if len(resp.content) > MAX_IMAGE_SIZE:
                raise HTTPException(status_code=400, detail="Image too large")

            return Response(
                content=resp.content,
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400",
                    "Access-Control-Allow-Origin": "*",
                },
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Failed to fetch image")
