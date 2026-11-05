import math
from PIL import Image, ImageDraw, ImageFilter

def render_arc_reactor(canvas_size=1024):
    """Render an ultra high-res smooth antialiased Stark Arc Reactor icon."""
    size = canvas_size
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    center = size / 2.0

    # Glow layer
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)

    r_outer = size * 0.46
    # Outer dark titanium bezel
    draw.ellipse(
        [center - r_outer, center - r_outer, center + r_outer, center + r_outer],
        fill=(12, 14, 18, 255),
        outline=(30, 41, 59, 255),
        width=int(size * 0.022)
    )

    # Outer cyan glow ring
    r_ring_outer = size * 0.40
    r_ring_inner = size * 0.33
    r_ring_mid = (r_ring_outer + r_ring_inner) / 2.0

    glow_draw.ellipse(
        [center - r_ring_outer, center - r_ring_outer, center + r_ring_outer, center + r_ring_outer],
        outline=(0, 210, 255, 120),
        width=int(size * 0.08)
    )

    draw.ellipse(
        [center - r_ring_outer, center - r_ring_outer, center + r_ring_outer, center + r_ring_outer],
        outline=(0, 220, 255, 240),
        width=int(size * 0.038)
    )

    # 10 Energy Coils
    num_coils = 10
    for i in range(num_coils):
        angle = (2 * math.pi / num_coils) * i
        x1 = center + (r_ring_inner - size * 0.01) * math.cos(angle)
        y1 = center + (r_ring_inner - size * 0.01) * math.sin(angle)
        x2 = center + (r_ring_outer + size * 0.01) * math.cos(angle)
        y2 = center + (r_ring_outer + size * 0.01) * math.sin(angle)
        # Block notch
        draw.line([(x1, y1), (x2, y2)], fill=(12, 14, 18, 255), width=int(size * 0.045))
        # Core glowing filament
        draw.line([(x1, y1), (x2, y2)], fill=(56, 189, 248, 255), width=int(size * 0.016))
        draw.line([(x1, y1), (x2, y2)], fill=(224, 247, 250, 255), width=int(size * 0.006))

    # Inner mid bezel ring
    r_mid = size * 0.28
    draw.ellipse(
        [center - r_mid, center - r_mid, center + r_mid, center + r_mid],
        outline=(14, 165, 233, 220),
        width=int(size * 0.02)
    )

    # Mark VI Inverted Triangle Core
    r_tri = size * 0.22
    tri_points = []
    for i in range(3):
        a = (2 * math.pi / 3) * i + (math.pi / 2)
        tri_points.append((center + r_tri * math.cos(a), center + r_tri * math.sin(a)))

    glow_draw.polygon(tri_points, fill=(0, 210, 255, 100))
    draw.polygon(tri_points, fill=(8, 20, 36, 250), outline=(0, 229, 255, 255))
    draw.line(tri_points + [tri_points[0]], fill=(0, 229, 255, 255), width=int(size * 0.03))

    # Inner luminous triangle
    r_tri_inner = size * 0.14
    tri_inner_pts = []
    for i in range(3):
        a = (2 * math.pi / 3) * i + (math.pi / 2)
        tri_inner_pts.append((center + r_tri_inner * math.cos(a), center + r_tri_inner * math.sin(a)))
    draw.polygon(tri_inner_pts, fill=(165, 243, 252, 240))

    # Radiant core spark
    r_core = size * 0.06
    draw.ellipse(
        [center - r_core, center - r_core, center + r_core, center + r_core],
        fill=(255, 255, 255, 255)
    )

    # Blur glow slightly and composite
    glow = glow.filter(ImageFilter.GaussianBlur(radius=int(size * 0.015)))
    final_img = Image.alpha_composite(glow, img)
    return final_img

def main():
    hi_res = render_arc_reactor(1024)
    # Downsample to 256x256 using Lanczos for flawless antialiasing
    img_256 = hi_res.resize((256, 256), Image.Resampling.LANCZOS)
    img_256.save("jarvis.png", format="PNG")

    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icon_images = [hi_res.resize(s, Image.Resampling.LANCZOS) for s in sizes]
    icon_images[-1].save(
        "jarvis.ico",
        format="ICO",
        sizes=sizes,
        append_images=icon_images[:-1]
    )
    print("Flawless antialiased jarvis.png and jarvis.ico generated!")

if __name__ == "__main__":
    main()
