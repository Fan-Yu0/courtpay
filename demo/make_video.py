"""Render the 45s demo video from the real run transcript."""

from __future__ import annotations

import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1920, 1080, 30
DURATION = 45.0

BG_TOP = (7, 11, 16)
BG_BOTTOM = (14, 22, 34)
TEXT = (232, 238, 247)
MUTED = (143, 163, 191)
BLUE = (76, 141, 255)
PURPLE = (139, 92, 246)
RED = (228, 72, 60)
GREEN = (52, 211, 153)
AMBER = (251, 191, 36)

FONT_DIR = "C:/Windows/Fonts"


def font(name, size):
    for candidate in (name, "segoeui.ttf"):
        path = os.path.join(FONT_DIR, candidate)
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def bold(size):
    return font("segoeuib.ttf", size)


def regular(size):
    return font("segoeui.ttf", size)


def mono(size):
    return font("consola.ttf", size)


def gradient():
    base = Image.new("RGB", (W, H), BG_TOP)
    draw = ImageDraw.Draw(base)
    for y in range(H):
        t = y / H
        draw.line(
            [(0, y), (W, y)],
            fill=(
                int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t),
                int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t),
                int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t),
            ),
        )
    return base


BACKDROP = gradient()


def glow(img, center, radius, color, alpha=70):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for i in range(radius, 0, -8):
        a = int(alpha * (1 - i / radius) ** 2)
        draw.ellipse(
            [center[0] - i, center[1] - i, center[0] + i, center[1] + i],
            fill=(color[0], color[1], color[2], a),
        )
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def tint(color, alpha, bg=(12, 17, 24)):
    return (
        int(bg[0] + (color[0] - bg[0]) * alpha),
        int(bg[1] + (color[1] - bg[1]) * alpha),
        int(bg[2] + (color[2] - bg[2]) * alpha),
    )


def ease(t):
    return t * t * (3 - 2 * t)


def scene_title(p):
    img = BACKDROP.copy()
    img = glow(img, (330, 250), 700, PURPLE, 55)
    img = glow(img, (1580, 820), 700, BLUE, 45)
    d = ImageDraw.Draw(img)
    alpha = int(255 * min(1.0, p * 3))
    shift = int(24 * (1 - ease(min(1.0, p * 2))))
    d.text((180, 330 + shift), "CourtPay", font=bold(150), fill=TEXT + (alpha,))
    d.text(
        (186, 520 + shift),
        "x402 purchases that can be appealed",
        font=regular(52),
        fill=MUTED,
    )
    d.line([(186, 620), (186 + int(520 * ease(min(1.0, p * 1.6))), 620)], fill=BLUE, width=4)
    if p > 0.35:
        a = min(1.0, (p - 0.35) * 3)
        logo_row(d, 186, 720, a)
    return img


def logo_row(d, x, y, alpha=1.0):
    a = int(255 * alpha)

    def chip(cx, color, glyph, label, glyph_font, label_font):
        box = [cx, y, cx + 480, y + 104]
        d.rounded_rectangle(box, radius=18, outline=tint(color, 0.55), width=2, fill=tint(color, 0.12))
        d.rounded_rectangle([cx + 18, y + 22, cx + 78, y + 82], radius=14, fill=color + (a,))
        tw = d.textlength(glyph, font=glyph_font)
        d.text((cx + 48 - tw / 2, y + 52 - 22), glyph, font=glyph_font, fill=(255, 255, 255, a))
        d.text((cx + 98, y + 36), label, font=label_font, fill=TEXT + (a,))

    chip(x, RED, "IC", "Internet Court", bold(30), bold(38))
    chip(x + 520, PURPLE, "GL", "GenLayer", bold(30), bold(38))
    chip(x + 1040, BLUE, "402", "x402", bold(22), bold(38))


def scene_gap(p):
    img = BACKDROP.copy()
    d = ImageDraw.Draw(img)
    d.text((180, 180), "The problem", font=bold(34), fill=MUTED)
    d.text((180, 236), "Payment settles before the buyer reads the artifact.", font=bold(66), fill=TEXT)
    steps = [
        ("buyer pays", BLUE),
        ("200 OK", GREEN),
        ("artifact shipped", TEXT),
        ("???", RED),
    ]
    y = 470
    for i, (label, color) in enumerate(steps):
        local = max(0.0, min(1.0, (p - i * 0.12) * 4))
        if local <= 0:
            continue
        x = 180 + i * 430
        box = [x, y, x + 360, y + 200]
        d.rounded_rectangle(box, radius=20, fill=tint(color, 0.10), outline=tint(color, 0.5), width=3)
        d.text((x + 28, y + 80), label, font=bold(36), fill=color)
        if i < 3:
            d.line([(x + 366, y + 100), (x + 424, y + 100)], fill=MUTED + (160,), width=3)
    if p > 0.55:
        d.text(
            (180, 760),
            "A dispute today is a support ticket, not a verdict.",
            font=regular(44),
            fill=MUTED,
        )
    return img


def scene_bridge(p):
    img = BACKDROP.copy()
    img = glow(img, (960, 540), 620, PURPLE, 60)
    d = ImageDraw.Draw(img)
    d.text((180, 420), "So we made the receipt a case.", font=bold(84), fill=TEXT)
    d.text((186, 540), "Signed receipt   ·   public delivery   ·   reasoned verdict", font=regular(44), fill=MUTED)
    return img


LINES = [
    ("seller", "Base Sepolia RPC latency feed · 0.25 USDC · 0x07400490E8…c26ef2BF67", AMBER),
    ("buyer", "GET /dataset/latency-feed → 402 Payment Required", BLUE),
    ("buyer", "sign EIP-3009 authorization → 200 OK · receipt dd6af1213b…6367af0f", BLUE),
    ("buyer", "settled by local-ledger · ref local:0x04…3174513d", BLUE),
    ("buyer", "preflight: 3 rows · missing p99_ms, probe_checksum", BLUE),
    ("court", "deploy CourtPayCourt → Studio Network", PURPLE),
    ("court", "contract 0x533f3b4b9D6BE050fD64fa23e577Ab5918E46b10", PURPLE),
    ("court", "case-1 opened from receipt hash · dispute filed", PURPLE),
    ("jury", "validators fetch the delivery and re-run the review", PURPLE),
    ("jury", "REFUND · confidence high · 35s", GREEN),
    ("result", "refund 250000 of 250000 units · case-1", GREEN),
]


def scene_terminal(p):
    img = BACKDROP.copy()
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([120, 120, 1800, 960], radius=22, fill=(10, 14, 20), outline=(42, 56, 78), width=2)
    d.rounded_rectangle([120, 120, 1800, 182], radius=22, fill=(18, 24, 34))
    for i, color in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([152 + i * 34, 143, 172 + i * 34, 163], fill=color)
    d.text((330, 138), "courtpay demo \u2014 studio network", font=regular(28), fill=MUTED)

    visible = p * (len(LINES) + 2.2)
    y = 236
    for i, (tag, text, color) in enumerate(LINES):
        local = min(1.0, max(0.0, visible - i))
        if local <= 0:
            break
        alpha = int(255 * min(1.0, local * 2))
        dx = int(18 * (1 - ease(local)))
        pill = [176 + dx, y - 6, 176 + dx + 132, y + 38]
        d.rounded_rectangle(pill, radius=10, fill=tint(color, 0.28))
        label = tag
        tw = d.textlength(label, font=mono(22))
        d.text((pill[0] + (132 - tw) / 2, y + 2), label, font=mono(22), fill=tint(color, 1.0))
        d.text((330 + dx, y + 1), text, font=mono(30), fill=TEXT + (alpha,))
        y += 62
    return img


def wrap(d, text, fnt, width):
    words = text.split()
    lines, current = [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if d.textlength(candidate, font=fnt) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def scene_verdict(p):
    img = BACKDROP.copy()
    img = glow(img, (960, 300), 700, GREEN, 45)
    d = ImageDraw.Draw(img)
    d.text((180, 170), "the verdict, on-chain", font=bold(34), fill=MUTED)
    d.text((180, 226), "VIOLATED", font=bold(120), fill=GREEN)
    d.text((180 + d.textlength("VIOLATED", font=bold(120)) + 30, 300), "high confidence", font=regular(42), fill=MUTED)

    reasoning = (
        "The delivery only contains 3 rows instead of the promised 10, and it is "
        "missing the required p99 latency and probe checksum fields for each row."
    )
    lines = wrap(d, reasoning, regular(40), 1420)
    y = 430
    for line in lines:
        d.text((184, y), line, font=regular(40), fill=TEXT)
        y += 56

    bar_y = y + 40
    d.rounded_rectangle([180, bar_y, 1740, bar_y + 140], radius=18, fill=(20, 28, 40), outline=tint(GREEN, 0.45), width=2)
    d.text((212, bar_y + 36), "refund", font=regular(34), fill=MUTED)
    d.text((212, bar_y + 72), "0.25 of 0.25 USDC", font=bold(46), fill=TEXT)
    d.text((900, bar_y + 36), "case", font=regular(34), fill=MUTED)
    d.text((900, bar_y + 72), "case-1  ·  0x533f3b4b…46b10", font=bold(40), fill=TEXT)
    return img


def scene_close(p):
    img = BACKDROP.copy()
    img = glow(img, (960, 520), 760, BLUE, 45)
    d = ImageDraw.Draw(img)
    d.text((180, 300), "CourtPay", font=bold(96), fill=TEXT)
    d.text((186, 430), "github.com/Fan-Yu0/courtpay", font=regular(48), fill=MUTED)
    d.text((186, 500), "21 tests  ·  live case on GenLayer Studio  ·  MIT", font=regular(34), fill=MUTED)
    logo_row(d, 186, 640, 1.0)
    d.text((186, 820), "Also runs as an agent skill: SKILL.md", font=regular(30), fill=MUTED)
    return img


SCENES = [
    (0.0, 4.6, scene_title),
    (4.6, 10.0, scene_gap),
    (10.0, 12.0, scene_bridge),
    (12.0, 31.5, scene_terminal),
    (31.5, 38.5, scene_verdict),
    (38.5, 45.0, scene_close),
]


def render_frame(t):
    for index, (start, end, fn) in enumerate(SCENES):
        if start <= t < end or (index == len(SCENES) - 1 and t >= start):
            p = (t - start) / (end - start)
            img = fn(p)
            fade = 0.5 / FPS * 1.4
            if index > 0 and t - start < fade:
                prev = SCENES[index - 1][2](1.0)
                blend = (t - start) / fade
                img = Image.blend(prev, img, min(1.0, blend))
            return img
    return BACKDROP.copy()


def main(output="demo/courtpay-demo.mp4"):
    frames_dir = "demo/frames"
    os.makedirs(frames_dir, exist_ok=True)
    total = int(DURATION * FPS)
    for i in range(total):
        frame = render_frame(i / FPS)
        frame.save(os.path.join(frames_dir, "f%05d.png" % i))
        if i % 90 == 0:
            print("frame", i, "/", total, flush=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-framerate", str(FPS), "-i", os.path.join(frames_dir, "f%05d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium",
            "-movflags", "+faststart", output,
        ],
        check=True,
    )
    print("wrote", output)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "demo/courtpay-demo.mp4")
