# chromium.py
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime

from playwright.async_api import async_playwright

from browser_common import (
    normalize_url,
    navigate_to_page,
    scroll_to_trigger_lazy_loading,
    setup_media_blocking,
    generate_output_path,
)


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
) -> tuple[bytes, str]:
    """
    使用 Chromium 截图并返回 (图片字节数据, 最终URL)。
    不包含 Cookie 注入功能。

    参数:
        url: 目标 URL
        width: 视口宽度（640~4096）
        height: 视口高度（480~4096）
        user_agent: 自定义 User-Agent，不提供则使用默认
        full_page: 是否截取整个页面（滚动截图）
        device_scale_factor: 设备像素比（缩放），范围 0.1~5.0
        max_scrolls: 全页截图时最大滚动次数
        max_stable_before_break: 高度连续不变多少次后停止滚动
        block_media: 是否阻止图片和媒体资源加载
    """
    if not (640 <= width <= 4096):
        raise ValueError(f"Width must be between 640 and 4096, got {width}")
    if not (480 <= height <= 4096):
        raise ValueError(f"Height must be between 480 and 4096, got {height}")
    if not (0.1 <= device_scale_factor <= 5.0):
        raise ValueError(f"device_scale_factor must be between 0.1 and 5.0, got {device_scale_factor}")

    normalized = normalize_url(url)

    async with async_playwright() as playwright:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [lanlan3292_python_screenshot_web.chromium] Launching Chromium for {normalized} with viewport {width}x{height}, scale={device_scale_factor}, full_page={full_page}")

        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-web-security",
                "--disable-dev-shm-usage",
                "--no-sandbox",
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
            # 媒体拦截
            await setup_media_blocking(context, block_media)

            page = await context.new_page()
            await navigate_to_page(page, normalized)

            # 等待加载
            try:
                await page.wait_for_load_state("load", timeout=60000)
            except Exception as exc:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [lanlan3292_python_screenshot_web.chromium] Load state warning: {exc}")
            await page.wait_for_timeout(5000)

            # 全页截图时的滚动触发懒加载
            if full_page:
                await scroll_to_trigger_lazy_loading(
                    page,
                    viewport_height=height,
                    max_scrolls=max_scrolls,
                    max_stable_before_break=max_stable_before_break,
                )

            final_url = page.url
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [lanlan3292_python_screenshot_web.chromium] Capturing screenshot (full_page={full_page})")
            image_bytes = await page.screenshot(full_page=full_page)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [lanlan3292_python_screenshot_web.chromium] Screenshot captured, size={len(image_bytes)} bytes, final_url={final_url}")
            return image_bytes, final_url

        finally:
            await context.close()
            await browser.close()


async def capture_screenshot(
    url: str,
    output_path: Path | None = None,
    user_agent: str | None = None,
    full_page: bool = False,
    device_scale_factor: float = 1.0,
    max_scrolls: int = 15,
    max_stable_before_break: int = 3,
    block_media: bool = False,
) -> tuple[Path, str]:
    """
    截图并保存到文件，返回 (保存路径, 最终URL)。
    参数同 capture_screenshot_bytes。
    """
    output_path = generate_output_path(url, output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    image_bytes, final_url = await capture_screenshot_bytes(
        url,
        width=1400,
        height=900,
        user_agent=user_agent,
        full_page=full_page,
        device_scale_factor=device_scale_factor,
        max_scrolls=max_scrolls,
        max_stable_before_break=max_stable_before_break,
        block_media=block_media,
    )
    output_path.write_bytes(image_bytes)
    return output_path, final_url