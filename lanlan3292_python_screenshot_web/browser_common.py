from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from playwright.async_api import Page, BrowserContext

logger = logging.getLogger(__name__)

# ---------- 公网 IP 掩码配置 ----------
PUBLIC_IP_FILE = Path(tempfile.gettempdir()) / "public_ip.env"
ENABLE_IP_MASK = False          # 日志掩码总开关（仅影响日志）
IP_MASK_MODE = 1               # 默认 DOM 掩码模式（2=仅出口 IPv4）

# IPv4 和 IPv6 正则（用于模式 1）
_IPV4_RE = re.compile(
    r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
)
_IPV6_RE = re.compile(
    r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b|\b(?:[0-9a-fA-F]{1,4}:){1,7}:[0-9a-fA-F]{1,4}\b|::[0-9a-fA-F]{1,4}\b',
    re.IGNORECASE
)

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

def mask_ip_in_text(text: str) -> str:
    """
    日志 IP 掩码：仅当 ENABLE_IP_MASK 为 True 时，将文本中的出口 IPv4 替换为 '**.**.**.**'。
    固定使用模式 2（仅出口 IPv4）。
    """
    if not ENABLE_IP_MASK:
        return text
    try:
        ip = get_public_ip()
    except Exception:
        return text
    if ip and ip in text:
        return text.replace(ip, "**.**.**.**")
    return text

async def mask_ip_in_page(page: Page, mode: int | None = None) -> None:
    """
    在页面的文本节点中根据模式替换 IP。
    mode: 0=关闭, 1=替换所有 IPv4/IPv6, 2=仅替换出口 IPv4。
    若 mode 为 None，则使用全局 IP_MASK_MODE。
    输出替换的节点数及页面文本预览（用于调试）。
    """
    if mode is None:
        mode = IP_MASK_MODE
    if mode == 0:
        return

    # 等待 object 结果页加载（如果有）
    try:
        await page.wait_for_selector('#results object', timeout=10000)
    except Exception:
        logger.debug("No #results object found, continuing")

    # 再等待 2 秒确保动态内容填充
    await page.wait_for_timeout(2000)

    try:
        ip = get_public_ip() if mode == 2 else None
    except Exception:
        ip = None

    # 构建 JavaScript 代码，包含 iframe/object/embed 递归处理
    if mode == 2:
        if not ip:
            logger.warning("No public IP available, skipping DOM masking")
            return
        escaped_ip = ip.replace('.', '\\.')
        js_code = f"""
            (function() {{
                const ip = '{ip}';
                const regex = new RegExp('{escaped_ip}', 'g');
                let totalCount = 0;
                let textPreview = '';

                function processDocument(doc) {{
                    if (!doc || !doc.body) return;
                    const walker = doc.createTreeWalker(
                        doc.body,
                        NodeFilter.SHOW_TEXT,
                        null,
                        false
                    );
                    let node;
                    while (node = walker.nextNode()) {{
                        const original = node.nodeValue;
                        textPreview += original.substring(0, 50) + ' ';
                        const replaced = original.replace(regex, '**.**.**.**');
                        if (replaced !== original) {{
                            node.nodeValue = replaced;
                            totalCount++;
                        }}
                    }}
                    // 递归处理 iframe, object, embed
                    const subFrames = doc.querySelectorAll('iframe, object, embed');
                    for (let el of subFrames) {{
                        try {{
                            let subDoc = null;
                            if (el.contentDocument) {{
                                subDoc = el.contentDocument;
                            }} else if (el.getSVGDocument) {{
                                subDoc = el.getSVGDocument();
                            }}
                            if (subDoc) processDocument(subDoc);
                        }} catch (e) {{ /* 跨域忽略 */ }}
                    }}
                }}

                processDocument(document);
                return {{ count: totalCount, preview: textPreview.slice(0, 1000) }};
            }})();
        """
    else:  # mode == 1
        js_code = """
            (function() {
                const ipv4Regex = /\\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\b/g;
                const ipv6Regex = /\\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\\b|\\b(?:[0-9a-fA-F]{1,4}:){1,7}:[0-9a-fA-F]{1,4}\\b|::[0-9a-fA-F]{1,4}\\b/gi;
                let totalCount = 0;
                let textPreview = '';

                function processDocument(doc) {
                    if (!doc || !doc.body) return;
                    const walker = doc.createTreeWalker(
                        doc.body,
                        NodeFilter.SHOW_TEXT,
                        null,
                        false
                    );
                    let node;
                    while (node = walker.nextNode()) {
                        const original = node.nodeValue;
                        textPreview += original.substring(0, 50) + ' ';
                        let replaced = original.replace(ipv4Regex, '**.**.**.**');
                        replaced = replaced.replace(ipv6Regex, '**:**:**:**:**:**:**:**:*');
                        if (replaced !== original) {
                            node.nodeValue = replaced;
                            totalCount++;
                        }
                    }
                    // 递归处理 iframe, object, embed
                    const subFrames = doc.querySelectorAll('iframe, object, embed');
                    for (let el of subFrames) {
                        try {
                            let subDoc = null;
                            if (el.contentDocument) {
                                subDoc = el.contentDocument;
                            } else if (el.getSVGDocument) {
                                subDoc = el.getSVGDocument();
                            }
                            if (subDoc) processDocument(subDoc);
                        } catch (e) { /* 跨域忽略 */ }
                    }
                }

                processDocument(document);
                return { count: totalCount, preview: textPreview.slice(0, 1000) };
            })();
        """

    try:
        result = await page.evaluate(js_code)
        count = result.get('count', 0)
        preview = result.get('preview', '')
        if count == 0:
            logger.warning(
                f"DOM IP masking applied (mode={mode}) but replaced 0 nodes. "
                f"Page text preview (first 1000 chars): {preview}"
            )
        else:
            logger.info(f"DOM IP masking applied (mode={mode}), replaced {count} text node(s)")
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