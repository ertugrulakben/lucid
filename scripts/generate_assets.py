import os

from PIL import Image, ImageDraw, ImageFont

# Ensure docs dir exists
os.makedirs("docs", exist_ok=True)

# --- hero.png (1280x640) ---
width, height = 1280, 640
img = Image.new("RGB", (width, height), color="#0a0a0f")
draw = ImageDraw.Draw(img)

# Simple vertical gradient
for y in range(height):
    r = int(10 + (20 - 10) * (y / height))
    g = int(10 + (25 - 10) * (y / height))
    b = int(15 + (40 - 15) * (y / height))
    draw.line([(0, y), (width, y)], fill=(r, g, b))

# Draw a subtle spotlight circle in the center-top
for radius in range(300, 0, -5):
    alpha = int(20 * (radius / 300))
    color = (20 + alpha, 30 + alpha, 60 + alpha)
    draw.ellipse([width // 2 - radius, height // 3 - radius, width // 2 + radius, height // 3 + radius], outline=color, width=5)

# Use default font (no external font dependency)
try:
    font_large = ImageFont.truetype("arial.ttf", 96)
    font_medium = ImageFont.truetype("arial.ttf", 36)
    font_small = ImageFont.truetype("arial.ttf", 24)
except Exception:
    font_large = ImageFont.load_default()
    font_medium = ImageFont.load_default()
    font_small = ImageFont.load_default()

# Title
title = "Lucid"
bbox = draw.textbbox((0, 0), title, font=font_large)
text_w = bbox[2] - bbox[0]
draw.text(((width - text_w) // 2, height // 2 - 80), title, fill="#ffffff", font=font_large)

# Tagline
tagline = "Spotlight-style desktop AI agent for Windows"
bbox = draw.textbbox((0, 0), tagline, font=font_medium)
text_w = bbox[2] - bbox[0]
draw.text(((width - text_w) // 2, height // 2 + 40), tagline, fill="#a0b0d0", font=font_medium)

# Shortcut hint
hint = "Press Ctrl + Alt + J"
bbox = draw.textbbox((0, 0), hint, font=font_small)
text_w = bbox[2] - bbox[0]
draw.text(((width - text_w) // 2, height // 2 + 110), hint, fill="#607080", font=font_small)

img.save("docs/hero.png", "PNG")
print("Saved docs/hero.png")

# --- demo.gif (640x320, 12fps, ~3s) ---
frames = []
w, h = 640, 320
num_frames = 36

for i in range(num_frames):
    frame = Image.new("RGB", (w, h), color="#0a0a0f")
    d = ImageDraw.Draw(frame)
    # Background gradient
    for y in range(h):
        rr = int(10 + (15 - 10) * (y / h))
        gg = int(10 + (18 - 10) * (y / h))
        bb = int(15 + (30 - 15) * (y / h))
        d.line([(0, y), (w, y)], fill=(rr, gg, bb))

    # Overlay bar appearing (first 12 frames: fade in + slide down)
    bar_y = 20
    alpha_bar = min(255, int(255 * (i / 12))) if i < 12 else 255
    bar_color = (20, 25, 40, alpha_bar)
    # Draw rounded rect manually
    d.rounded_rectangle([80, bar_y, w - 80, bar_y + 50], radius=25, fill=(25, 30, 50), outline=(50, 60, 90), width=2)

    # Text typing animation
    text = "Send email to Alice about the report"
    chars_to_show = min(len(text), max(0, (i - 6) * 2))
    shown = text[:chars_to_show]
    try:
        fnt = ImageFont.truetype("arial.ttf", 20)
    except Exception:
        fnt = ImageFont.load_default()
    d.text((100, bar_y + 14), shown, fill="#ffffff", font=fnt)
    # Blinking cursor
    if i % 6 < 3 and chars_to_show < len(text):
        bbox = d.textbbox((100, bar_y + 14), shown, font=fnt)
        cursor_x = bbox[2] if shown else 100
        d.rectangle([cursor_x + 2, bar_y + 14, cursor_x + 4, bar_y + 36], fill="#ffffff")

    # Mode tabs appearing after frame 14
    if i > 14:
        modes = ["Answer", "Teach", "Execute"]
        tab_x = 100
        for idx, mode in enumerate(modes):
            active = idx == 2  # Execute highlighted
            bg = (40, 50, 80) if active else (25, 30, 45)
            fg = "#ffffff" if active else "#8899aa"
            d.rounded_rectangle([tab_x, bar_y + 60, tab_x + 80, bar_y + 90], radius=12, fill=bg)
            d.text((tab_x + 10, bar_y + 64), mode, fill=fg, font=fnt)
            tab_x += 90

    # Action log sliding in after frame 24
    if i > 24:
        log_alpha = min(255, int(255 * ((i - 24) / 8)))
        log_bg = (15, 18, 30)
        d.rounded_rectangle([120, h - 100, w - 120, h - 20], radius=12, fill=log_bg, outline=(40, 50, 70), width=1)
        d.text((140, h - 85), "click_element \"Send\"", fill="#66ff99", font=fnt)
        d.text((140, h - 60), "typewrite \"Hello Alice...\"", fill="#66ff99", font=fnt)

    frames.append(frame)

# Save GIF
frames[0].save(
    "docs/demo.gif",
    save_all=True,
    append_images=frames[1:],
    duration=int(1000 / 12),
    loop=0,
    optimize=True,
)
print("Saved docs/demo.gif")
