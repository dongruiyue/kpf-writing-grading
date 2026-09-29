#!/usr/bin/env python3
"""kpf-writing-grading 交付前校验。

用法：
  python3 scripts/validate-deliverables.py <学生版反馈.txt> [报告.html]

只报错误，没有输出即全部通过。退出码 0 = 通过，1 = 有错误。
校验项来自 2026-09-29 红队审查抓到的真实问题，改校验项前先读 SKILL.md 对应规则。
"""
import re
import sys
from pathlib import Path

FEEDBACK_SECTIONS = [
    "【作文反馈】",
    "【得分与评语】",
    "【写得好的地方】",
    "【需要修改的地方】",
    "【下一步练习】",
]

HTML_REQUIRED = [
    "作文批改档案",
    "01", "原题",
    "02", "作文原文",
    "03", "逐句批改",
    "04", "修改后范文",
    "05", "详细评价",
    "shot-btn",
    "html2canvas",
]

HTML_FORBIDDEN = [
    ("wxblock", "学生版反馈样式残留（第 6 步已禁止该段出现在报告中）"),
    ("copyhint", "学生版反馈样式残留（第 6 步已禁止该段出现在报告中）"),
    ("【作文反馈】", "报告中出现了学生版反馈文本（两个交付物必须分开）"),
    ("给学生", "受众标签已废弃"),
    ("给家长", "受众标签已废弃"),
    ("给老师", "受众标签已废弃"),
    ("教学安排", "教师工作语气（报告读者是家长和学生，见第 6 步语气红线）"),
    ("备课", "教师工作语气（报告读者是家长和学生）"),
    ("教研", "教师工作语气（报告读者是家长和学生）"),
    ("听写清单", "教师工作语气（报告读者是家长和学生）"),
    ("课上统一", "教师工作语气（报告读者是家长和学生）"),
    ("全班过关", "教师工作语气（报告读者是家长和学生）"),
    ("观察点", "教师工作语气（报告读者是家长和学生）"),
]

# 模板作文内容指纹：用户自己的学生作文里几乎不可能逐字出现这些片段；
# 出现即说明照抄模板正文漏改。注意不放学生姓名（同名学生合法），只放作文原文片段。
# 若更换模板中的示例作文，同步更新这里的指纹。
STALE_MARKERS = ["play together happy",
                 "since you can have fun and won't feel lonely",
                 "Last week I forgot my homework and my best friend lent me his notebook"]


def check_feedback(text):
    errs = []
    positions = []
    for sec in FEEDBACK_SECTIONS:
        pos = text.find(sec)
        if pos < 0:
            errs.append(f"缺少分区 {sec}")
        positions.append(pos)
    if all(p >= 0 for p in positions) and positions != sorted(positions):
        errs.append("五个分区顺序错误")

    if "——" in text or "—" in text:
        errs.append("出现破折号（—— 或 —），学生版红线")
    if re.search(r"不是.{1,15}而是", text):
        errs.append("出现「不是…而是…」句式")
    if re.search(r"不仅仅.{1,15}更", text):
        errs.append("出现「不仅仅…更…」句式")

    stars = re.findall(r"重要性：🌟+", text)
    if len(stars) != 3:
        errs.append(f"重要性星级应为 3 条，实际 {len(stars)} 条")
    else:
        if not (len(stars[0].split("🌟")) - 1 > len(stars[1].split("🌟")) - 1 > len(stars[2].split("🌟")) - 1):
            errs.append("星级未按重要性递减（应 3 星 > 2 星 > 1 星）")

    score = re.search(r"【得分与评语】\s*\n?([^\n]*\d+\s*/\s*\d+[^\n]*)", text)
    if not score:
        errs.append("分数行缺少 x/满分 格式")
    else:
        line = score.group(1)
        if not re.search(r"C\s*\d", line):
            errs.append("分数行缺少分项小分（C x · CA x · O x · L x）")

    if re.search(r"约\s*\d+\s*词", text):
        errs.append("出现「约 N 词」——词数必须实际计数，不许估算（红队问题 #3）")
    return errs


def check_html(text):
    errs = []
    for token in HTML_REQUIRED:
        if token not in text:
            errs.append(f"报告缺少必要元素：{token}")
    for bad, why in HTML_FORBIDDEN:
        if bad in text:
            errs.append(f"报告出现禁用内容「{bad}」：{why}")
    for pat, label in [("{{", "花括号占位符"), ("[必填]", "必填占位符")]:
        if pat in text:
            errs.append(f"报告有未替换的{label}：{pat}")
    return errs


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    all_errs = []
    for a in args:
        p = Path(a)
        if not p.exists():
            all_errs.append(f"文件不存在：{a}")
            continue
        text = p.read_text(encoding="utf-8")
        if p.suffix.lower() in (".html", ".htm"):
            errs = check_html(text)
            # 模板指纹：只有「不是示例学生的报告里出现示例作文原文」才是照抄漏改；
            # 示例学生本人的档案含这些片段属正常，跳过
            if "李小雨" not in text:
                for stale in STALE_MARKERS:
                    if stale in text:
                        errs.append(f"报告残留样板数据「{stale}」——照抄模板后漏改，必须替换为本次内容")
        else:
            errs = check_feedback(text)
        for e in errs:
            all_errs.append(f"[{p.name}] {e}")
    if all_errs:
        print("未通过：")
        for e in all_errs:
            print(f"  - {e}")
        sys.exit(1)
    print("全部通过")


if __name__ == "__main__":
    main()
