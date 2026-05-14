"""Genera assets/icon.ico (16/32/48/256 px) para Generador de Pagos."""
from pathlib import Path
from PIL import Image, ImageDraw

BG    = (30,  30,  46,  255)   # #1e1e2e
BLUE  = (74, 158, 255,  255)   # #4a9eff
WHITE = (240, 242, 255,  255)  # blanco levemente azulado
BLUE_A = (74, 158, 255,  180)  # azul semitransparente para líneas


def _rrect(draw, x0, y0, x1, y1, r, fill):
    draw.rectangle([x0+r, y0,   x1-r, y1  ], fill=fill)
    draw.rectangle([x0,   y0+r, x1,   y1-r], fill=fill)
    for cx, cy in [(x0, y0), (x1-2*r, y0), (x0, y1-2*r), (x1-2*r, y1-2*r)]:
        draw.ellipse([cx, cy, cx+2*r, cy+2*r], fill=fill)


SS = 4  # factor de supersampling


def _make(base: int) -> Image.Image:
    S = base * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Fondo — rounded square oscuro
    m = max(1, int(S * 0.04))
    _rrect(d, m, m, S-m-1, S-m-1, int(S * 0.17), BG)

    # Documento blanco (izquierda/centro)
    dl, dt = int(S * 0.19), int(S * 0.14)
    dr, db = int(S * 0.67), int(S * 0.76)
    _rrect(d, dl, dt, dr, db, int(S * 0.04), WHITE)

    # Líneas azules (filas de datos en el documento)
    lx0 = dl + int(S * 0.07)
    lx1 = dr - int(S * 0.09)
    lh  = max(1, int(S * 0.025))
    for yf in (0.29, 0.40, 0.51, 0.62):
        y = int(S * yf)
        d.rectangle([lx0, y, lx1, y + lh], fill=BLUE_A)

    # Círculo azul (botón de envío, abajo-derecha)
    cr = int(S * 0.205)
    cx = int(S * 0.695)
    cy = int(S * 0.700)
    d.ellipse([cx-cr, cy-cr, cx+cr, cy+cr], fill=BLUE)

    # Flecha blanca hacia arriba dentro del círculo
    aw = int(cr * 0.46)
    ah = int(cr * 0.72)
    ty = cy - ah
    d.polygon([(cx, ty), (cx - aw, ty + aw), (cx + aw, ty + aw)], fill=WHITE)
    sw = max(1, int(aw * 0.52))
    d.rectangle([cx - sw, ty + aw, cx + sw, cy + int(ah * 0.28)], fill=WHITE)

    return img.resize((base, base), Image.LANCZOS)


def main() -> None:
    sizes  = [256, 48, 32, 16]
    frames = [_make(s) for s in sizes]

    out = Path(__file__).parent.parent / "assets" / "icon.ico"
    frames[0].save(
        out,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=frames[1:],
    )
    kb = out.stat().st_size // 1024
    print(f"OK -> {out}  ({kb} KB)")


if __name__ == "__main__":
    main()
