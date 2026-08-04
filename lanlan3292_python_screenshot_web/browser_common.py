# browser_common.py
from __future__ import annotations

import inspect
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import Page, BrowserContext

# ---------- 路径配置 ----------
ROOT = Path.cwd()
SCREENSHOT_DIR = ROOT / "output/lanlan3292_python_screenshot_web"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_SCHEMES = {"http", "https"}


# ---------- 日志 ----------
def log_message(msg: str) -> None:
    """
    自动从调用栈中识别调用者模块名（如 'chromium' 或 'firefox'），
    并输出格式化的日志。
    """
    import inspect
    stack = inspect.stack()
    caller_module = "unknown"
    for frame_info in stack:
        mod = frame_info.frame.f_globals.get("__name__")
        # 跳过 browser_common 自身以及任何属于 browser_common 的内部调用
        if mod and not (mod == "browser_common" or mod.endswith(".browser_common")):
            caller_module = mod.split(".")[-1]
            break
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [lanlan3292_python_screenshot_web.{caller_module}] {msg}")


# ---------- 校验 ----------
def validate_viewport_params(width: int, height: int, device_scale_factor: float) -> None:
    if not (640 <= width <= 4096):
        raise ValueError(f"Width must be between 640 and 4096, got {width}")
    if not (480 <= height <= 4096):
        raise ValueError(f"Height must be between 480 and 4096, got {height}")
    if not (0.1 <= device_scale_factor <= 5.0):
        raise ValueError(f"device_scale_factor must be between 0.1 and 5.0, got {device_scale_factor}")


# ---------- URL 处理 ----------
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


async def navigate_to_page(page: Page, url: str) -> None:
    normalized = normalize_url(url)
    try:
        await page.goto(normalized, wait_until="domcontentloaded", timeout=60000)
    except Exception as exc:
        log_message(f"Navigation warning for {normalized}: {exc}")


async def scroll_to_trigger_lazy_loading(
    page: Page,
    viewport_height: int,
    max_scrolls: int = 15,
    max_stable_before_break: int = 3,
) -> None:
    log_message("Scrolling to trigger lazy loading...")
    scroll_height = await page.evaluate("document.body.scrollHeight")
    current_scroll = 0
    scroll_count = 0
    stable_count = 0

    while current_scroll < scroll_height and scroll_count < max_scrolls:
        await page.evaluate(f"window.scrollTo(0, {current_scroll})")
        await page.wait_for_timeout(500)

        new_scroll_height = await page.evaluate("document.body.scrollHeight")
        if new_scroll_height == scroll_height:
            stable_count += 1
        else:
            stable_count = 0
            scroll_height = new_scroll_height

        if stable_count >= max_stable_before_break:
            log_message("Page height stable, stopping scroll.")
            break

        current_scroll += viewport_height
        scroll_count += 1

    if scroll_count >= max_scrolls:
        log_message(f"Reached max scroll limit ({max_scrolls}), stopping.")

    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(1000)
    log_message("Scrolling complete")


async def setup_media_blocking(context: BrowserContext, block_media: bool) -> None:
    if block_media:
        log_message("Blocking image/media resources.")
        async def route_handler(route):
            if route.request.resource_type in {"image", "media"}:
                await route.abort()
            else:
                await route.continue_()
        await context.route("**/*", route_handler)
    else:
        log_message("Media blocking disabled.")


def generate_output_path(url: str, output_path: Path | None = None, browser: str | None = None) -> Path:
    if output_path is not None:
        return output_path
    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    host = parsed.hostname or "page"
    slug = re.sub(r"[^a-z0-9]+", "-", host.lower()).strip("-") or "page"
    prefix = f"{browser}" if browser else ""
    file_name = f"{slug}-{int(time.time())}-{prefix}.png"
    return SCREENSHOT_DIR / file_name