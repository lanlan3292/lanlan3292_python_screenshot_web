# firefox.py
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import logging
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
    ENABLE_IP_MASK,
    mask_ip_in_page,          # 新增
)

logger = logging.getLogger(__name__)

# ---------- Firefox Cookie 路径 ----------
FIREFOX_COOKIE_DB = Path(os.getenv("FIREFOX_COOKIE_DB", "")) if os.getenv("FIREFOX_COOKIE_DB") else None

# ---------- Cookie 加载函数 ----------
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

def load_firefox_cookies(hostname: str, db_path: Path | None = None) -> list[dict]:
    """
    从 Firefox cookie 数据库加载匹配的 cookies。
    匹配时使用原始 host（含可能的前导点），匹配成功后再剥离前导点，
    以满足 Playwright 的 domain 规范（不能以 . 开头）。
    """
    db_file = db_path or FIREFOX_COOKIE_DB
    if db_file is None:
        logger.info("Firefox cookie DB path is not configured")
        return []
    if not db_file.exists():
        logger.warning(f"Firefox cookie DB not found: {db_file}")
        return []

    cookie_hostname = _normalize_cookie_host(hostname)
    if not cookie_hostname:
        logger.warning(f"Empty cookie hostname for input: {hostname!r}")
        return []

    with tempfile.TemporaryDirectory(prefix="firefox-cookies-") as temp_dir:
        temp_db_path = Path(temp_dir) / "cookies.sqlite"
        shutil.copy2(db_file, temp_db_path)
        try:
            conn = sqlite3.connect(temp_db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT host, name, value, path, isSecure, isHttpOnly, expiry FROM moz_cookies"
            ).fetchall()
            conn.close()

            matched = []
            for row in rows:
                raw_host = row["host"]  # 原始 host，可能以 . 开头
                # 先用原始 host 进行匹配（泛域名匹配）
                if _cookie_domain_matches(raw_host, cookie_hostname):
                    cookie_dict = dict(row)
                    # 匹配成功后，剥离前导点（如果存在），供 Playwright 注入
                    host_for_playwright = raw_host
                    if host_for_playwright.startswith("."):
                        host_for_playwright = host_for_playwright[1:]
                    cookie_dict["host"] = host_for_playwright
                    matched.append(cookie_dict)

            logger.info(
                f"Loaded {len(matched)} cookie(s) for hostname: {mask_ip_in_text(hostname)} "
                f"(normalized: {mask_ip_in_text(cookie_hostname)}) out of {len(rows)} total"
            )
            # 使用 debug 级别，避免日志风暴
            for row in matched:
                logger.debug(
                    f"cookie -> host={row['host']} name={row['name']} "
                    f"path={row['path']} isSecure={row['isSecure']} isHttpOnly={row.get('isHttpOnly', 0)}"
                )
            return matched
        except Exception as exc:
            logger.error(f"Failed to load Firefox cookies: {exc}")
            return []

# ---------- 核心截图函数 ----------
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
) -> tuple[bytes, str]:
    validate_viewport_params(width, height, device_scale_factor)
    normalized = normalize_url(url, allow_schemes_whitelist=allow_schemes_whitelist)
    parsed = urlparse(normalized)
    hostname = parsed.hostname or ""

    async with async_playwright() as playwright:
        logger.info(f"Launching Firefox for {mask_ip_in_text(normalized)} with viewport {width}x{height}, scale={device_scale_factor}, full_page={full_page}")

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
                logger.info(f"Cookie injection enabled for {mask_ip_in_text(hostname)}")
                cookies = load_firefox_cookies(hostname)
                if cookies:
                    cookie_payload = []
                    for cookie in cookies:
                        payload = {
                            "name": cookie["name"],
                            "value": cookie["value"],
                            "domain": cookie["host"],  # 已剥离前导点
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
                    logger.info(f"Injecting {len(cookie_payload)} cookie(s)")
                    try:
                        await context.add_cookies(cookie_payload)
                    except Exception as exc:
                        logger.error(f"Cookie injection failed: {exc}")
                else:
                    logger.info(f"No cookies to inject for {mask_ip_in_text(hostname)}")
            else:
                logger.info("Cookie injection skipped (inject_cookies=False)")

            page = await context.new_page()
            await navigate_to_page(page, normalized)
            await page.wait_for_timeout(3000)

            # 优先等待网络空闲，超时 5 秒则回退到 1 秒等待
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                logger.warning("Network idle timeout, falling back to 1s wait")
                await page.wait_for_timeout(1000)

            logger.info("wait 10s")
            await page.wait_for_timeout(10000)

            if full_page:
                await scroll_to_trigger_lazy_loading(
                    page,
                    viewport_height=height,
                    max_scrolls=max_scrolls,
                    max_stable_before_break=max_stable_before_break,
                )

            final_url = page.url
            logger.info(f"Capturing screenshot (full_page={full_page})")

            # 在截图前对 DOM 中的 IP 进行掩码处理
            await mask_ip_in_page(page)

            image_bytes = await page.screenshot(full_page=full_page)
            logger.info(f"Screenshot captured, size={len(image_bytes)} bytes, final_url={mask_ip_in_text(final_url)}")
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
) -> tuple[bytes, str]:
    image_bytes, final_url = await capture_screenshot_bytes(
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
    )
    return image_bytes, final_url