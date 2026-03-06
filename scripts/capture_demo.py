"""Capture a smooth, cursor-animated demo GIF of the Streamlit UI."""

from __future__ import annotations

import math
import shutil
import subprocess
import time
from pathlib import Path

from PIL import Image, ImageDraw
from playwright.sync_api import Page, sync_playwright

FRAMES_DIR = Path("data/demo_frames")
OUTPUT_GIF = Path("assets/demo.gif")
APP_URL = "http://127.0.0.1:8765"
VIEWPORT = {"width": 1440, "height": 900}
DEVICE_SCALE = 2
OUTPUT_WIDTH = 1100

# Cursor state
_frame_counter = 0
_cursor_x = 720.0  # CSS px (center of viewport)
_cursor_y = 450.0


def _ease_in_out_cubic(t: float) -> float:
    """Cubic ease-in-out for smooth cursor motion."""
    if t < 0.5:
        return 4 * t * t * t
    return 1 - (-2 * t + 2) ** 3 / 2


def _get_center(page: Page, selector: str) -> tuple[float, float]:
    """Get the center of an element in CSS px."""
    box = page.locator(selector).first.bounding_box()
    if box is None:
        return _cursor_x, _cursor_y
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def _draw_cursor(img: Image.Image, cx: float, cy: float) -> Image.Image:
    """Draw a classic pointer cursor at (cx, cy) in output-pixel coords."""
    frame = img.copy()
    draw = ImageDraw.Draw(frame)

    # Scale cursor to be clearly visible (~32px tall at 1100px width)
    s = (OUTPUT_WIDTH / 1100.0) * 1.8
    # Classic arrow cursor polygon (tip at 0,0)
    raw = [
        (0, 0), (0, 21), (6, 16.5), (9.5, 23.5),
        (12.5, 22), (9, 15), (15, 15),
    ]
    pts = [(cx + dx * s, cy + dy * s) for dx, dy in raw]

    # Shadow (darker, offset)
    shadow = [(x + 2 * s, y + 2 * s) for x, y in pts]
    draw.polygon(shadow, fill=(0, 0, 0, 60))
    # White fill + black outline
    draw.polygon(pts, fill="white", outline="black", width=max(1, round(1.2 * s)))
    return frame


def _css_to_output(cx: float, cy: float) -> tuple[float, float]:
    """Convert CSS viewport coords → output image coords."""
    scale = OUTPUT_WIDTH / VIEWPORT["width"]
    return cx * scale, cy * scale


def _capture(page: Page, cursor_css: tuple[float, float] | None = None) -> Path:
    """Take a screenshot and return its path. Stores cursor position for later."""
    global _frame_counter
    name = f"{_frame_counter:04d}"
    path = FRAMES_DIR / f"{name}.png"
    page.screenshot(path=str(path))

    # Store cursor position as metadata in filename-based sidecar
    if cursor_css:
        meta = FRAMES_DIR / f"{name}.cursor"
        meta.write_text(f"{cursor_css[0]},{cursor_css[1]}")

    _frame_counter += 1
    return path


def _hold(page: Page, duration_s: float, fps: int = 12) -> None:
    """Capture repeated frames to create a pause at current position."""
    n = max(1, int(duration_s * fps))
    for _ in range(n):
        _capture(page, (_cursor_x, _cursor_y))


def _move_cursor_to(
    page: Page, tx: float, ty: float, duration_s: float = 0.4, fps: int = 20
) -> None:
    """Animate cursor from current pos to (tx, ty) in CSS px, capturing frames."""
    global _cursor_x, _cursor_y
    sx, sy = _cursor_x, _cursor_y
    n = max(2, int(duration_s * fps))
    for i in range(1, n + 1):
        t = _ease_in_out_cubic(i / n)
        _cursor_x = sx + (tx - sx) * t
        _cursor_y = sy + (ty - sy) * t
        _capture(page, (_cursor_x, _cursor_y))


def _type_text(page: Page, selector: str, text: str, char_delay: float = 0.07) -> None:
    """Type text one character at a time, capturing a frame per character."""
    el = page.locator(selector).first
    el.click()
    time.sleep(0.15)
    # Capture the click frame
    _capture(page, (_cursor_x, _cursor_y))

    for ch in text:
        page.keyboard.type(ch, delay=0)
        time.sleep(char_delay)
        _capture(page, (_cursor_x, _cursor_y))


def _clear_input(page: Page, selector: str) -> None:
    """Select all and delete text in an input."""
    el = page.locator(selector).first
    el.click()
    page.keyboard.press("Control+a")
    page.keyboard.press("Backspace")
    time.sleep(0.1)


def _slide(page: Page, selector: str, steps: int, direction: str = "right", fps: int = 15) -> None:
    """Move slider incrementally, capturing frames with cursor on the thumb."""
    global _cursor_x, _cursor_y
    el = page.locator(selector).first
    el.click()
    time.sleep(0.1)

    key = "ArrowRight" if direction == "right" else "ArrowLeft"
    capture_every = max(1, steps // 30)  # ~30 frames for the slide
    for i in range(steps):
        page.keyboard.press(key)
        if i % capture_every == 0:
            # Read the actual thumb position from the DOM after each step
            thumb = page.locator(
                f"{selector} >> xpath=ancestor::div[contains(@class,'stSlider')]//div[@role='slider']"
            ).first
            tbox = thumb.bounding_box() if thumb.count() else None
            if tbox:
                cx = tbox["x"] + tbox["width"] / 2
                cy = tbox["y"] + tbox["height"] / 2
            else:
                # Fallback: estimate from the input's own bounding box
                box = el.bounding_box()
                if box:
                    progress = (i + 1) / steps
                    cx = box["x"] + box["width"] * (progress if direction == "right" else 1 - progress)
                    cy = box["y"] + box["height"] / 2
                else:
                    cx, cy = _cursor_x, _cursor_y
            _cursor_x, _cursor_y = cx, cy
            _capture(page, (cx, cy))


def _wait_rerun(page: Page, settle: float = 1.5) -> None:
    """Wait for Streamlit to rerun after an interaction."""
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    time.sleep(settle)


def _hide_streamlit_chrome(page: Page) -> None:
    """Hide the Streamlit toolbar, deploy button, and hamburger menu."""
    page.evaluate("""
        const style = document.createElement('style');
        style.textContent = `
            header[data-testid="stHeader"],
            #MainMenu, button[kind="header"],
            .stDeployButton, [data-testid="stToolbar"],
            [data-testid="stDecoration"],
            footer { display: none !important; visibility: hidden !important; }
            .stApp > header { display: none !important; }
            section[data-testid="stSidebar"] > div:first-child { padding-top: 1rem; }
        `;
        document.head.appendChild(style);
    """)
    time.sleep(0.3)


def wait_for_streamlit(page: Page, timeout: int = 30) -> None:
    """Wait for initial Streamlit load."""
    page.wait_for_load_state("networkidle", timeout=timeout * 1000)
    page.wait_for_selector(".hero", timeout=timeout * 1000)
    time.sleep(2.5)
    _hide_streamlit_chrome(page)


def main() -> None:
    global _cursor_x, _cursor_y, _frame_counter
    _frame_counter = 0
    _cursor_x, _cursor_y = 720.0, 450.0

    if FRAMES_DIR.exists():
        shutil.rmtree(FRAMES_DIR)
    FRAMES_DIR.mkdir(parents=True)
    OUTPUT_GIF.parent.mkdir(parents=True, exist_ok=True)

    search_sel = "input[aria-label='🔎 Search title/company/location']"
    slider_sel = "[aria-label='🎯 Minimum score']"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport=VIEWPORT,
            device_scale_factor=DEVICE_SCALE,
        )
        page = context.new_page()

        # ── 1  Load dashboard ──────────────────────────────────────────
        print("1/7  Loading dashboard...")
        page.goto(APP_URL)
        wait_for_streamlit(page)
        # Cursor starts near center
        _cursor_x, _cursor_y = 720, 350
        _hold(page, 2.5)  # Pause to admire

        # ── 2  Move to search & type ──────────────────────────────────
        print("2/7  Typing search query...")
        sx, sy = _get_center(page, search_sel)
        _move_cursor_to(page, sx, sy, duration_s=0.5)
        _type_text(page, search_sel, "Machine Learning", char_delay=0.06)
        page.keyboard.press("Enter")
        _wait_rerun(page, 2.5)
        _hold(page, 2.0)  # Show filtered results

        # ── 3  Clear search ───────────────────────────────────────────
        print("3/7  Clearing search...")
        _clear_input(page, search_sel)
        page.keyboard.press("Enter")
        _wait_rerun(page, 2.0)
        _hold(page, 0.5)

        # ── 4  Move to score slider & drag ────────────────────────────
        print("4/7  Adjusting score slider...")
        slx, sly = _get_center(page, slider_sel)
        # Move to left edge of slider
        sbox = page.locator(slider_sel).first.bounding_box()
        if sbox:
            slx = sbox["x"] + 10
            sly = sbox["y"] + sbox["height"] / 2
        _move_cursor_to(page, slx, sly, duration_s=0.4)
        _slide(page, slider_sel, 100, direction="right", fps=15)  # → 50.0
        _wait_rerun(page, 1.0)
        _hold(page, 1.8)  # Pause on filtered view

        # ── 5  Reset slider ───────────────────────────────────────────
        print("5/7  Resetting slider...")
        _slide(page, slider_sel, 100, direction="left", fps=15)  # back to 0
        _wait_rerun(page, 1.5)
        _hold(page, 0.5)

        # ── 6  Click a job "View Details" ─────────────────────────────
        print("6/7  Clicking job details...")
        view_buttons = page.locator("button:has-text('View Details')")
        if view_buttons.count() > 1:
            btn = view_buttons.nth(1)
            btn.scroll_into_view_if_needed()
            time.sleep(0.3)
            box = btn.bounding_box()
            if box:
                bx = box["x"] + box["width"] / 2
                by = min(box["y"] + box["height"] / 2, VIEWPORT["height"] - 20)
                _move_cursor_to(page, bx, by, duration_s=0.5)
            _capture(page, (_cursor_x, _cursor_y))
            btn.click()
            _wait_rerun(page, 2.0)
            # Move cursor to the right panel (job details area) so it stays visible
            _move_cursor_to(page, 950, 400, duration_s=0.4)
        _hold(page, 2.5)  # Read the details

        # ── 7  Click another job ──────────────────────────────────────
        print("7/7  Selecting another job...")
        view_buttons = page.locator("button:has-text('View Details')")
        if view_buttons.count() > 2:
            btn = view_buttons.nth(2)
            btn.scroll_into_view_if_needed()
            time.sleep(0.3)
            box = btn.bounding_box()
            if box:
                bx = box["x"] + box["width"] / 2
                by = min(box["y"] + box["height"] / 2, VIEWPORT["height"] - 20)
                _move_cursor_to(page, bx, by, duration_s=0.5)
            _capture(page, (_cursor_x, _cursor_y))
            btn.click()
            _wait_rerun(page, 2.0)
            # Move cursor to the right panel again
            _move_cursor_to(page, 950, 400, duration_s=0.4)
        _hold(page, 2.5)

        browser.close()

    # ── Post-process: add cursor & build GIF ──────────────────────────
    print(f"\nPost-processing {_frame_counter} frames...")
    frame_paths = sorted(FRAMES_DIR.glob("*.png"))

    output_frames: list[Image.Image] = []
    for fp in frame_paths:
        img = Image.open(fp).convert("RGBA")
        # Downscale from retina to output size
        ratio = OUTPUT_WIDTH / img.width
        target_h = int(img.height * ratio)
        img = img.resize((OUTPUT_WIDTH, target_h), Image.LANCZOS)
        # Convert to RGB
        rgb = Image.new("RGB", img.size, (255, 255, 255))
        rgb.paste(img, mask=img.split()[3])

        # Overlay cursor if position file exists
        cursor_file = fp.with_suffix(".cursor")
        if cursor_file.exists():
            cx_css, cy_css = cursor_file.read_text().split(",")
            ox, oy = _css_to_output(float(cx_css), float(cy_css))
            rgb = _draw_cursor(rgb, ox, oy)

        output_frames.append(rgb)

    if not output_frames:
        print("ERROR: No frames!")
        return

    print(f"Total frames: {len(output_frames)}")

    # Uniform frame duration for smooth playback (~12-15 fps feel)
    frame_duration_ms = 80  # 12.5 fps

    # Save with Pillow first
    output_frames[0].save(
        str(OUTPUT_GIF),
        save_all=True,
        append_images=output_frames[1:],
        duration=frame_duration_ms,
        loop=0,
        optimize=False,
    )

    raw_size = OUTPUT_GIF.stat().st_size / (1024 * 1024)
    print(f"Raw GIF: {raw_size:.1f} MB")

    # Try gifsicle optimization if available
    gifsicle = shutil.which("gifsicle")
    if gifsicle:
        print("Optimizing with gifsicle...")
        opt_path = OUTPUT_GIF.with_name("demo_opt.gif")
        subprocess.run(
            [
                gifsicle, "--optimize=3", "--colors", "192",
                "--lossy=40", str(OUTPUT_GIF), "-o", str(opt_path),
            ],
            check=False,
        )
        if opt_path.exists():
            opt_size = opt_path.stat().st_size / (1024 * 1024)
            print(f"Optimized GIF: {opt_size:.1f} MB")
            opt_path.replace(OUTPUT_GIF)
    else:
        print("gifsicle not found — trying ffmpeg for optimization...")
        # Use ffmpeg: gif → palette → optimized gif
        palette = FRAMES_DIR / "palette.png"
        tmp_gif = OUTPUT_GIF.with_name("demo_tmp.gif")
        # Generate palette
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(OUTPUT_GIF),
                "-vf", "fps=12,palettegen=max_colors=192:stats_mode=diff",
                str(palette),
            ],
            check=False, capture_output=True,
        )
        if palette.exists():
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(OUTPUT_GIF), "-i", str(palette),
                    "-lavfi", "fps=12 [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=3",
                    str(tmp_gif),
                ],
                check=False, capture_output=True,
            )
            if tmp_gif.exists():
                opt_size = tmp_gif.stat().st_size / (1024 * 1024)
                print(f"ffmpeg optimized: {opt_size:.1f} MB")
                tmp_gif.replace(OUTPUT_GIF)

    final_size = OUTPUT_GIF.stat().st_size / (1024 * 1024)
    print(f"\nFinal GIF: {OUTPUT_GIF}  ({final_size:.1f} MB, {len(output_frames)} frames)")


if __name__ == "__main__":
    main()
