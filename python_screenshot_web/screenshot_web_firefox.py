# screenshot_web_firefox.py
from __future__ import annotations

import os
import re
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime

from playwright.async_api import async_playwright

# ---------- 路径配置 ----------
ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
SCREENSHOT_DIR = ROOT / "outputs/screenshots_web"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

FIREFOX_COOKIE_DB = Path(os.getenv("FIREFOX_COOKIE_DB", "")) if os.getenv("FIREFOX_COOKIE_DB") else None

ALLOWED_SCHEMES = {"http", "https"}


# ---------- 辅助 ----------
def normalize_url(url: str) -> str:
    cleaned = url.strip()
    if not cleaned:
        raise ValueError("URL cannot be empty")
    parsed = urlparse(cleaned)
    if not parsed.scheme:
        if "://" in cleaned:
            raise ValueError("URL must include a valid scheme")
        return f"https://{cleaned}"
    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"Unsupported URL scheme: {scheme}")
    if not parsed.netloc:
        raise ValueError("URL must include a hostname")
    return parsed.geturl()


async def navigate_to_page(page, url: str) -> None:
    normalized = normalize_url(url)
    try:
        await page.goto(normalized, wait_until="domcontentloaded", timeout=60000)
    except Exception as exc:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web_firefox] Navigation warning for {normalized}: {exc}")


# ---------- Firefox Cookie 加载（无白名单判断） ----------
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
    从 Firefox cookie 数据库加载匹配 hostname 的所有 cookie。
    此函数本身不进行任何安全过滤，只负责数据提取。
    """
    db_file = db_path or FIREFOX_COOKIE_DB
    if db_file is None:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web_firefox] Firefox cookie DB path is not configured")
        return []
    if not db_file.exists():
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web_firefox] Firefox cookie DB not found: {db_file}")
        return []

    temp_db_path = None
    try:
        if db_path is None:
            temp_dir = Path(tempfile.mkdtemp(prefix="firefox-cookies-", dir=str(CONFIG_DIR)))
            temp_db_path = temp_dir / "cookies.sqlite"
            shutil.copy2(db_file, temp_db_path)
            db_file = temp_db_path

        cookie_hostname = _normalize_cookie_host(hostname)
        if not cookie_hostname:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web_firefox] Empty cookie hostname for input: {hostname!r}")
            return []

        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT host, name, value, path, isSecure, isHttpOnly, expiry FROM moz_cookies"
        ).fetchall()
        conn.close()

        matched = [
            dict(row)
            for row in rows
            if _cookie_domain_matches(row["host"], cookie_hostname)
        ]
        print(
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web_firefox] Loaded {len(matched)} cookie(s) for hostname: {hostname} "
            f"(normalized: {cookie_hostname}) out of {len(rows)} total"
        )
        for row in matched:
            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web_firefox] cookie -> host={row['host']} name={row['name']} "
                f"path={row['path']} isSecure={row['isSecure']} isHttpOnly={row.get('isHttpOnly', 0)}"
            )
        return matched
    except Exception as exc:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web_firefox] Failed to load Firefox cookies: {exc}")
        return []
    finally:
        if temp_db_path and temp_db_path.exists():
            shutil.rmtree(temp_db_path.parent, ignore_errors=True)


# ---------- 核心截图函数（无安全检查，Cookie 注入由参数控制） ----------
async def capture_screenshot_bytes(
    url: str,
    width: int = 1400,
    height: int = 900,
    inject_cookies: bool = False,
    user_agent: str | None = None,
    full_page: bool = False,
    device_scale_factor: float = 1.0,
) -> tuple[bytes, str]:
    """
    截图并返回 (图片字节数据, 最终URL)。
    不再进行任何安全检查（白名单、IP、Cookie 白名单等）。
    若 inject_cookies=True，则自动加载 Firefox 中匹配的 Cookie 并注入。

    参数:
        url: 目标 URL
        width: 视口宽度（640~4096）
        height: 视口高度（480~4096）
        inject_cookies: 是否注入 Cookie
        user_agent: 自定义 User-Agent，不提供则使用默认
        full_page: 是否截取整个页面（滚动截图）
        device_scale_factor: 设备像素比（缩放），范围 0.1~5.0，默认 1.0
    """
    if not (640 <= width <= 4096):
        raise ValueError(f"Width must be between 640 and 4096, got {width}")
    if not (480 <= height <= 4096):
        raise ValueError(f"Height must be between 480 and 4096, got {height}")
    if not (0.1 <= device_scale_factor <= 5.0):
        raise ValueError(f"device_scale_factor must be between 0.1 and 5.0, got {device_scale_factor}")

    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    hostname = parsed.hostname or ""

    async with async_playwright() as playwright:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web_firefox] Launching Firefox for {normalized} with viewport {width}x{height}, scale={device_scale_factor}, full_page={full_page}")
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
            # Cookie 注入
            if inject_cookies:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web_firefox] Cookie injection enabled for {hostname}")
                cookies = load_firefox_cookies(hostname)
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
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web_firefox] Injecting {len(cookie_payload)} cookie(s)")
                    try:
                        await context.add_cookies(cookie_payload)
                    except Exception as exc:
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web_firefox] Cookie injection failed: {exc}")
                else:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web_firefox] No cookies to inject for {hostname}")
            else:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web_firefox] Cookie injection skipped (inject_cookies=False)")

            page = await context.new_page()
            await navigate_to_page(page, normalized)

            # 等待加载
            try:
                await page.wait_for_load_state("load", timeout=60000)
            except Exception as exc:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web_firefox] Load state warning: {exc}")
            await page.wait_for_timeout(5000)

            # 获取最终 URL
            final_url = page.url

            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web_firefox] Capturing screenshot (full_page={full_page})")
            image_bytes = await page.screenshot(full_page=full_page)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web_firefox] Screenshot captured, size={len(image_bytes)} bytes, final_url={final_url}")
            #debug_path = CONFIG_DIR / "debug_screenshot.png"
            #debug_path.write_bytes(image_bytes)
            #print(f"[DEBUG] Saved screenshot to {debug_path}")
            return image_bytes, final_url
        finally:
            await context.close()
            await browser.close()


async def capture_screenshot(
    url: str,
    output_path: Path | None = None,
    inject_cookies: bool = False,
    user_agent: str | None = None,
    full_page: bool = False,
    device_scale_factor: float = 1.0,
) -> tuple[Path, str]:
    """
    截图并保存到文件，返回 (保存路径, 最终URL)。
    参数同 capture_screenshot_bytes。
    """
    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    host = parsed.hostname or "page"
    slug = re.sub(r"[^a-z0-9]+", "-", host.lower()).strip("-") or "page"
    if output_path is None:
        file_name = f"{slug}-{int(time.time())}.png"
        output_path = SCREENSHOT_DIR / file_name

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image_bytes, final_url = await capture_screenshot_bytes(
        normalized,
        inject_cookies=inject_cookies,
        user_agent=user_agent,
        full_page=full_page,
        device_scale_factor=device_scale_factor,
    )
    output_path.write_bytes(image_bytes)
    return output_path, final_url