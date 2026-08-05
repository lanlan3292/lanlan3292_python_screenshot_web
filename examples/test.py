import asyncio
import time
from pathlib import Path
import logging
import base64
import webbrowser
import tempfile

from lanlan3292_python_screenshot_web.firefox import capture_screenshot

logging.basicConfig(level=logging.INFO)

async def main():
    target_url = "https://example.com"
    print("...")

    image_bytes, final_url = await capture_screenshot(
        url=target_url,
        device_scale_factor=2.0,
        width=1920,
        height=1080,
    )

    #output_dir = Path.cwd() / "screenshots"
    #output_dir.mkdir(exist_ok=True)
    #file_path = output_dir / f"screenshot-{int(time.time())}.png"
    #file_path.write_bytes(image_bytes)

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:image/png;base64,{b64}"
    #webbrowser.open(data_url)
    temp_html = Path(tempfile.gettempdir()) / "preview_screenshot.html"
    temp_html.write_text(
        f'<html><body style="background:#222;display:flex;justify-content:center;"><img src="{data_url}"/></body></html>',
        encoding="utf-8",
    )
    webbrowser.open(temp_html.as_uri())

    print("done")
    #print(f"file: {file_path}")
    print(f"size: {len(image_bytes)} bytes")
    #print(f"{data_url}")
    print(f"{temp_html}")
    print(f"final: {final_url}")

if __name__ == "__main__":
    asyncio.run(main())