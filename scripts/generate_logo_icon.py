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


def transparent_logo(size: int) -> Image.Image:
    image = Image.open(SOURCE).convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
    pixels = []
    for red, green, blue, _ in image.getdata():
        # Remove the white JPG background while retaining the soft logo highlights.
        alpha = max(0, 255 - min(red, green, blue))
        pixels.append((red, green, blue, alpha))
    image.putdata(pixels)
    return image


def full_logo(size: int) -> Image.Image:
    return Image.open(SOURCE).convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)


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
