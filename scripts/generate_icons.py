from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "resources"
RESOURCES.mkdir(exist_ok=True)


def draw_icon(size: int) -> Image.Image:
    scale = 4
    canvas = size * scale
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    radius = int(canvas * 0.22)
    draw.rounded_rectangle(
        (0, 0, canvas - 1, canvas - 1),
        radius=radius,
        fill=(15, 23, 42, 255),
    )

    margin = int(canvas * 0.24)
    points = [
        (margin, int(canvas * 0.64)),
        (int(canvas * 0.42), int(canvas * 0.50)),
        (int(canvas * 0.56), int(canvas * 0.57)),
        (canvas - margin, int(canvas * 0.32)),
    ]
    line_width = max(2, int(canvas * 0.055))
    draw.line(points, fill=(52, 211, 153, 255), width=line_width, joint="curve")

    dot_radius = max(2, int(canvas * 0.035))
    for x, y in points:
        draw.ellipse(
            (x - dot_radius, y - dot_radius, x + dot_radius, y + dot_radius),
            fill=(255, 255, 255, 255),
        )

    tip_x, tip_y = points[-1]
    arrow = max(2, int(canvas * 0.075))
    draw.polygon(
        [
            (tip_x, tip_y - arrow),
            (tip_x - arrow, tip_y + int(arrow * 0.35)),
            (tip_x + int(arrow * 0.25), tip_y + arrow),
        ],
        fill=(52, 211, 153, 255),
    )

    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    icon = draw_icon(256)
    icon.save(RESOURCES / "icon.png")
    icon.save(
        RESOURCES / "icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    draw_icon(32).save(RESOURCES / "tray.png")
    print("icons written")


if __name__ == "__main__":
    main()
