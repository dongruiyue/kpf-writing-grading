#!/usr/bin/env python3
"""把学生版文字反馈渲染成一张竖版图片（1080 宽，高度按内容算）。

用法:
    python3 render-feedback-card.py <反馈.txt> <输出.png>

输入就是经校验器通过的学生版反馈纯文本（五个【】分区）：
    【作文反馈】/【得分与评语】/【写得好的地方】/【需要修改的地方】/【下一步练习】
"""
import math
import re
import sys

from PIL import Image, ImageDraw, ImageFont

W_LOGICAL = 1080
SS = 2
M = 84
CONTENT_W = W_LOGICAL - M * 2

PAPER = (250, 249, 246)
INK = (30, 35, 40)
MUTED = (110, 106, 99)
ACCENT = (42, 90, 79)
RULE = (227, 224, 216)
TINT = (242, 239, 232)

FONT_PATHS = [
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0),
    ("/System/Library/Fonts/STHeiti Light.ttc", 0),
    ("/System/Library/Fonts/Supplemental/Songti.ttc", 0),
]
BOLD_PATHS = [
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", 1),
    ("/System/Library/Fonts/STHeiti Medium.ttc", 0),
    ("/System/Library/Fonts/Supplemental/Songti.ttc", 1),
]

_fcache = {}


def font(size, bold=False):
    key = (bold, size)
    if key in _fcache:
        return _fcache[key]
    for path, index in (BOLD_PATHS if bold else FONT_PATHS):
        try:
            f = ImageFont.truetype(path, size * SS, index=index)
            _fcache[key] = f
            return f
        except Exception:
            continue
    raise SystemExit("找不到可用的中文字体")


def wrap(text, f, maxw):
    lines = []
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        cur = ""
        for ch in para:
            if f.getlength(cur + ch) <= maxw or not cur:
                cur += ch
            else:
                cut = cur.rfind(" ")
                if 0 < cut and len(cur) - cut < 14:
                    lines.append(cur[:cut])
                    cur = cur[cut + 1:] + ch
                else:
                    lines.append(cur)
                    cur = ch.lstrip()
        if cur:
            lines.append(cur)
    return lines


def parse(path):
    raw = open(path, encoding="utf-8").read()
    d = {"name": "", "title": "", "date": "", "score": "", "parts": "", "band": "",
         "comment": [], "goods": [], "fixes": [], "next": []}
    section = ""
    buf = []
    score_seen = False

    def flush():
        nonlocal buf, score_seen
        text = " ".join(buf).strip()
        buf = []
        if not text:
            return
        if section == "得分与评语":
            if not score_seen:
                m = re.match(r"^(\S+?)（(.+)）", text)
                if m:
                    d["score"] = m.group(1)
                    inside = m.group(2)
                    rest = text[m.end():].strip()
                    if "，" in inside:
                        parts, band = inside.split("，", 1)
                        d["parts"], d["band"] = parts.strip(), band.strip()
                    else:
                        d["parts"] = inside.strip()
                    score_seen = True
                    if rest:
                        d["comment"].append(rest)
                return
            d["comment"].append(text)
        elif section == "写得好的地方":
            d["goods"].append(re.sub(r"^\d+[.、]\s*", "", text))
        elif section == "需要修改的地方":
            d["fixes"].append(re.sub(r"^\d+[.、]\s*", "", text))
        elif section == "下一步练习":
            d["next"].append(text)

    for line in raw.split("\n"):
        line = line.strip()
        if line.startswith("【") and line.endswith("】"):
            flush()
            section = line[1:-1]
            if section == "作文反馈":
                section = "标题"
            continue
        if section == "标题":
            if not d["name"] and line:
                m = re.search(r"\d+月\d+日$", line)
                if m:
                    d["date"] = m.group(0)
                    line = line[:m.start()].strip()
                name, _, title = line.partition(" ")
                d["name"], d["title"] = name.strip(), title.strip()
            continue
        if not line:
            flush()
            continue
        # 编号条目各自成条
        if section in ("写得好的地方", "需要修改的地方") and re.match(r"^\d+[.、]", line):
            flush()
        buf.append(line)
    flush()
    return d


def split_importance(s):
    for key in ("重要性：", "重要性:"):
        if key in s:
            body, stars = s.split(key, 1)
            n = stars.count("🌟") or stars.count("★")
            return body.strip(), n
    return s, 0


def star(draw, cx, cy, r, color):
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    draw.polygon(pts, fill=color)


def build(d):
    img = Image.new("RGB", (W_LOGICAL * SS, 4000 * SS), PAPER)
    draw = ImageDraw.Draw(img)
    y = [96 * SS]

    def put(text, size, color, bold=False, indent=0, leading=1.55, tracking=0):
        f = font(size, bold)
        if tracking:
            text = " ".join(list(text))
        lines = wrap(text, f, (CONTENT_W - indent) * SS)
        lh = int(size * SS * leading)
        for ln in lines:
            draw.text((M * SS + indent * SS, y[0]), ln, font=f, fill=color)
            y[0] += lh
        return f

    put("作文反馈", 24, MUTED, tracking=1, leading=1.2)
    y[0] += 34 * SS
    put(d["name"], 76, INK, bold=True, leading=1.05)
    y[0] += 12 * SS
    if d["title"]:
        put(d["title"], 30, MUTED, leading=1.4)
        y[0] += 6 * SS
    put(d["date"], 26, MUTED, leading=1.3)
    y[0] += 46 * SS

    if d["score"]:
        fscore = font(88, bold=True)
        draw.text((M * SS, y[0]), d["score"], font=fscore, fill=ACCENT)
        y[0] += int(88 * SS * 1.05)
        y[0] += 12 * SS
    if d["parts"]:
        put(d["parts"], 30, INK, leading=1.3)
        y[0] += 8 * SS
    if d["band"]:
        band_color = ACCENT if "判为不过" in d["band"] or "未稳过" in d["band"] else MUTED
        put(d["band"], 28, band_color, leading=1.3)
    y[0] += 52 * SS

    draw.line([(M * SS, y[0]), ((W_LOGICAL - M) * SS, y[0])], fill=RULE, width=SS)
    y[0] += 42 * SS

    if d["comment"]:
        put("\n".join(d["comment"]), 31, INK, leading=1.62)
    y[0] += 50 * SS

    put("写得好的地方", 24, MUTED, tracking=1, leading=1.2)
    y[0] += 24 * SS
    for i, g in enumerate(d["goods"], 1):
        draw.text((M * SS, y[0] + 6 * SS), str(i), font=font(21, bold=True), fill=ACCENT)
        put(g, 30, INK, indent=44, leading=1.55)
        y[0] += 18 * SS
    y[0] += 34 * SS

    put("需要修改的地方", 24, MUTED, tracking=1, leading=1.2)
    y[0] += 24 * SS
    for item in d["fixes"]:
        body, stars = split_importance(item)
        put(body, 30, INK, indent=20, leading=1.55)
        if stars:
            y[0] += 12 * SS
            for k in range(stars):
                star(draw, (M + 32 + k * 34) * SS, y[0] + 11 * SS, 11 * SS, ACCENT)
            y[0] += 34 * SS
        y[0] += 24 * SS
    y[0] += 24 * SS

    put("下一步练习", 24, MUTED, tracking=1, leading=1.2)
    y[0] += 22 * SS
    fnext = font(29)
    lines = wrap(" ".join(d["next"]), fnext, (CONTENT_W - 64) * SS)
    lh = int(29 * SS * 1.55)
    box_h = lh * len(lines) + 44 * SS
    draw.rounded_rectangle([M * SS, y[0] - 14 * SS, (W_LOGICAL - M) * SS, y[0] - 14 * SS + box_h],
                           radius=16 * SS, fill=TINT)
    ty = y[0] + 8 * SS
    for ln in lines:
        draw.text(((M + 32) * SS, ty), ln, font=fnext, fill=INK)
        ty += lh
    y[0] = y[0] - 14 * SS + box_h + 60 * SS

    h = max(int(y[0]), 640 * SS)
    out = img.crop((0, 0, W_LOGICAL * SS, h)).resize((W_LOGICAL, h // SS), Image.LANCZOS)
    return out


def main():
    if len(sys.argv) < 3:
        raise SystemExit("用法: python3 render-feedback-card.py <反馈.txt> <输出.png>")
    d = parse(sys.argv[1])
    if not d["name"]:
        raise SystemExit("没读到学生姓名，检查反馈文本第二行")
    img = build(d)
    img.save(sys.argv[2])
    print(f"已生成 {sys.argv[2]}  {img.width}x{img.height}")


if __name__ == "__main__":
    main()
