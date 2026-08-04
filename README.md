# python_screenshot_web_firefox

The following is AI-generated(awa):

A Python asynchronous screenshot utility that captures web pages using **Playwright** with **Firefox**. It optionally injects cookies from a local Firefox profile, making it ideal for capturing authenticated or personalized pages.

---

## Features

- **Headless Firefox** – fast and reliable rendering.
- **Cookie injection** – load cookies directly from a Firefox cookie database (`cookies.sqlite`) to maintain sessions.
- **Customizable viewport** – set width, height, and device pixel ratio.
- **Full‑page screenshots** – capture entire scrollable content.
- **Flexible output** – returns bytes or saves to a file.
- **No built‑in security filters** – you control which URLs and cookies are used.

---

## Requirements

- Python 3.8+
- [Playwright](https://playwright.dev/python/) for Python
- Firefox browser (installed automatically by Playwright)

---

## Installation

1. **Clone or download** this script into your project.

2. **Install dependencies**:

```bash
pip install playwright
playwright install firefox
```

3. **Set the path to your Firefox cookie database** (optional, but required for cookie injection):

```bash
export FIREFOX_COOKIE_DB="/path/to/your/firefox/profile/cookies.sqlite"
```

On Windows, use `set` instead of `export`.

---

## Usage

### Basic example (asynchronous)

```python
import asyncio
from screenshot_web_firefox import capture_screenshot, capture_screenshot_bytes

async def main():
    # Save to default output folder (outputs/screenshots_web/)
    path, final_url = await capture_screenshot("https://example.com")
    print(f"Screenshot saved to {path}, final URL: {final_url}")

    # Get image bytes directly
    image_bytes, final_url = await capture_screenshot_bytes("https://example.com")
    # ... process image_bytes

asyncio.run(main())
```

### With cookie injection (authenticated pages)

```python
path, final_url = await capture_screenshot(
    "https://my.dashboard.com",
    inject_cookies=True,          # load cookies from Firefox DB
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
| `width` | `int` | `1400` | Viewport width (640‑4096) |
| `height` | `int` | `900` | Viewport height (480‑4096) |
| `inject_cookies` | `bool` | `False` | If `True`, loads and injects matching cookies from Firefox DB |
| `user_agent` | `str \| None` | `None` | Custom User‑Agent string |
| `full_page` | `bool` | `False` | Capture entire scrollable page (not just viewport) |
| `device_scale_factor` | `float` | `1.0` | Pixel ratio (0.1‑5.0) – higher = sharper images |

### `capture_screenshot(url, output_path=None, ...) -> tuple[Path, str]`

Same as above but saves the screenshot to a file.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `output_path` | `Path \| None` | `None` | Custom save path; if `None`, auto‑generated in `outputs/screenshots_web/` |

All other parameters are identical to `capture_screenshot_bytes`.

---

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `FIREFOX_COOKIE_DB` | Absolute path to Firefox’s `cookies.sqlite` file. Required for cookie injection. |

If not set, cookie injection will be skipped with a warning.

---

## Cookie Injection Details

- The script extracts cookies whose `host` field matches the target URL’s domain (including subdomains).
- Cookies are converted to Playwright’s format and injected **before** navigation.
- Expiration times are handled automatically.

> ⚠️ **Security note**: This script does **not** validate or filter URLs or cookies. Use it only with trusted inputs and in a controlled environment.

---

## Output Directory

Screenshots are saved (by default) to:

```
outputs/screenshots_web/<host>-<timestamp>.png
```

You can change this by modifying the `SCREENSHOT_DIR` constant at the top of the script.

---

## Troubleshooting

- **`FIREFOX_COOKIE_DB` not found** – ensure the path points to a valid `cookies.sqlite` file.
- **Navigation timeout** – the script waits up to 60 seconds; increase `timeout` inside `navigate_to_page` if needed.
- **Blank screenshot** – some pages may require additional waiting; you can add custom `page.wait_for_selector()` logic.

---

## License

This script is provided as‑is under the [MIT License](https://opensource.org/licenses/MIT).
