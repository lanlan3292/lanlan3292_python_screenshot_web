from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from playwright.async_api import BrowserContext, Page

from .public_ip import get_public_ip

logger = logging.getLogger(__name__)

ENABLE_IP_MASK = True
IP_MASK_MODE = 1

_IPV4_RE = re.compile(
    r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
)
_IPV6_RE = re.compile(
    r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b|\b(?:[0-9a-fA-F]{1,4}:){1,7}:[0-9a-fA-F]{1,4}\b|::[0-9a-fA-F]{1,4}\b',
    re.IGNORECASE,
)


async def mask_ip_in_text(text: str) -> str:
    """Mask the configured public IP without blocking the event loop."""
    if not ENABLE_IP_MASK:
        return text
    try:
        ip = await get_public_ip()
    except Exception:
        return text
    return text.replace(ip, "**.**.**.**") if ip else text


async def mask_ip_in_page(page: Page, mode: int | None = None) -> None:
    if mode is None:
        mode = IP_MASK_MODE
    if mode == 0:
        return

    try:
        await page.wait_for_selector('#results object', timeout=10000)
    except Exception:
        logger.debug("No #results object found, continuing")

    await page.wait_for_timeout(2000)

    ip = None
    if mode == 2:
        try:
            ip = await get_public_ip()
        except Exception:
            logger.warning("Unable to obtain public IP, skipping DOM masking")
            return

    if mode == 2:
        escaped_ip = ip.replace('.', '\\.')
        js_code = f"""
            (function() {{
                const regex = new RegExp('{escaped_ip}', 'g');
                let totalCount = 0;
                function processDocument(doc) {{
                    if (!doc || !doc.body) return;
                    const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
                    let node;
                    while (node = walker.nextNode()) {{
                        const original = node.nodeValue;
                        const replaced = original.replace(regex, '**.**.**.**');
                        if (replaced !== original) {{ node.nodeValue = replaced; totalCount++; }}
                    }}
                    for (const el of doc.querySelectorAll('iframe, object, embed')) {{
                        try {{
                            const subDoc = el.contentDocument || (el.getSVGDocument && el.getSVGDocument());
                            if (subDoc) processDocument(subDoc);
                        }} catch (e) {{}}
                    }}
                }}
                processDocument(document);
                return totalCount;
            }})();
        """
    else:
        js_code = """
            (function() {
                const ipv4Regex = /\\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\b/g;
                const ipv6Regex = /\\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\\b|\\b(?:[0-9a-fA-F]{1,4}:){1,7}:[0-9a-fA-F]{1,4}\\b|::[0-9a-fA-F]{1,4}\\b/gi;
                let totalCount = 0;
                function processDocument(doc) {
                    if (!doc || !doc.body) return;
                    const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
                    let node;
                    while (node = walker.nextNode()) {
                        const original = node.nodeValue;
                        let replaced = original.replace(ipv4Regex, '**.**.**.**');
                        replaced = replaced.replace(ipv6Regex, '**:**:**:**:**:**:**:**:*');
                        if (replaced !== original) { node.nodeValue = replaced; totalCount++; }
                    }
                    for (const el of doc.querySelectorAll('iframe, object, embed')) {
                        try {
                            const subDoc = el.contentDocument || (el.getSVGDocument && el.getSVGDocument());
                            if (subDoc) processDocument(subDoc);
                        } catch (e) {}
                    }
                }
                processDocument(document);
                return totalCount;
            })();
        """

    try:
        count = await page.evaluate(js_code)
        logger.info("DOM IP masking applied (mode=%s), replaced %s text node(s)", mode, count)
    except Exception as exc:
        logger.warning("Failed to mask IP in DOM: %s", exc)


def validate_viewport_params(width: int, height: int, device_scale_factor: float) -> None:
    if not (640 <= width <= 4096):
        raise ValueError(f"Width must be between 640 and 4096, got {width}")
    if not (480 <= height <= 4096):
        raise ValueError(f"Height must be between 480 and 4096, got {height}")
    if not (0.1 <= device_scale_factor <= 5.0):
        raise ValueError(f"device_scale_factor must be between 0.1 and 5.0, got {device_scale_factor}")


def normalize_url(url: str, allow_schemes_whitelist: bool = True) -> str:
    cleaned = url.strip()
    if not cleaned:
        raise ValueError("URL cannot be empty")
    parsed = urlparse(cleaned)
    if not parsed.scheme:
        if "://" in cleaned:
            raise ValueError("URL must include a valid scheme")
        return f"https://{cleaned}"
    scheme = parsed.scheme.lower()
    if allow_schemes_whitelist and scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported URL scheme: {scheme}")
    if scheme in {"http", "https"} and not parsed.netloc:
        raise ValueError("URL must include a hostname")
    if not parsed.netloc and not parsed.path:
        raise ValueError("URL must include a hostname or path")
    return parsed.geturl()


async def navigate_to_page(page: Page, url: str) -> None:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    except Exception as exc:
        masked = await mask_ip_in_text(url)
        logger.warning("Navigation warning for %s: %s", masked, exc)


async def scroll_to_trigger_lazy_loading(
    page: Page,
    viewport_height: int,
    max_scrolls: int = 15,
    max_stable_before_break: int = 3,
) -> None:
    logger.info("Scrolling to trigger lazy loading via JS...")
    js_code = """
        (async ({ viewportHeight, maxScrolls, maxStableBeforeBreak }) => {
            let currentScroll = viewportHeight;
            let scrollCount = 0;
            let stableCount = 0;
            let scrollHeight = document.body.scrollHeight;
            while (currentScroll < scrollHeight && scrollCount < maxScrolls) {
                window.scrollTo(0, currentScroll);
                await new Promise(resolve => setTimeout(resolve, 500));
                const newScrollHeight = document.body.scrollHeight;
                if (newScrollHeight === scrollHeight) stableCount++;
                else { stableCount = 0; scrollHeight = newScrollHeight; }
                if (stableCount >= maxStableBeforeBreak) break;
                currentScroll += viewportHeight;
                scrollCount++;
            }
            window.scrollTo(0, 0);
            await new Promise(resolve => setTimeout(resolve, 1000));
        })
    """
    await page.evaluate(js_code, {
        "viewportHeight": viewport_height,
        "maxScrolls": max_scrolls,
        "maxStableBeforeBreak": max_stable_before_break,
    })
    logger.info("Scrolling complete")


async def setup_media_blocking(context: BrowserContext, block_media: bool) -> None:
    if not block_media:
        logger.info("Media blocking disabled.")
        return

    logger.info("Blocking image/media resources.")

    async def route_handler(route):
        try:
            if route.request.resource_type in {"image", "media"}:
                await route.abort()
            else:
                await route.continue_()
        except Exception:
            pass

    await context.route("**/*", route_handler)
