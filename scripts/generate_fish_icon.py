from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
RESOURCE_ROOTS = [
    ROOT / "template" / "{{ cookiecutter.format }}" / "app" / "src" / "main" / "res",
    ROOT / "build" / "python" / "android" / "gradle" / "app" / "src" / "main" / "res",
]
DENSITIES = {
    "mdpi": 48,
    "hdpi": 72,
    "xhdpi": 96,
    "xxhdpi": 144,
    "xxxhdpi": 192,
}

# Draw at 4x and downsample so the small launcher assets stay crisp.
SCALE = 4
BG = (9, 53, 76, 255)
BODY = (245, 174, 55, 255)

FIN = (24, 155, 165, 255)
FIN_DARK = (13, 105, 126, 255)
INK = (8, 43, 58, 255)
WHITE = (255, 255, 255, 255)


def points(values: list[tuple[float, float]]) -> list[tuple[int, int]]:
    return [(round(x * SCALE), round(y * SCALE)) for x, y in values]


def draw_fish(size: int, *, background: bool) -> Image.Image:
    canvas = Image.new("RGBA", (size * SCALE, size * SCALE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    s = size * SCALE

    if background:
        draw.ellipse((0, 0, s - 1, s - 1), fill=BG)
        # A subtle inner ring keeps the icon readable against dark launchers.
        draw.ellipse((round(s * .055), round(s * .055), round(s * .945), round(s * .945)), outline=(62, 196, 196, 255), width=max(1, round(s * .018)))

    # Fish body and tail share the same coordinate system so the silhouette stays aligned.
    cx, cy = size * .52, size * .52
    body_box = (size * .25, size * .30, size * .79, size * .70)
    tail = [(size * .29, size * .50), (size * .08, size * .30), (size * .13, size * .50), (size * .08, size * .70)]
    draw.polygon(points(tail), fill=FIN_DARK)
    draw.ellipse(tuple(round(v * SCALE) for v in body_box), fill=BODY, outline=INK, width=max(2, round(size * .035 * SCALE)))

    # Upper and lower fins.
    draw.polygon(points([(size * .45, size * .33), (size * .54, size * .15), (size * .62, size * .34)]), fill=FIN, outline=INK)
    draw.polygon(points([(size * .47, size * .67), (size * .55, size * .84), (size * .64, size * .66)]), fill=FIN, outline=INK)
    # Fin highlights.
    draw.line(points([(size * .51, size * .22), (size * .55, size * .30)]), fill=(117, 229, 214, 255), width=max(1, round(size * .018 * SCALE)))

    # Eye, gill, and a small body highlight.
    eye_r = size * .055
    draw.ellipse((round((cx + size * .13 - eye_r) * SCALE), round((cy - size * .09 - eye_r) * SCALE), round((cx + size * .13 + eye_r) * SCALE), round((cy - size * .09 + eye_r) * SCALE)), fill=WHITE, outline=INK, width=max(1, round(size * .018 * SCALE)))
    pupil_r = size * .018
    draw.ellipse((round((cx + size * .145 - pupil_r) * SCALE), round((cy - size * .09 - pupil_r) * SCALE), round((cx + size * .145 + pupil_r) * SCALE), round((cy - size * .09 + pupil_r) * SCALE)), fill=INK)
    draw.arc(tuple(round(v * SCALE) for v in (size * .48, size * .40, size * .67, size * .62)), start=285, end=75, fill=INK, width=max(1, round(size * .018 * SCALE)))
    draw.ellipse(tuple(round(v * SCALE) for v in (size * .34, size * .39, size * .43, size * .47)), fill=(255, 224, 135, 255))

    # Two bubbles reinforce the fish theme without crowding the adaptive-icon safe zone.
    for x, y, r in ((.77, .22, .055), (.86, .13, .035)):
        draw.ellipse(tuple(round(v * SCALE) for v in (size * (x-r), size * (y-r), size * (x+r), size * (y+r))), outline=WHITE, width=max(1, round(size * .014 * SCALE)))

    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def save_icons(resource_root: Path) -> None:
    for density, size in DENSITIES.items():
        folder = resource_root / f"mipmap-{density}"
        folder.mkdir(parents=True, exist_ok=True)
        draw_fish(size * 9 // 4, background=False).save(folder / "ic_launcher_foreground.png")
        draw_fish(size, background=True).save(folder / "ic_launcher.png")
        draw_fish(size, background=True).save(folder / "ic_launcher_round.png")


if __name__ == "__main__":
    for root in RESOURCE_ROOTS:
        if root.exists():
            save_icons(root)
