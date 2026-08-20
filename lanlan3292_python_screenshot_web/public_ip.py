from __future__ import annotations

import asyncio
import ipaddress
import logging
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

PUBLIC_IP_FILE = Path(tempfile.gettempdir()) / "public_ip.env"
IP_SERVICES = (
    "https://checkip.amazonaws.com",
    "https://icanhazip.com",
    "https://api.ipify.org",
)


def _get_public_ip_sync() -> str:
    for url in IP_SERVICES:
        try:
            logger.info("Fetching public IP from %s", url)
            request = Request(url, headers={"User-Agent": "curl/8.0"})
            with urlopen(request, timeout=10) as response:
                value = response.read().decode("utf-8").strip()

            try:
                ipaddress.ip_address(value)
            except ValueError:
                continue

            PUBLIC_IP_FILE.parent.mkdir(parents=True, exist_ok=True)
            PUBLIC_IP_FILE.write_text(value, encoding="utf-8")
            return value
        except Exception:
            continue

    try:
        cached = PUBLIC_IP_FILE.read_text(encoding="utf-8").strip()
        ipaddress.ip_address(cached)
        return cached
    except Exception as exc:
        raise RuntimeError("Unable to get public IP") from exc


async def get_public_ip() -> str:
    """Get the public IP without blocking the asyncio event loop."""
    return await asyncio.to_thread(_get_public_ip_sync)
