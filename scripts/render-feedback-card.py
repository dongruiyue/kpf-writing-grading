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

W_LOGICAL = 900
SS = 2
M = 56
CONTENT_W = W_LOGICAL - M * 2

PAPER = (252, 251, 248)
INK = (28, 32, 36)
MUTED = (108, 104, 97)
ACCENT = (36, 82, 72)
RULE = (223, 220, 212)

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
    img = Image.new("RGB", (W_LOGICAL * SS, 3600 * SS), PAPER)
    draw = ImageDraw.Draw(img)
    y = [60 * SS]

    def text(s, size, color, bold=False, indent=0, leading=1.5):
        f = font(size, bold)
        lines = wrap(s, f, (CONTENT_W - indent) * SS)
        lh = int(size * SS * leading)
        for ln in lines:
            draw.text(((M + indent) * SS, y[0]), ln, font=f, fill=color)
            y[0] += lh
        return len(lines)

    # 顶部
    text("作文反馈", 19, MUTED, bold=True, leading=1.2)
    y[0] += 16 * SS

    fname, fdate = font(34, True), font(19)
    draw.text((M * SS, y[0]), d["name"], font=fname, fill=INK)
    if d["date"]:
        draw.text(((W_LOGICAL - M) * SS - fdate.getlength(d["date"]), y[0] + 14 * SS),
                  d["date"], font=fdate, fill=MUTED)
    y[0] += int(34 * SS * 1.35)
    if d["title"]:
        text(d["title"], 21, MUTED, leading=1.35)
    y[0] += 12 * SS

    # 分数行
    fbig, fpart = font(46, True), font(20)
    draw.text((M * SS, y[0]), d["score"], font=fbig, fill=ACCENT)
    score_w = fbig.getlength(d["score"])
    if d["parts"]:
        draw.text((M * SS + score_w + 16 * SS, y[0] + 18 * SS), d["parts"], font=fpart, fill=INK)
    y[0] += int(46 * SS * 1.18)
    if d["band"]:
        color = ACCENT if ("判为不过" in d["band"] or "未稳过" in d["band"]) else MUTED
        text(d["band"], 19, color, leading=1.35)
    y[0] += 20 * SS

    draw.line([(M * SS, y[0]), ((W_LOGICAL - M) * SS, y[0])], fill=RULE, width=SS)
    y[0] += 22 * SS

    # 评语
    if d["comment"]:
        text("\n".join(d["comment"]), 25, INK, leading=1.62)
    y[0] += 22 * SS

    # 写得好的地方
    text("写得好的地方", 20, INK, bold=True, leading=1.2)
    y[0] += 6 * SS
    for i, g in enumerate(d["goods"], 1):
        draw.text((M * SS, y[0] + 2 * SS), f"{i}", font=font(19, True), fill=ACCENT)
        text(g, 25, INK, indent=26, leading=1.55)
        y[0] += 8 * SS
    y[0] += 18 * SS

    # 需要修改的地方
    text("需要修改的地方", 20, INK, bold=True, leading=1.2)
    y[0] += 6 * SS
    for item in d["fixes"]:
        body, stars = split_importance(item)
        if stars:
            for k in range(stars):
                cx, cy = (M + 7 + k * 13) * SS, y[0] + 12 * SS
                draw.ellipse([cx - 3.4 * SS, cy - 3.4 * SS, cx + 3.4 * SS, cy + 3.4 * SS], fill=ACCENT)
        text(body, 25, INK, indent=46, leading=1.55)
        y[0] += 9 * SS
    y[0] += 14 * SS

    # 下一步练习
    draw.line([(M * SS, y[0]), ((W_LOGICAL - M) * SS, y[0])], fill=RULE, width=SS)
    y[0] += 18 * SS
    text("下一步练习", 20, INK, bold=True, leading=1.2)
    y[0] += 6 * SS
    text(" ".join(d["next"]), 25, INK, leading=1.6)
    y[0] += 44 * SS

    h = max(int(y[0]), 520 * SS)
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
