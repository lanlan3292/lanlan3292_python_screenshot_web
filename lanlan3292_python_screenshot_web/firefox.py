# firefox.py
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright

from .browser_common import (
    normalize_url,
    validate_viewport_params,
    navigate_to_page,
    scroll_to_trigger_lazy_loading,
    setup_media_blocking,
    mask_ip_in_text,
    mask_ip_in_page,
)

logger = logging.getLogger(__name__)
FIREFOX_COOKIE_DB = Path(os.getenv("FIREFOX_COOKIE_DB", "")) if os.getenv("FIREFOX_COOKIE_DB") else None


def _normalize_cookie_host(hostname: str) -> str:
    cleaned = hostname.strip()
    if not cleaned:
        return ""
    parsed = urlparse(cleaned if "://" in cleaned else f"https://{cleaned}")
    return (parsed.hostname or "").lower()


def _cookie_domain_matches(cookie_host: str, hostname: str) -> bool:
    cookie_host = (cookie_host or "").strip().lower()
    hostname = (hostname or "").strip().lower()
    if not cookie_host or not hostname:
        return False
    if cookie_host.startswith("."):
        domain = cookie_host[1:]
        return hostname == domain or hostname.endswith("." + domain)
    return hostname == cookie_host


def _load_firefox_cookies_sync(hostname: str, db_path: Path | None = None) -> list[dict]:
    db_file = db_path or FIREFOX_COOKIE_DB
    if db_file is None or not db_file.exists():
        return []

    cookie_hostname = _normalize_cookie_host(hostname)
    if not cookie_hostname:
        return []

    with tempfile.TemporaryDirectory(prefix="firefox-cookies-") as temp_dir:
        temp_db_path = Path(temp_dir) / "cookies.sqlite"
        shutil.copy2(db_file, temp_db_path)
        with sqlite3.connect(temp_db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT host, name, value, path, isSecure, isHttpOnly, expiry FROM moz_cookies"
            ).fetchall()

        matched = []
        for row in rows:
            raw_host = row["host"]
            if _cookie_domain_matches(raw_host, cookie_hostname):
                matched.append(dict(row))
        return matched


async def load_firefox_cookies(hostname: str, db_path: Path | None = None) -> list[dict]:
    """Read Firefox's cookie database without blocking the event loop."""
    return await asyncio.to_thread(_load_firefox_cookies_sync, hostname, db_path)


async def capture_screenshot_bytes(
    url: str,
    width: int = 1400,
    height: int = 900,
    inject_cookies: bool = False,
    user_agent: str | None = None,
    full_page: bool = False,
    device_scale_factor: float = 1.0,
    max_scrolls: int = 15,
    max_stable_before_break: int = 3,
    block_media: bool = False,
    allow_schemes_whitelist: bool = True,
    ip_mask_mode: int | None = None,
) -> tuple[bytes, str]:
    validate_viewport_params(width, height, device_scale_factor)
    normalized = normalize_url(url, allow_schemes_whitelist=allow_schemes_whitelist)
    hostname = urlparse(normalized).hostname or ""

    async with async_playwright() as playwright:
        masked_normalized = await mask_ip_in_text(normalized)
        logger.info(
            "Launching Firefox for %s with viewport %sx%s, scale=%s, full_page=%s",
            masked_normalized, width, height, device_scale_factor, full_page,
        )

        browser = await playwright.firefox.launch(
            headless=True,
            firefox_user_prefs={
                "media.volume_scale": "0.0",
                "media.default_volume": "0.0",
                "media.hardware-video-decoding.enabled": False,
                "media.autoplay.default": 5,
                "media.block-autoplay-until-in-foreground": True,
                "media.block-play-until-visible": True,
                "media.navigator.enabled": False,
                "media.peerconnection.ice.proxy_only_if_single_homed": True,
                "media.peerconnection.ice.default_address_only": True,
                "media.peerconnection.ice.no_host": True,
                "intl.accept_languages": "en-US,en",
                "general.useragent.locale": "en-US",
                "browser.search.region": "US",
                "toolkit.telemetry.enabled": False,
                "datareporting.healthreport.uploadEnabled": False,
                "geo.enabled": False,
                "permissions.default.geo": 0,
                "geo.provider.network.url": "",
                "geo.provider.use_os_location": False,
            },
        )

        context_options = {
            "viewport": {"width": width, "height": height},
            "locale": "en-US",
            "timezone_id": "UTC",
            "extra_http_headers": {"Accept-Language": "en-US,en;q=0.9"},
            "device_scale_factor": device_scale_factor,
        }
        if user_agent:
            context_options["user_agent"] = user_agent

        context = await browser.new_context(**context_options)
        try:
            await setup_media_blocking(context, block_media)

            if inject_cookies:
                cookies = await load_firefox_cookies(hostname)
                if cookies:
                    cookie_payload = []
                    for cookie in cookies:
                        payload = {
                            "name": cookie["name"],
                            "value": cookie["value"],
                            "domain": cookie["host"],
                            "path": cookie["path"] or "/",
                            "secure": bool(cookie.get("isSecure", 0)),
                            "httpOnly": bool(cookie.get("isHttpOnly", 0)),
                            "sameSite": "Lax",
                        }
                        expiry = cookie.get("expiry")
                        if isinstance(expiry, (int, float)) and expiry > 0:
                            expiry_seconds = int(expiry / 1000 if expiry > 1_000_000_000_000 else expiry)
                            if expiry_seconds > 0:
                                payload["expires"] = expiry_seconds
                        cookie_payload.append(payload)
                    await context.add_cookies(cookie_payload)

            page = await context.new_page()
            await navigate_to_page(page, normalized)
            await page.wait_for_timeout(3000)

            if full_page:
                await scroll_to_trigger_lazy_loading(
                    page,
                    viewport_height=height,
                    max_scrolls=max_scrolls,
                    max_stable_before_break=max_stable_before_break,
                )

            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                logger.warning("Network idle timeout, falling back to 1s wait")
                await page.wait_for_timeout(1000)

            await page.wait_for_timeout(10000)
            final_url = page.url
            await mask_ip_in_page(page, ip_mask_mode)
            image_bytes = await page.screenshot(full_page=full_page)
            masked_final_url = await mask_ip_in_text(final_url)
            logger.info("Screenshot captured, size=%s bytes, final_url=%s", len(image_bytes), masked_final_url)
            return image_bytes, final_url
        finally:
            await context.close()
            await browser.close()


async def capture_screenshot(
    url: str,
    width: int = 1400,
    height: int = 900,
    inject_cookies: bool = False,
    user_agent: str | None = None,
    full_page: bool = False,
    device_scale_factor: float = 1.0,
    max_scrolls: int = 15,
    max_stable_before_break: int = 3,
    block_media: bool = False,
    allow_schemes_whitelist: bool = True,
    ip_mask_mode: int | None = None,
) -> tuple[bytes, str]:
    return await capture_screenshot_bytes(
        url,
        width=width,
        height=height,
        inject_cookies=inject_cookies,
        user_agent=user_agent,
        full_page=full_page,
        device_scale_factor=device_scale_factor,
        max_scrolls=max_scrolls,
        max_stable_before_break=max_stable_before_break,
        block_media=block_media,
        allow_schemes_whitelist=allow_schemes_whitelist,
        ip_mask_mode=ip_mask_mode,
    )
