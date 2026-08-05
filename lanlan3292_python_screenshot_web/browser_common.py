from __future__ import annotations

import logging
from urllib.parse import urlparse
from pathlib import Path
import tempfile
from urllib.request import Request, urlopen

from playwright.async_api import Page, BrowserContext

logger = logging.getLogger(__name__)

# ---------- 公网 IP 掩码（内嵌） ----------
PUBLIC_IP_FILE = Path(tempfile.gettempdir()) / "public_ip.env"
ENABLE_IP_MASK = True  # 全局总开关，默认开启

def get_public_ip() -> str:
    """获取当前公网 IP，结果缓存到临时文件。"""
    try:
        request = Request("https://api.ip.sb/ip", headers={"User-Agent": "curl/8.0"})
        with urlopen(request, timeout=10) as response:
            ip = response.read().decode("utf-8").strip()
        PUBLIC_IP_FILE.parent.mkdir(parents=True, exist_ok=True)
        PUBLIC_IP_FILE.write_text(ip, encoding="utf-8")
        return ip
    except Exception:
        if PUBLIC_IP_FILE.exists():
            cached = PUBLIC_IP_FILE.read_text(encoding="utf-8").strip()
            if cached:
                return cached
        raise

def mask_ip_in_text(text: str, ip_address: str | None = None) -> str:
    """如果全局开关开启，将文本中的公网 IP 替换为 '**.**.**.**'。"""
    if not ENABLE_IP_MASK:
        return text
    if ip_address is None:
        try:
            ip_address = get_public_ip()
        except Exception:
            return text
    if not ip_address or ip_address not in text:
        return text
    return text.replace(ip_address, "**.**.**.**")

async def mask_ip_in_page(page: Page) -> None:
    """
    在页面 DOM 中将公网 IP 替换为 '**.**.**.**'。
    仅当全局开关 ENABLE_IP_MASK 为 True 时执行。
    """
    if not ENABLE_IP_MASK:
        return
    try:
        ip = get_public_ip()
    except Exception:
        logger.warning("Failed to get public IP, skipping DOM IP masking")
        return
    if not ip:
        return
    escaped_ip = ip.replace('.', '\\.')
    js_code = f"""
        (function() {{
            const ip = '{ip}';
            const escaped = '{escaped_ip}';
            const regex = new RegExp(escaped, 'g');
            const walker = document.createTreeWalker(
                document.body,
                NodeFilter.SHOW_TEXT,
                {{
                    acceptNode: function(node) {{
                        if (node.textContent.includes(ip)) return NodeFilter.FILTER_ACCEPT;
                        return NodeFilter.FILTER_REJECT;
                    }}
                }}
            );
            const nodes = [];
            let node;
            while (node = walker.nextNode()) {{
                nodes.push(node);
            }}
            for (let n of nodes) {{
                n.textContent = n.textContent.replace(regex, '**.**.**.**');
            }}
        }})();
    """
    try:
        await page.evaluate(js_code)
        logger.info("DOM IP masking applied")
    except Exception as e:
        logger.warning(f"Failed to mask IP in DOM: {e}")

# ---------- 原有函数 ----------
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
        logger.warning(f"Navigation warning for {mask_ip_in_text(url)}: {exc}")

async def scroll_to_trigger_lazy_loading(
    page: Page,
    viewport_height: int,
    max_scrolls: int = 15,
    max_stable_before_break: int = 3,
) -> None:
    logger.info("Scrolling to trigger lazy loading via JS...")
    js_code = """
        (async (viewportHeight, maxScrolls, maxStableBeforeBreak) => {
            let currentScroll = viewportHeight;
            let scrollCount = 0;
            let stableCount = 0;
            let scrollHeight = document.body.scrollHeight;

            while (currentScroll < scrollHeight && scrollCount < maxScrolls) {
                window.scrollTo(0, currentScroll);
                await new Promise(resolve => setTimeout(resolve, 500));

                const newScrollHeight = document.body.scrollHeight;
                if (newScrollHeight === scrollHeight) {
                    stableCount++;
                } else {
                    stableCount = 0;
                    scrollHeight = newScrollHeight;
                }

                if (stableCount >= maxStableBeforeBreak) {
                    console.log("Page height stable, stopping scroll.");
                    break;
                }

                currentScroll += viewportHeight;
                scrollCount++;
            }

            if (scrollCount >= maxScrolls) {
                console.log("Reached max scroll limit, stopping.");
            }

            window.scrollTo(0, 0);
            await new Promise(resolve => setTimeout(resolve, 1000));
        })(viewportHeight, maxScrolls, maxStableBeforeBreak);
    """
    await page.evaluate(js_code, viewport_height, max_scrolls, max_stable_before_break)
    logger.info("Scrolling complete")

async def setup_media_blocking(context: BrowserContext, block_media: bool) -> None:
    if block_media:
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
    else:
        logger.info("Media blocking disabled.")