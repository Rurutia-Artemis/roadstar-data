#!/usr/bin/env python3
"""roadstar-data README hero in zh-CN / en / ja. Usage: gen_hero.py <assets/readme dir>. Palette and star motif shared with Roadstar."""
import sys
from pathlib import Path

OUT = Path(sys.argv[1])
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans', 'Noto Sans CJK SC', sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
BG, CARD, INK, MUTED, LINE = "#F7F4EE", "#FFFFFF", "#2B2A3D", "#8A8798", "#E4DED3"
COLORS = [("#F2B544", "#9A6B0C"), ("#3E9C9E", "#2E7C7E"), ("#E07A5F", "#B9583F"), ("#3E9C9E", "#2E7C7E"), ("#F2B544", "#9A6B0C")]


def star(cx, cy, r, fill):
    return (f'<path d="M{cx},{cy-r} Q{cx},{cy} {cx+r},{cy} Q{cx},{cy} {cx},{cy+r} '
            f'Q{cx},{cy} {cx-r},{cy} Q{cx},{cy} {cx},{cy-r} Z" fill="{fill}"/>')


T = {
    "zh-CN": ("大家的派活数据，汇成一张共用的分工表", "只有固定选项和取整数字 · 全部公开 · 随时撤回",
              [("同意一次", "默认不开"), ("自动回传", "跑完一场开 Issue"), ("双重校验", "本机 + Action"), ("每周汇总", "周日 00:00 JST"), ("拍板发版", "所有人一起更新")]),
    "en": ("Everyone's dispatch data, merged into one shared table", "Fixed options and rounded numbers only · all public · withdraw any time",
           [("Opt in once", "off by default"), ("Auto send", "one Issue per run"), ("Checked twice", "local + workflow"), ("Weekly merge", "Sun 00:00 JST"), ("Ship it", "everyone updates")]),
    "ja": ("みんなの割り振りデータを、共通の一枚の表に", "決まった選択肢と丸めた数字だけ、すべて公開、いつでも取り下げ可",
           [("一度だけ同意", "初期設定は無効"), ("自動で送信", "実行ごとに Issue"), ("二重の検証", "手元とワークフロー"), ("毎週集計", "日曜 0 時 JST"), ("確認して公開", "全員が同じ表へ")]),
}

for lang, (tag, sub, steps) in T.items():
    W, H = 1200, 420
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t d">',
         f'<title id="t">roadstar-data: {tag}</title>',
         f'<desc id="d">{sub}. ' + " → ".join(a + " " + b for a, b in steps) + '</desc>',
         f'<rect width="{W}" height="{H}" rx="28" fill="{BG}"/>',
         f'<text x="60" y="84" font-family="{MONO}" font-size="20" letter-spacing="3" fill="{MUTED}">ROADSTAR · COMMUNITY DATA · SCHEMA 1</text>',
         f'<text x="56" y="160" font-family="{SANS}" font-size="72" font-weight="800" fill="{INK}" letter-spacing="-1">roadstar-data</text>',
         f'<text x="60" y="214" font-family="{SANS}" font-size="30" font-weight="700" fill="{INK}">{tag}</text>',
         f'<text x="60" y="252" font-family="{SANS}" font-size="20" fill="{MUTED}">{sub}</text>',
         star(1110, 92, 34, "#F2B544")]
    cw, gap, x0, y0 = 204, 26, 40, 290
    for i, (a, b) in enumerate(steps):
        x = x0 + i * (cw + gap)
        c, dark = COLORS[i]
        s.append(f'<rect x="{x}" y="{y0}" width="{cw}" height="96" rx="20" fill="{CARD}" stroke="{LINE}" stroke-width="2"/>')
        s.append(star(x + 26, y0 + 34, 10, c))
        s.append(f'<text x="{x+44}" y="{y0+42}" font-family="{SANS}" font-size="22" font-weight="800" fill="{INK}">{a}</text>')
        s.append(f'<text x="{x+22}" y="{y0+76}" font-family="{SANS}" font-size="18" fill="{dark}">{b}</text>')
        if i < 4:
            ax = x + cw + 4
            s.append(f'<path d="M{ax},{y0+48} l16,0 m-6,-6 l6,6 l-6,6" stroke="#F2B544" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/>')
    s.append('</svg>\n')
    name = "hero.svg" if lang == "en" else f"hero.{lang}.svg"
    (OUT / name).write_text("\n".join(s), encoding="utf-8")
print("ok")
