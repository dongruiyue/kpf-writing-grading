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


def _band_ranges(is_ket):
    if is_ket:
        return {"A": (13, 15), "B": (11, 12), "C": (8, 10), "edge": (6, 7), "fail": (0, 5)}
    return {"A": (17, 20), "B": (14, 16), "C": (11, 13), "edge": (8, 10), "fail": (0, 7)}


def _check_score_parts(total, max_score, pairs, band_text, is_ket, errs):
    """反馈文本和 HTML 报告共用的分数校验。pairs = [(维度名, 数值), ...]"""
    expected_names = ["C", "O", "L"] if is_ket else ["C", "CA", "O", "L"]
    expected_max = 15 if is_ket else 20

    if total < 0 or max_score < 0:
        errs.append(f"分数出现负数：{total}/{max_score}")
        return
    if max_score != expected_max:
        errs.append(f"满分应为 {expected_max}，实际 /{max_score}")

    names = [n for n, _ in pairs]
    subs = [int(v) for _, v in pairs]
    if not pairs:
        errs.append("分数行缺少分项小分（C x · CA x · O x · L x）")
    else:
        if sorted(names) != sorted(expected_names):
            missing = [n for n in expected_names if n not in names]
            dup = [n for n in set(names) if names.count(n) > 1]
            extra = [n for n in names if n not in expected_names]
            if missing:
                errs.append(f"缺少维度小分：{missing}（应为 {expected_names}）")
            if dup:
                errs.append(f"维度小分重复：{dup}（应为 {expected_names}）")
            if extra:
                errs.append(f"多出维度小分：{extra}（应为 {expected_names}）")
        elif names != expected_names:
            errs.append(f"小分顺序错误：{names}（应为 {expected_names}）")
        if len(pairs) == len(expected_names):
            for n, v in pairs:
                if not 0 <= int(v) <= 5:
                    errs.append(f"{n} 小分 {v} 超出 0–5 范围")
            if sum(subs) != total:
                errs.append(f"总分 {total} ≠ 小分之和 {sum(subs)}（{pairs}）")

    # 档位一致性：分数与档位必须落在 rubrics 定性档位表的对应区间
    r = _band_ranges(is_ket)
    if "未过字数线" in band_text or "判为不过" in band_text:
        if re.search(r"Grade\s*[ABC]", band_text):
            errs.append("未过字数线不应标 Grade 档位（规则：判为不过时不写档位）")
        return
    if "未达到本级要求" in band_text:
        lo, hi = r["fail"]
        if not lo <= total <= hi:
            errs.append(f"分数 {total} 与档位「未达到本级要求」不一致（该档范围 {lo}–{hi}）")
        return
    m = re.search(r"Grade\s*([ABC])", band_text)
    if not m:
        errs.append("分数行缺少档位说明（Grade X / Grade X 边缘，未稳过 / 未达到本级要求 / 未过字数线判为不过）")
        return
    g = m.group(1)
    if "边缘" in band_text or "未稳过" in band_text:
        lo, hi = r["edge"]
        label = f"Grade {g} 边缘档"
    else:
        lo, hi = r[g]
        label = f"Grade {g}"
    if not lo <= total <= hi:
        errs.append(f"分数 {total} 与档位「{label}」不一致（该档范围 {lo}–{hi}，见 rubrics 定性档位表）")


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
        total_m = re.search(r"(-?\d+)\s*/\s*(-?\d+)", line)
        if not total_m:
            errs.append("分数行缺少 x/满分 格式")
        else:
            # 发现小数单独报错，不静默截断
            if re.search(r"[CLO]A?\s*\d+\.\d+", line):
                errs.append("分数行出现小数小分——评分规则只接受整数（教研口径：写作评分无 0.5）")
            is_ket = "KET" in text[:300]
            pairs = re.findall(r"\b(C|CA|O|L)\s*(\d+)\b", line)
            _check_score_parts(int(total_m.group(1)), int(total_m.group(2)), pairs, line, is_ket, errs)

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

    # 分数区校验：抬头里的总分 / 小分 / 档位与文本反馈走同一套规则
    num_m = re.search(r'<div class="num">(-?\d+)<small>\s*/\s*(-?\d+)</small></div>', text)
    subs_m = re.search(r'<div class="subs">([^<]+)</div>', text)
    band_m = re.search(r'<div class="band(?:\s+fail)?">([^<]+)</div>', text)
    if not num_m:
        errs.append("报告抬头缺少总分（.scorebox .num）")
    if not subs_m:
        errs.append("报告抬头缺少分项小分（.scorebox .subs）")
    if not band_m:
        errs.append("报告抬头缺少档位说明（.scorebox .band）")
    if num_m and subs_m:
        is_ket = "KET" in text[:2000]
        pairs = re.findall(r"\b(C|CA|O|L)\s*(\d+)\b", subs_m.group(1))
        _check_score_parts(int(num_m.group(1)), int(num_m.group(2)), pairs,
                           band_m.group(1) if band_m else "", is_ket, errs)
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


# ── 自检：已知反例回归（GPT6-astra 两轮审查实测构造）───────────

_FEEDBACK_BASE = """【作文反馈】
测试生 PET article 3月15日

【得分与评语】
{score_line}
评语。

【写得好的地方】
1. a
2. b

【需要修改的地方】
1. x。重要性：🌟🌟🌟
2. y。重要性：🌟🌟
3. z。重要性：🌟

【下一步练习】
练习内容"""

_SELFTEST = [
    # (名称, 分数行, 是否应拦下)
    ("astra 反例 99/20 超范围", "99/20（C 9 · CA 5 · O 5 · L 5，Grade A 通过）", True),
    ("astra 反例 小分和≠总分", "14/20（C 5 · CA 5 · O 5 · L 5，Grade A 通过）", True),
    ("astra 反例 重复C缺CA", "16/20（C 4 · C 4 · O 4 · L 4，Grade B 通过）", True),
    ("astra 反例 小数 4.5", "16/20（C 4.5 · CA 4.5 · O 4 · L 4，Grade B 通过）", True),
    ("astra 反例 顺序错 LOCA", "16/20（L 4 · O 4 · CA 4 · C 4，Grade B 通过）", True),
    ("astra 三审反例 负数", "-16/20（C 4 · CA 4 · O 4 · L 4，Grade B 水平）", True),
    ("astra 三审反例 4/20 标 Grade A", "4/20（C 1 · CA 1 · O 1 · L 1，Grade A 通过）", True),
    ("astra 三审反例 16/20 标边缘", "16/20（C 4 · CA 4 · O 4 · L 4，Grade C 边缘，未稳过）", True),
    ("未过线却标 Grade 档位", "10/20（C 2 · CA 3 · O 2 · L 3，Grade C 边缘，未稳过，未过字数线：51 词）", True),
    ("正例 PET 16/20 Grade B", "16/20（C 4 · CA 4 · O 4 · L 4，Grade B 水平）", False),
    ("正例 PET 10/20 边缘", "10/20（C 2 · CA 3 · O 3 · L 2，Grade C 边缘，未稳过）", False),
    ("正例 PET 11/20 未过字数线", "11/20（C 2 · CA 3 · O 3 · L 3，未过字数线：52 词，不足 90 词，判为不过）", False),
]


def selftest():
    failed = 0
    for name, line, expect_err in _SELFTEST:
        errs = check_feedback(_FEEDBACK_BASE.replace("{score_line}", line))
        score_errs = [e for e in errs if any(k in e for k in ("分", "维度", "范围", "顺序", "小数", "档位"))]
        ok = bool(score_errs) == expect_err
        if not ok:
            failed += 1
            print(f"  ✗ {name}: 应拦={expect_err} 实拦={bool(score_errs)}")
        else:
            print(f"  ✓ {name}")

    # HTML 报告侧：模板正例 + astra 反例
    tpl = Path(__file__).parent.parent / "assets" / "report-template.html"
    if tpl.exists():
        html = tpl.read_text(encoding="utf-8")
        ok = not check_html(html)
        print(f"  {'✓' if ok else '✗'} HTML 模板正例")
        failed += 0 if ok else 1
        bad = html.replace('class="num">11<', 'class="num">99<')
        ok = bool(check_html(bad))
        print(f"  {'✓' if ok else '✗'} HTML 反例 99/20")
        failed += 0 if ok else 1
    print("自检全部通过" if failed == 0 else f"自检 {failed} 项失败")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
    main()
