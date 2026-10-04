from __future__ import annotations

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "logo02.png"
RESOURCE_ROOTS = (
    ROOT / "template" / "{{ cookiecutter.format }}" / "app" / "src" / "main" / "res",
    ROOT / "build" / "python" / "android" / "gradle" / "app" / "src" / "main" / "res",
)
DENSITIES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
ICON_CONTENT_RATIO = 0.84


def resized_on_canvas(size: int, *, transparent: bool) -> Image.Image:
    """Keep the logo crisp while leaving a consistent white border around it."""
    source = Image.open(SOURCE).convert("RGBA")
    inner_size = max(1, round(size * ICON_CONTENT_RATIO))
    inner = source.resize((inner_size, inner_size), Image.Resampling.LANCZOS)
    background = (0, 0, 0, 0) if transparent else (255, 255, 255, 255)
    canvas = Image.new("RGBA", (size, size), background)
    offset = (size - inner_size) // 2
    canvas.alpha_composite(inner, (offset, offset))
    return canvas


def transparent_logo(size: int) -> Image.Image:
    image = resized_on_canvas(size, transparent=True)
    pixels = []
    for red, green, blue, alpha in image.getdata():
        # Remove the white JPG background while retaining the soft logo highlights.
        pixels.append((red, green, blue,
                       0 if alpha == 0 else max(0, 255 - min(red, green, blue))))
    image.putdata(pixels)
    return image


def full_logo(size: int) -> Image.Image:
    return resized_on_canvas(size, transparent=False)


def write_resources(resource_root: Path) -> None:
    if not resource_root.exists():
        return
    transparent_logo(432).save(resource_root / "drawable" / "logo_foreground.png")
    for density, size in DENSITIES.items():
        folder = resource_root / f"mipmap-{density}"
        folder.mkdir(parents=True, exist_ok=True)
        transparent_logo(size).save(folder / "ic_launcher_foreground.png")
        full_logo(size).save(folder / "ic_launcher.png")
        full_logo(size).save(folder / "ic_launcher_round.png")
        full_logo(size * 20 // 3).convert("L").save(folder / "splash.png")


if __name__ == "__main__":
    for resource_root in RESOURCE_ROOTS:
        write_resources(resource_root)
