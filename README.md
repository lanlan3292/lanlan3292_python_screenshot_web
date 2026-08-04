# python_screenshot_web_firefox (lanlan3292_python_screenshot_web)

The following is AI-generated(awa):

An asynchronous web screenshot tool powered by **Playwright** + **Firefox**.  
It supports optional cookie injection from a local Firefox profile, full‑page scrolling with lazy‑load handling, and resource blocking for faster captures.

---

## Features

- **Headless Firefox** – fast, reliable rendering.
- **Cookie injection** – load cookies from Firefox’s `cookies.sqlite` to keep sessions alive.
- **Full‑page screenshots** – automatically scrolls to trigger lazy‑loaded content, with safeguards against infinite scroll.
- **Media blocking** – optionally block images and videos to reduce bandwidth and speed up captures.
- **Customisable viewport** – set width, height, and device pixel ratio.
- **Output flexibility** – return raw bytes or save directly to a file.
- **No built‑in security filters** – you control which URLs and cookies are used.

---

## Requirements

- Python 3.8+
- [Playwright](https://playwright.dev/python/) for Python
- Firefox browser (installed automatically by Playwright)

---

## Installation

```bash
pip install git+https://github.com/lanlan3292/lanlan3292_python_screenshot_web.git
```

or

1. **Clone or download** this repository.

2. **Install dependencies**:

```bash
pip install playwright
playwright install firefox
```

3. **Set the path to your Firefox cookie database**  
   (optional – only required if you plan to use cookie injection):

```bash
export FIREFOX_COOKIE_DB="/path/to/your/firefox/profile/cookies.sqlite"
```

On Windows, use `set` instead of `export`.

---

## Usage

### Basic example (asynchronous)

```python
import asyncio
from lanlan3292_python_screenshot_web.firefox import capture_screenshot, capture_screenshot_bytes

async def main():
    # Save to default output folder (output/lanlan3292_python_screenshot_web/)
    path, final_url = await capture_screenshot("https://example.com")
    print(f"Screenshot saved to {path}, final URL: {final_url}")

    # Get image bytes directly
    image_bytes, final_url = await capture_screenshot_bytes("https://example.com")
    # ... process image_bytes

asyncio.run(main())
```

```python
import asyncio
from lanlan3292_python_screenshot_web.chromium import capture_screenshot

async def main():
    target_url = "https://example.com"
    
    print("...")
    file_path, final_url = await capture_screenshot(
        url=target_url,
        device_scale_factor=1.0
    )
    
    print(f"done!")
    print(f"here: {file_path}")
    print(f"final: {final_url}")

if __name__ == "__main__":
    asyncio.run(main())
```

### With cookie injection and media blocking

```python
path, final_url = await capture_screenshot(
    "https://en.wikipedia.org/wiki/Python_(programming_language)",
    inject_cookies=True,          # load cookies from Firefox DB
    block_media=True,             # block images/videos for faster loading
    width=1920,
    height=1080,
    full_page=True,
    device_scale_factor=2.0       # retina‑like quality
)
```

---

## API Reference

### `capture_screenshot_bytes(url, ...) -> tuple[bytes, str]`

Captures a screenshot and returns `(image_bytes, final_url)`.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | `str` | **required** | Target URL (scheme optional, `https` assumed) |
| `width` | `int` | `1400` | Viewport width (640–4096) |
| `height` | `int` | `900` | Viewport height (480–4096) |
| `inject_cookies` | `bool` | `False` | If `True`, injects matching cookies from Firefox DB |
| `user_agent` | `str \| None` | `None` | Custom User‑Agent string |
| `full_page` | `bool` | `False` | Capture entire scrollable page (not just viewport) |
| `device_scale_factor` | `float` | `1.0` | Pixel ratio (0.1–5.0) – higher = sharper images |
| `max_scrolls` | `int` | `15` | Max scroll steps for full‑page lazy‑loading (prevents infinite scroll) |
| `max_stable_before_break` | `int` | `3` | Stop scrolling if page height stays unchanged for this many consecutive scrolls |
| `block_media` | `bool` | `False` | If `True`, blocks image and media resources (speeds up loading) |

### `capture_screenshot(url, output_path=None, ...) -> tuple[Path, str]`

Same as above but saves the screenshot to a file.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `output_path` | `Path \| None` | `None` | Custom save path; if `None`, auto‑generated in `output/lanlan3292_python_screenshot_web/` |

All other parameters are identical to `capture_screenshot_bytes`.

---

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `FIREFOX_COOKIE_DB` | Absolute path to Firefox’s `cookies.sqlite` file. Required for cookie injection. |

If not set, cookie injection will be skipped with a warning.

---

## Cookie Injection Details

- Cookies are matched by domain (including subdomains) using the `host` field from the Firefox database.
- They are converted to Playwright’s format and injected **before** navigation.
- Expiration times are automatically converted to seconds.

> ⚠️ **Security note**: The script does **not** perform any validation or filtering of URLs or cookies. Use it only with trusted inputs and in a controlled environment.

---

## Full‑Page Scrolling Behaviour

When `full_page=True`, the script:

1. Scrolls down step‑by‑step (one viewport height at a time) to trigger lazy‑loaded content.
2. Stops when either:
   - the page height stops increasing for `max_stable_before_break` consecutive scrolls, or
   - the maximum scroll count (`max_scrolls`) is reached.
3. Scrolls back to the top before taking the screenshot.

This ensures consistent captures even for dynamic, infinite‑scroll pages.

---

## Output Directory

Screenshots are saved (by default) to:

```
output/lanlan3292_python_screenshot_web/<host>-<timestamp>.png
```

You can change this by modifying the `SCREENSHOT_DIR` constant in `firefox.py`.

---

## Troubleshooting

- **`FIREFOX_COOKIE_DB` not found** – ensure the path points to a valid `cookies.sqlite` file.
- **Navigation timeout** – the script waits up to 60 seconds; you can modify the `timeout` inside `navigate_to_page` if needed.
- **Blank or partial screenshot** – some pages may require additional waiting. You can insert custom `page.wait_for_selector()` logic before the screenshot.
- **Infinite scroll not fully captured** – increase `max_scrolls` or `max_stable_before_break` to allow more scroll steps.