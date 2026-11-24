"""生成 assets/demo.gif：960×600 的终端风演示动图。

只用 Pillow（开发期依赖，不进 requirements）。跑法：
    python scripts/make_demo_gif.py

注意：微软雅黑里没有 ✓ 这种字形，画上去是个方框，
所以输出行一律用「·」起头，别再用打勾。
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

W, H = 960, 600
BG = "#0b0f14"
BAR = "#161b22"
LINE = "#21262d"
GREEN = "#7ee787"
TEXT = "#c9d1d9"
DIM = "#8b949e"
BLUE = "#79c0ff"
YELLOW = "#e3b341"
RED = "#ff7b72"

FONT_PATH = r"C:\Windows\Fonts\msyh.ttc"

LINE_H = 26
MAX_W = W - 56

COLORS = {
    "cmd": GREEN,
    "out": TEXT,
    "dim": DIM,
    "cite": BLUE,
    "warn": YELLOW,
    "bad": RED,
}


def font(size: int):
    return ImageFont.truetype(FONT_PATH, size)


_MEASURE = ImageDraw.Draw(Image.new("RGB", (1, 1)))


def clip(text: str, size: int = 17) -> str:
    """超宽的行截断加省略号，免得文字跑到屏幕外面去。"""
    f = font(size)
    if _MEASURE.textlength(text, font=f) <= MAX_W:
        return text
    while text and _MEASURE.textlength(text + "…", font=f) > MAX_W:
        text = text[:-1]
    return text + "…"


def render(rows, cursor_row=None):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    d.rectangle([0, 0, W, 36], fill=BAR)
    for i, color in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]):
        d.ellipse([16 + i * 22, 12, 28 + i * 22, 24], fill=color)
    d.text((92, 9), "yingda — 工单分诊、起草与转人工", font=font(15), fill=DIM)
    d.line([0, 36, W, 36], fill=LINE)

    y = 56
    for idx, (style, text) in enumerate(rows):
        shown = clip(text)
        d.text((28, y), shown, font=font(17), fill=COLORS[style])
        if cursor_row == idx:
            w = _MEASURE.textlength(shown, font=font(17))
            d.rectangle([28 + w + 4, y + 2, 28 + w + 13, y + 20], fill=GREEN)
        y += LINE_H
        if y > H - 18:
            break
    return img


# 每行：(样式, 文本)。cmd 行逐字打出来，其余逐行出现。
SCRIPT = [
    ("cmd", "> python -m yingda kb add samples/kb-退款政策.md samples/kb-物流发票账号.md"),
    ("out", "· 退款与售后政策 10 段、物流发票账号 9 段，入库"),
    ("dim", "  知识库：19 段 / 2 个来源"),
    ("dim", ""),
    ("cmd", '> python -m yingda intake --file samples/ticket-1-退款.txt --subject "想退年费会员"'),
    ("out", "· 工单 [1] 已入队：想退掉 11 月买的年费会员"),
    ("dim", ""),
    ("cmd", "> python -m yingda process --id 1"),
    ("out", "=== 工单 [1] → drafted ==="),
    ("out", "分诊：退款退货 / P1 / 情绪 neutral"),
    ("out", "命中 4 段：[1] 7 天内且用量≤1GB 可全额退，3—5 个工作日到账"),
    ("dim", "          [2] 已开发票的，需先退回发票或提供红冲材料 …"),
    ("out", "草稿：7 天内、已用容量不超过 1GB 可以全额退，原路退回 3—5 天。"),
    ("out", "      是否还在 7 天内，我核实下单时间后回复你。"),
    ("cite", "判断：可直接回 —— 草稿三项都能在知识库找到依据，没编政策。"),
    ("dim", ""),
    ("cmd", "> python -m yingda process --id 3"),
    ("bad", "=== 工单 [3] → escalated ==="),
    ("bad", "判断：转人工（主管）—— 账号被盗、境外登录、威胁曝光，接不住。"),
]
TAIL = [
    ("dim", ""),
    ("warn", "4 张工单：3 张能直发，1 张必须人接。每条判断都写着依据。"),
]


def build():
    frames = []
    shown = []

    for style, text in SCRIPT:
        if style == "cmd":
            # 一次打六个字符：纯逐字打帧太多，GIF 会重到 800KB
            for i in range(6, len(text) + 1, 6):
                frames.append(render(shown + [("cmd", text[:i])], cursor_row=len(shown)))
        shown = shown + [(style, text)]
        frames.append(render(shown))

    for _ in range(10):
        frames.append(render(shown + TAIL))

    frames = [f.quantize(colors=20, method=Image.MEDIANCUT) for f in frames]
    out = os.path.join("assets", "demo.gif")
    os.makedirs("assets", exist_ok=True)
    frames[0].save(
        out,
        save_all=True,
        append_images=frames[1:],
        duration=150,
        loop=0,
        optimize=True,
    )
    print(f"ok -> {out}  {len(frames)} 帧  {os.path.getsize(out) / 1024:.1f} KB")


if __name__ == "__main__":
    build()
