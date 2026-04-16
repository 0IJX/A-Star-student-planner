from PIL import Image
from pathlib import Path

# Paths
src = Path(__file__).parent / "kid-icon.png"
dst = Path(__file__).parent / "app.ico"

# Open and crop to square
img = Image.open(src).convert("RGBA")
side = min(img.width, img.height)
left = (img.width - side) // 2
top = (img.height - side) // 2
img = img.crop((left, top, left + side, top + side))

# Save as multi-size .ico with high-quality resizing
sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256), (512, 512)]
icons = [img.resize(size, Image.LANCZOS) for size in sizes]
icons[0].save(dst, format="ICO", sizes=sizes, append_images=icons[1:])
print(f"Updated: {dst} (LANCZOS resampling)")
