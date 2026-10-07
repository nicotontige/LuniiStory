"""Draws the application artwork: the icon in every format we ship, and the
banner the README opens with.

    python tools/make_icon.py

Run it when the artwork changes; the results are committed, so neither a build
nor the README depends on the fonts installed on the machine doing the drawing.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ICONS_DIR = ROOT / "luniistory" / "ui" / "icons"
ASSETS_DIR = ROOT / ".github" / "assets"

# The Lunii turquoise, with the deep end of it for the lettering: the same pair
# the application's header carries, so the mark and the window agree.
BACKGROUND = "#02D3BE"
MONOGRAM_COLOUR = "#0D2B28"

SIZE = 1024
CORNER = 0.225          # share of the side, close to the macOS squircle
MONOGRAM = "LS"
TRACKING = 0.05         # share of the side; Heavy sets L and S touching

BANNER = (1200, 400)
TAGLINE = "Community stories on your Lunii, in a couple of clicks"

# Geometric sans faces, in order of preference.
FONT_CANDIDATES = [
    ("/System/Library/Fonts/Avenir Next.ttc", 8),   # Avenir Next Heavy
    ("/System/Library/Fonts/Supplemental/Futura.ttc", 1),
    ("/Library/Fonts/Arial Bold.ttf", 0),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0),
    ("C:/Windows/Fonts/arialbd.ttf", 0),
]


def load_font(size):
    for path, index in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size, index=index)
            except OSError:
                continue
    raise SystemExit("No suitable font found; add one to FONT_CANDIDATES.")


def draw_icon(size=SIZE):
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([(0, 0), (size - 1, size - 1)], radius=int(size * CORNER), fill=BACKGROUND)

    font = load_font(int(size * 0.54))
    tracking = size * TRACKING

    # Each letter is placed by hand: drawn as one string, Heavy sets the L and
    # the S touching, and the pair lands off centre.
    boxes = [draw.textbbox((0, 0), letter, font=font) for letter in MONOGRAM]
    widths = [box[2] - box[0] for box in boxes]
    total = sum(widths) + tracking * (len(MONOGRAM) - 1)

    # Measure the real ink rather than the font metrics, so the monogram is
    # optically centred instead of sitting on its baseline.
    top = min(box[1] for box in boxes)
    bottom = max(box[3] for box in boxes)

    x = (size - total) / 2
    y = (size - (bottom - top)) / 2 - top
    for letter, box, width in zip(MONOGRAM, boxes, widths):
        draw.text((x - box[0], y), letter, font=font, fill=MONOGRAM_COLOUR)
        x += width + tracking

    return image


def write_png(image):
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    target = ICONS_DIR / "icon.png"
    image.save(target)
    return target


def write_ico(image):
    target = ICONS_DIR / "icon.ico"
    sizes = [(size, size) for size in (16, 24, 32, 48, 64, 128, 256)]
    image.save(target, format="ICO", sizes=sizes)
    return target


def write_icns(image):
    """macOS bundle icon, built with the system tool when it is available."""
    if sys.platform != "darwin":
        print("  icns skipped: iconutil only exists on macOS")
        return None

    target = ICONS_DIR / "icon.icns"
    with tempfile.TemporaryDirectory() as work:
        iconset = Path(work) / "icon.iconset"
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            image.resize((size, size), Image.LANCZOS).save(iconset / f"icon_{size}x{size}.png")
            image.resize((size * 2, size * 2), Image.LANCZOS).save(
                iconset / f"icon_{size}x{size}@2x.png"
            )
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(target)], check=True)
    return target


def write_banner(image):
    """Header image for the README: the mark, the name and what it does."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    target = ASSETS_DIR / "banner.png"

    banner = Image.new("RGB", BANNER, BACKGROUND)
    draw = ImageDraw.Draw(banner)

    mark = 208
    left, top = 108, (BANNER[1] - mark) // 2
    banner.paste(image.resize((mark, mark), Image.LANCZOS), (left, top), image.resize((mark, mark), Image.LANCZOS))

    text_left = left + mark + 56
    room = BANNER[0] - text_left - 108
    name_font = load_font(104)

    # Shrink the tagline until it fits rather than letting it run off the edge.
    size = 34
    while size > 14:
        tagline_font = load_font(size)
        if draw.textlength(TAGLINE, font=tagline_font) <= room:
            break
        size -= 1

    name_box = draw.textbbox((0, 0), "luniiStory", font=name_font)
    tagline_box = draw.textbbox((0, 0), TAGLINE, font=tagline_font)
    block = (name_box[3] - name_box[1]) + 26 + (tagline_box[3] - tagline_box[1])
    y = (BANNER[1] - block) // 2

    draw.text((text_left - name_box[0], y - name_box[1]), "luniiStory", font=name_font, fill=MONOGRAM_COLOUR)
    draw.text(
        (text_left - tagline_box[0], y + (name_box[3] - name_box[1]) + 26 - tagline_box[1]),
        TAGLINE, font=tagline_font, fill="#0D4B44",
    )

    banner.save(target)
    return target


def main():
    image = draw_icon()
    for writer in (write_png, write_ico, write_icns, write_banner):
        written = writer(image)
        if written:
            print(f"  {written.relative_to(ROOT)}  {written.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
