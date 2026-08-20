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
    ip_mask_mode: int | None = None,
) -> tuple[bytes, str]:
    validate_viewport_params(width, height, device_scale_factor)
    normalized = normalize_url(url, allow_schemes_whitelist=allow_schemes_whitelist)

    async with async_playwright() as playwright:
        masked_normalized = await mask_ip_in_text(normalized)
        logger.info(
            "Launching Chromium for %s with viewport %sx%s, scale=%s, full_page=%s",
            masked_normalized, width, height, device_scale_factor, full_page,
        )

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
            logger.info(
                "Screenshot captured, size=%s bytes, final_url=%s",
                len(image_bytes), masked_final_url,
            )
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
    ip_mask_mode: int | None = None,
) -> tuple[bytes, str]:
    return await capture_screenshot_bytes(
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
        ip_mask_mode=ip_mask_mode,
    )
