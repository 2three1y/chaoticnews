#!/usr/bin/env python3
"""Social card images (link previews) for Chaotic News.

Called by tools/add_story.py on every build. Draws an original 1200x630 PNG
title card for each story, each section and the site, in the same style as the
on-page SVG title cards: CN logo bug, section colours, the headline, and a
SATIRE tag on the card itself so a screenshot can't pass as real news.

Needs Pillow (pip install pillow). No network, no CDNs.
"""
import re
import zlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
SS = 2  # draw at 2x, then shrink, for smooth edges
RED = (209, 17, 28)
INK = (11, 11, 13)
WHITE = (255, 255, 255)

BOLD_FONTS = [
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf",
]


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


_font_cache = {}


def font(size):
    size = int(size)
    if size in _font_cache:
        return _font_cache[size]
    f = None
    for path in BOLD_FONTS:
        try:
            f = ImageFont.truetype(path, size)
            break
        except OSError:
            continue
    if f is None:
        f = ImageFont.load_default(size)
    _font_cache[size] = f
    return f


def _wrap(draw, text, fnt, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=fnt) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fit_headline(draw, text, width, height, start=74, smallest=40):
    """Biggest size where the headline fits the box (max 4 lines)."""
    size = start * SS
    while size >= smallest * SS:
        fnt = font(size)
        lines = _wrap(draw, text, fnt, width)
        lh = int(size * 1.12)
        if (len(lines) <= 4 and lh * len(lines) <= height
                and all(draw.textlength(l, font=fnt) <= width for l in lines)):
            return fnt, lines, lh
        size -= 2 * SS
    fnt = font(smallest * SS)
    lines = _wrap(draw, text, fnt, width)
    lh = int(smallest * SS * 1.12)
    max_lines = max(1, height // lh)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and draw.textlength(last + "\u2026", font=fnt) > width:
            last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
        lines[-1] = last + "\u2026"
    return fnt, lines, lh


def draw_card(out_path, headline, section, palette, seed, kicker=None, live=False):
    c1, c2, acc = (_hex(c) for c in palette)
    w, h = W * SS, H * SS
    # diagonal gradient
    small = Image.new("RGB", (2, 2))
    small.putpixel((0, 0), c1)
    small.putpixel((1, 1), c2)
    mid = tuple((a + b) // 2 for a, b in zip(c1, c2))
    small.putpixel((1, 0), mid)
    small.putpixel((0, 1), mid)
    img = small.resize((w, h), Image.BILINEAR).convert("RGBA")

    over = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    s = SS
    hsh = zlib.crc32(seed.encode())
    # light stripes
    d.polygon([(0, h), (470 * s, 0), (565 * s, 0), (95 * s, h)], fill=(255, 255, 255, 13))
    d.polygon([(170 * s, h), (640 * s, 0), (678 * s, 0), (208 * s, h)], fill=(255, 255, 255, 10))
    # rings (top right)
    cx, cy = (860 + hsh % 220) * s, (150 + (hsh >> 8) % 120) * s
    for i, r in enumerate((95, 175, 265, 365)):
        a = int(255 * (0.16 - i * 0.03))
        wd = (14 - i * 3) * s
        d.ellipse([cx - r * s, cy - r * s, cx + r * s, cy + r * s], outline=(255, 255, 255, a), width=wd)
    # equaliser bars (right, behind the text)
    for i in range(7):
        bh = ((hsh >> (i * 3)) % 140 + 30) * s
        x = (900 + i * 40) * s
        d.rectangle([x, 520 * s - bh, x + 24 * s, 520 * s], fill=acc + (70,))
    img = Image.alpha_composite(img, over)
    d = ImageDraw.Draw(img)

    # CN logo bug + wordmark
    bug_bg, bug_fg = (WHITE, RED) if section == "Breaking" else (RED, WHITE)
    d.rounded_rectangle([56 * s, 48 * s, 160 * s, 120 * s], radius=6 * s, fill=bug_bg)
    f = font(44 * s)
    d.text((108 * s, 85 * s), "CN", font=f, fill=bug_fg, anchor="mm")
    d.text((180 * s, 85 * s), "CHAOTIC NEWS", font=font(34 * s), fill=WHITE, anchor="lm")

    # SATIRE tag (top right) on the card itself
    tag_f = font(30 * s)
    tw = d.textlength("SATIRE", font=tag_f)
    x2 = (W - 56) * s
    x1 = x2 - tw - 44 * s
    d.rounded_rectangle([x1, 52 * s, x2, 116 * s], radius=6 * s, fill=(255, 214, 0), outline=INK, width=3 * s)
    d.text(((x1 + x2) / 2, 85 * s), "SATIRE", font=tag_f, fill=INK, anchor="mm")
    if live:
        lf = font(26 * s)
        lw = d.textlength("LIVE", font=lf)
        lx2 = x1 - 18 * s
        lx1 = lx2 - lw - 60 * s
        d.rounded_rectangle([lx1, 58 * s, lx2, 110 * s], radius=5 * s, fill=RED)
        d.ellipse([lx1 + 16 * s, 76 * s, lx1 + 32 * s, 92 * s], fill=WHITE)
        d.text((lx1 + 42 * s, 85 * s), "LIVE", font=lf, fill=WHITE, anchor="lm")

    # kicker + headline
    top = 160 * s
    if kicker:
        ks = 26
        while ks > 16 and d.textlength(kicker.upper(), font=font(ks * s)) > (W - 120) * s:
            ks -= 1
        d.text((60 * s, top), kicker.upper(), font=font(ks * s), fill=(235, 235, 235), anchor="la")
        top += 46 * s
    box_w, box_h = (W - 120) * s, 500 * s - top
    hf, lines, lh = _fit_headline(d, headline, box_w, box_h)
    y = top + max(0, (box_h - lh * len(lines)) // 2) if not kicker else top
    for line in lines:
        # soft shadow for contrast over the art
        d.text((60 * s + 3 * s, y + 3 * s), line, font=hf, fill=(0, 0, 0))
        d.text((60 * s, y), line, font=hf, fill=WHITE)
        y += lh

    # bottom bar: section block, network name, satire line
    d.rectangle([0, 530 * s, w, h], fill=INK)
    sec_f = font(34 * s)
    sec_txt = section.upper()
    sw = d.textlength(sec_txt, font=sec_f)
    d.rectangle([0, 530 * s, 60 * s + sw + 40 * s, h], fill=RED)
    d.text((48 * s, 580 * s), sec_txt, font=sec_f, fill=WHITE, anchor="lm")
    note_f = font(26 * s)
    note = "SATIRE \u00b7 EVERY STORY IS MADE UP"
    d.text(((W - 48) * s, 580 * s), note, font=note_f, fill=(255, 214, 0), anchor="rm")

    img = img.convert("RGB").resize((W, H), Image.LANCZOS)
    # 256-colour palette keeps files small (well under 300 KB)
    img = img.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".tmp.png")
    img.save(tmp, "PNG", optimize=True)
    if out_path.exists() and out_path.read_bytes() == tmp.read_bytes():
        tmp.unlink()  # unchanged: keep git clean
    else:
        tmp.replace(out_path)
    return out_path


def draw_icons(root):
    """CN favicon (ICO + 32px PNG) and 180px apple-touch-icon."""
    root = Path(root)
    big = Image.new("RGB", (720, 720), RED)
    d = ImageDraw.Draw(big)
    d.text((360, 372), "CN", font=font(380), fill=WHITE, anchor="mm")
    outs = {}
    touch = big.resize((180, 180), Image.LANCZOS)
    for name, im, kw in (("apple-touch-icon.png", touch, {}),
                          ("favicon-32.png", big.resize((32, 32), Image.LANCZOS), {})):
        p = root / name
        tmp = root / (name + ".tmp")
        im.save(tmp, "PNG", optimize=True)
        if p.exists() and p.read_bytes() == tmp.read_bytes():
            tmp.unlink()
        else:
            tmp.replace(p)
        outs[name] = p
    ico = root / "favicon.ico"
    tmp = root / "favicon.ico.tmp"
    big.save(tmp, "ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    if ico.exists() and ico.read_bytes() == tmp.read_bytes():
        tmp.unlink()
    else:
        tmp.replace(ico)
    return outs
