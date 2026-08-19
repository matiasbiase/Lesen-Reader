"""
Generates the app icons. Run by hand, once:
    ./.venv/bin/python backend/make_icons.py

The icon is the app's mark: a serif "l" on paper, struck through by a marker
stroke on the diagonal — the same gesture the app makes when you save a word.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

WEB = Path(__file__).resolve().parent.parent / "web" / "icons"
PAPER = (250, 248, 244)
INK = (28, 26, 23)
MARKER = (255, 206, 74)

FONTS = [
    "/System/Library/Fonts/Supplemental/Palatino.ttc",
    "/System/Library/Fonts/Supplemental/Georgia.ttf",
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    "/Library/Fonts/Arial.ttf",
]


def font_at(size: int):
    for f in FONTS:
        if Path(f).exists():
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                continue
    return ImageFont.load_default()


def make(size: int, maskable: bool = False) -> Image.Image:
    img = Image.new("RGB", (size, size), PAPER)
    d = ImageDraw.Draw(img, "RGBA")

    # the marker stroke, on the diagonal like in the app
    pad = size * (0.22 if maskable else 0.14)
    h = size * 0.30
    y = size * 0.545
    d.polygon([(pad, y - h / 2 + size * 0.022), (size - pad, y - h / 2 - size * 0.018),
               (size - pad, y + h / 2 - size * 0.018), (pad, y + h / 2 + size * 0.022)],
              fill=MARKER + (215,))

    # the "l" of lesen
    f = font_at(int(size * (0.5 if maskable else 0.62)))
    box = d.textbbox((0, 0), "l", font=f)
    d.text(((size - (box[2] - box[0])) / 2 - box[0],
            (size - (box[3] - box[1])) / 2 - box[1] - size * 0.02),
           "l", font=f, fill=INK)
    return img


if __name__ == "__main__":
    WEB.mkdir(parents=True, exist_ok=True)
    for name, size, mask in [("icon-180.png", 180, False), ("icon-192.png", 192, False),
                             ("icon-512.png", 512, False), ("icon-maskable-512.png", 512, True)]:
        make(size, mask).save(WEB / name)
        print("→", WEB / name)

    # iOS asks for these two at the root even when the <link> points elsewhere,
    # and Safari asks for favicon.ico. Without them that's three 404s a visit.
    root = WEB.parent
    icon180 = make(180)
    for name in ("apple-touch-icon.png", "apple-touch-icon-precomposed.png"):
        icon180.save(root / name)
        print("→", root / name)
    make(64).save(root / "favicon.ico", sizes=[(64, 64), (32, 32), (16, 16)])
    print("→", root / "favicon.ico")
