# chromium.py
from __future__ import annotations

import logging

from playwright.async_api import async_playwright

from .browser_common import (
    normalize_url,
    validate_viewport_params,
    navigate_to_page,
    scroll_to_trigger_lazy_loading,
    setup_media_blocking,
)

logger = logging.getLogger(__name__)

async def capture_screenshot_bytes(
    url: str,
    width: int = 1400,
    height: int = 900,
    user_agent: str | None = None,
    full_page: bool = False,
    device_scale_factor: float = 1.0,
    max_scrolls: int = 15,
    max_stable_before_break: int = 3,
    block_media: bool = False,
    allow_schemes_whitelist: bool = True,  # 新增，默认保持白名单
) -> tuple[bytes, str]:
    """
    使用 Chromium 截图并返回 (图片字节数据, 最终URL)。
    不包含 Cookie 注入功能。
    """
    validate_viewport_params(width, height, device_scale_factor)
    normalized = normalize_url(url, allow_schemes_whitelist=allow_schemes_whitelist)

    async with async_playwright() as playwright:
        logger.info(f"Launching Chromium for {normalized} with viewport {width}x{height}, scale={device_scale_factor}, full_page={full_page}")

        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-web-security",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--enable-chrome-browser-cloud-management",
                "--ignore-certificate-errors",
                "--whitelisted-extension-id",
            ],
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

            page = await context.new_page()
            await navigate_to_page(page, normalized)  # 传入已标准化的 URL

            # 优先等待网络空闲（networkidle），超时 5 秒则回退到 1 秒等待
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                logger.warning("Network idle timeout, falling back to 1s wait")
                await page.wait_for_timeout(1000)

            if full_page:
                await scroll_to_trigger_lazy_loading(
                    page,
                    viewport_height=height,
                    max_scrolls=max_scrolls,
                    max_stable_before_break=max_stable_before_break,
                )

            final_url = page.url
            logger.info(f"Capturing screenshot (full_page={full_page})")
            image_bytes = await page.screenshot(full_page=full_page)
            logger.info(f"Screenshot captured, size={len(image_bytes)} bytes, final_url={final_url}")
            return image_bytes, final_url

        finally:
            await context.close()
            await browser.close()

async def capture_screenshot(
    url: str,
    width: int = 1400,
    height: int = 900,
    user_agent: str | None = None,
    full_page: bool = False,
    device_scale_factor: float = 1.0,
    max_scrolls: int = 15,
    max_stable_before_break: int = 3,
    block_media: bool = False,
    allow_schemes_whitelist: bool = True,  # 新增
) -> tuple[bytes, str]:
    image_bytes, final_url = await capture_screenshot_bytes(
        url,
        width=width,
        height=height,
        user_agent=user_agent,
        full_page=full_page,
        device_scale_factor=device_scale_factor,
        max_scrolls=max_scrolls,
        max_stable_before_break=max_stable_before_break,
        block_media=block_media,
        allow_schemes_whitelist=allow_schemes_whitelist,
    )
    return image_bytes, final_url