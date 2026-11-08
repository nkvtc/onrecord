"""Draw site/card.png, the 1200x630 preview image X and other sites show for a shared link.

Run after changing the wording:  uv run --with pillow python scripts/make_card.py
Uses Georgia and Segoe UI from Windows; pass font paths via CARD_SERIF / CARD_SANS elsewhere.
"""

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
BG, TEXT, MUTED, ACCENT, BORDER = "#121211", "#f0efec", "#a3a29a", "#3987e5", "#2e2d2b"
FONTS = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
SERIF_B = os.environ.get("CARD_SERIF", str(FONTS / "georgiab.ttf"))
SANS = os.environ.get("CARD_SANS", str(FONTS / "segoeui.ttf"))
SANS_B = os.environ.get("CARD_SANS_BOLD", str(FONTS / "segoeuib.ttf"))
OUT = Path(__file__).resolve().parents[1] / "site" / "card.png"

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)
pad = 72

# Wordmark
f = ImageFont.truetype(SERIF_B, 44)
d.text((pad, 60), "on", font=f, fill=TEXT)
d.text((pad + d.textlength("on", font=f), 60), "record", font=f, fill=ACCENT)

# Headline
f = ImageFont.truetype(SERIF_B, 66)
y = 170
for line in ["What the US government", "did, said and spent,", "on the record."]:
    d.text((pad, y), line, font=f, fill=TEXT)
    y += 82

# What's in it
f = ImageFont.truetype(SANS, 28)
d.text(
    (pad, y + 26),
    "Bills and votes · budget · executive orders · every named pardon since 1993 · trade",
    font=f,
    fill=MUTED,
)

# Footer
d.line([(pad, H - 92), (W - pad, H - 92)], fill=BORDER, width=2)
f = ImageFont.truetype(SANS_B, 26)
d.text((pad, H - 70), "Every figure linked to its official source", font=f, fill=TEXT)
f = ImageFont.truetype(SANS, 26)
note = "Open source · nkvtc.github.io/onrecord"
d.text((W - pad - d.textlength(note, font=f), H - 70), note, font=f, fill=MUTED)

img.save(OUT, optimize=True)
print(f"Wrote {OUT} ({OUT.stat().st_size // 1024} KB)")
