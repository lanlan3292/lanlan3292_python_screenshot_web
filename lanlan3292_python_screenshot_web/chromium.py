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
    mask_ip_in_text,
    ENABLE_IP_MASK,
    mask_ip_in_page,
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
    allow_schemes_whitelist: bool = True,
    mask_dom_text: bool = True,  # 参数重命名
) -> tuple[bytes, str]:
    validate_viewport_params(width, height, device_scale_factor)
    normalized = normalize_url(url, allow_schemes_whitelist=allow_schemes_whitelist)

    async with async_playwright() as playwright:
        logger.info(f"Launching Chromium for {mask_ip_in_text(normalized)} with viewport {width}x{height}, scale={device_scale_factor}, full_page={full_page}")

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
            await navigate_to_page(page, normalized)
            await page.wait_for_timeout(3000)

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

            if mask_dom_text:
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
    user_agent: str | None = None,
    full_page: bool = False,
    device_scale_factor: float = 1.0,
    max_scrolls: int = 15,
    max_stable_before_break: int = 3,
    block_media: bool = False,
    allow_schemes_whitelist: bool = True,
    mask_dom_text: bool = True,  # 参数重命名
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
        mask_dom_text=mask_dom_text,
    )
    return image_bytes, final_url