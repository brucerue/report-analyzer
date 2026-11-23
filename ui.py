"""화면 꾸미기: '교정지' — 원문은 괘선 종이처럼, 근거·새 문장은 형광펜, 없어진 문장은 붉은 줄긋기.

색 (CSS 변수와 같음)
  종이 #F2F4F3 · 먹 #1F2B30 · 형광펜 #EEF36A · 교정 빨강 #B8322A · 인주 청 #24479A · 괘선 #CDD5D2
글꼴: 제목 고운바탕, 본문 IBM Plex Sans KR, 원문 나눔고딕코딩
"""
import html
import re

import streamlit as st

CSS = """<style>
@import url("https://fonts.googleapis.com/css2?family=Gowun+Batang:wght@400;700&family=IBM+Plex+Sans+KR:wght@400;500;600&family=Nanum+Gothic+Coding:wght@400;700&display=swap");
:root{
  --paper:#F2F4F3; --sheet:#FFFFFF; --ink:#1F2B30; --ink-soft:#56646A; --rule:#CDD5D2;
  --marker:#EEF36A; --red:#B8322A; --seal:#24479A;
}
html, body, [data-testid="stAppViewContainer"], .stApp{ background:var(--paper); color:var(--ink); }
.stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp button, .stApp textarea{
  font-family:"IBM Plex Sans KR", system-ui, sans-serif;
}
.stApp p, .stApp li{ line-height:1.7; }
[data-testid="stMainBlockContainer"], .block-container{ max-width:1080px; padding-top:2.2rem; }
[data-testid="stHeader"]{ background:transparent; }

/* 앱 이름 */
.ra-masthead{ display:flex; align-items:baseline; gap:.9rem; flex-wrap:wrap; margin:0 0 1.4rem; }
.ra-masthead h1{ font-family:"Gowun Batang", serif; font-weight:700; font-size:2rem; letter-spacing:-.01em;
  margin:0; padding:0; color:var(--ink); }
.ra-masthead p{ margin:0; color:var(--ink-soft); font-size:.92rem; }

/* 문서 표지 */
.ra-cover{ background:var(--sheet); border:1px solid var(--rule); border-left:6px solid var(--seal);
  padding:1.3rem 1.5rem 1.1rem; margin:.6rem 0 1.2rem; }
.ra-cover .corp{ font-family:"Gowun Batang", serif; font-size:2.4rem; font-weight:700; line-height:1.15; margin:0; }
.ra-cover .doc{ font-size:1.15rem; margin:.35rem 0 .9rem; color:var(--ink); }
.ra-cover .meta{ display:flex; flex-wrap:wrap; gap:.4rem 2rem; margin:0; padding:0; font-size:.9rem; list-style:none; }
.ra-cover .meta li{ margin:0; padding:0; }
.ra-cover .meta .k{ color:var(--ink-soft); margin-right:.45rem; }
.ra-cover .meta .v{ font-weight:500; }
.ra-cover a{ color:var(--seal); font-weight:600; text-decoration:none; border-bottom:1px solid currentColor; }
.ra-cover a:focus-visible{ outline:3px solid var(--seal); outline-offset:3px; }

/* 원문 (괘선 종이) */
.ra-sheet{ background:var(--sheet); border:1px solid var(--rule); max-height:560px; overflow:auto;
  font-family:"Nanum Gothic Coding", monospace; font-size:.86rem; line-height:1.75; margin:.3rem 0 .8rem; }
.ra-sheet .ln{ display:grid; grid-template-columns:5.4rem 1fr; border-bottom:1px solid #E6EBE9; }
.ra-sheet .no{ color:#8A979C; text-align:right; padding:0 .8rem 0 0; border-right:1px solid var(--rule);
  user-select:none; font-variant-numeric:tabular-nums; }
.ra-sheet .tx{ padding:0 .8rem; white-space:pre-wrap; word-break:break-all; }
.ra-sheet .mark .tx{ background:linear-gradient(transparent 12%, var(--marker) 12%, var(--marker) 88%, transparent 88%); }
.ra-sheet .mark .no{ color:var(--ink); font-weight:700; }
.ra-sheet .gone .tx{ color:var(--red); text-decoration:line-through; text-decoration-thickness:1.5px; }
.ra-sheet .gone .no{ color:var(--red); }
.ra-sheet .gap .tx{ color:#9AA6AA; }
.ra-sheet::-webkit-scrollbar{ width:10px; } .ra-sheet::-webkit-scrollbar-thumb{ background:var(--rule); }

/* 부분 목록 */
.ra-parts{ display:grid; grid-template-columns:repeat(auto-fill, minmax(290px, 1fr)); column-gap:2.4rem; border-top:1px solid var(--ink); margin:.4rem 0 1rem; }
.ra-parts div{ display:flex; justify-content:space-between; gap:1rem; padding:.55rem 0; border-bottom:1px solid var(--rule); font-size:.92rem; }
.ra-parts span{ color:var(--ink-soft); font-variant-numeric:tabular-nums; white-space:nowrap; }
.ra-parts .none{ color:#9AA6AA; }

/* 기사 포인트 카드 */
.ra-cards{ display:grid; grid-template-columns:repeat(auto-fill, minmax(320px, 1fr)); gap:1rem; margin:.6rem 0 1rem; }
.ra-card{ background:var(--sheet); border:1px solid var(--rule); border-top:3px solid var(--ink); padding:1rem 1.15rem .9rem; }
.ra-card h3{ font-family:"IBM Plex Sans KR", sans-serif; font-size:.95rem; font-weight:600; margin:0 0 .5rem; padding:0; color:var(--ink); }
.ra-card .val{ font-size:1.75rem; font-weight:600; line-height:1.2; font-variant-numeric:tabular-nums; letter-spacing:-.01em; }
.ra-card .cmp{ font-size:.88rem; color:var(--ink-soft); margin:.25rem 0 .6rem; }
.ra-card .cmp b{ color:var(--ink); font-weight:600; }
.ra-card table{ width:100%; border-collapse:collapse; font-size:.88rem; margin:.3rem 0 .4rem; }
.ra-card td{ border-top:1px solid #E6EBE9; padding:.35rem 0; vertical-align:top; }
.ra-card td.l{ color:var(--ink-soft); padding-right:.8rem; width:38%; }
.ra-card td.ln{ text-align:right; white-space:nowrap; padding-left:.6rem; color:#8A979C; font-size:.78rem; font-variant-numeric:tabular-nums; }
.ra-card td.raw{ font-family:"Nanum Gothic Coding", monospace; font-size:.8rem; word-break:break-all; }
.ra-card .foot{ font-size:.78rem; color:var(--ink-soft); margin:.4rem 0 0; }
.ra-card .empty{ color:var(--ink-soft); font-size:.9rem; margin:0; }

/* AI 답의 근거 표시 */
.ra-cite{ font-size:.78rem; color:var(--seal); border:1px solid #B9C6E4; background:#F1F4FB; padding:.05rem .4rem;
  white-space:nowrap; border-radius:2px; }
.ra-answer{ background:var(--sheet); border:1px solid var(--rule); padding:1.1rem 1.4rem; margin:.6rem 0; }
.ra-answer strong{ font-weight:600; }
.ra-note{ color:var(--ink-soft); font-size:.86rem; margin:.3rem 0 0; }
.ra-legend{ font-size:.86rem; color:var(--ink-soft); margin:.2rem 0 .6rem; }
.ra-legend .m{ background:var(--marker); padding:0 .3rem; color:var(--ink); }
.ra-legend .r{ color:var(--red); text-decoration:line-through; }

/* Streamlit 기본 부품 정리 */
.stTabs [data-baseweb="tab-list"]{ gap:1.6rem; border-bottom:1px solid var(--rule); }
.stTabs [data-baseweb="tab"]{ padding:.6rem 0; font-size:1rem; }
.stTabs [aria-selected="true"]{ color:var(--ink); font-weight:600; }
.stTabs [data-baseweb="tab-highlight"]{ background:var(--ink); height:3px; }
[data-testid="stForm"]{ background:var(--sheet); border:1px solid var(--rule); border-radius:0; padding:1rem 1.2rem; }
.stButton button[kind="primary"], [data-testid="stFormSubmitButton"] button{ background:var(--seal); border-color:var(--seal); border-radius:2px; }
.stButton button, [data-testid="stFormSubmitButton"] button{ border-radius:2px; font-weight:500; }
[data-testid="stExpander"] details{ border:1px solid var(--rule); border-radius:0; background:var(--sheet); }
[data-testid="stExpander"] summary{ font-weight:500; }
[data-testid="stAlert"]{ border-radius:0; }
@media (max-width:640px){
  .ra-cover .corp{ font-size:1.8rem; }
  .ra-sheet .ln{ grid-template-columns:3.4rem 1fr; }
  .ra-masthead h1{ font-size:1.6rem; }
}
</style>
"""


def inject():
    st.html(CSS)  # 스타일만 있는 st.html은 화면 전체에 적용된다


def esc(s):
    return html.escape(str(s or ""), quote=True)


def masthead(updated):
    st.html(f'<div class="ra-masthead"><h1>사업보고서 분석기</h1>'
                f'<p>정기보고서를 목차별로 읽고, 근거 줄을 짚어 줍니다. 숫자는 원문으로 확인하세요. (업데이트 {esc(updated)})</p></div>',
                )


def cover(corp, report_name, filed, versions, prev_name, link):
    items = [("제출일", filed)]
    if versions > 1:
        items.append(("정정", f"{versions - 1}회 — 최신본을 읽어요"))
    items.append(("종목코드", corp.get("stock_code") or "비상장"))
    dl = "".join(f'<li><span class="k">{esc(k)}</span><span class="v">{esc(v)}</span></li>' for k, v in items)
    st.html(f'<section class="ra-cover" aria-label="고른 보고서"><p class="corp">{esc(corp["corp_name"])}</p>'
                f'<p class="doc">{esc(report_name)}</p><ul class="meta">{dl}<li><a href="{esc(link)}" target="_blank" rel="noopener">DART 원문 열기</a></li></ul></section>')


def sheet(rows, height=None):
    """rows: [(줄 번호 또는 None, 글, 종류 '' | 'mark' | 'gone' | 'gap')] -> 괘선 원문."""
    body = "".join(f'<div class="ln {k}"><span class="no">{"" if n is None else n}</span><span class="tx">{esc(t)}</span></div>'
                   for n, t, k in rows)
    style = f' style="max-height:{height}px"' if height else ""
    st.html(f'<div class="ra-sheet" role="region" tabindex="0" aria-label="보고서 원문"{style}>{body}</div>')


def numbered_rows(text, marks=()):
    """'123: 글' 줄들 -> sheet rows. marks에 든 줄 번호는 형광펜."""
    out = []
    for raw in str(text or "").split("\n"):
        m = re.match(r"^(\d+): (.*)$", raw)
        if m:
            n = int(m.group(1))
            out.append((n, m.group(2), "mark" if n in marks else ""))
        elif raw.strip():
            out.append((None, raw, "gap"))
    return out


def around_rows(lines, centers, width=3):
    """근거 줄 앞뒤 원문 (가운데 줄은 형광펜, 떨어진 묶음 사이는 '…')."""
    want = sorted({k for c in centers for k in range(max(1, c - width), min(len(lines), c + width) + 1)})
    out, last = [], None
    for k in want:
        if last is not None and k != last + 1:
            out.append((None, "…", "gap"))
        out.append((k, lines[k - 1].strip(), "mark" if k in centers else ""))
        last = k
    return out


def parts_list(found, missing):
    cells = "".join(f"<div>{esc(name)}<span>줄 {n:,}</span></div>" for name, n in found)
    st.html(f'<div class="ra-parts">{cells}</div>')
    if missing:
        note(f"못 찾은 부분 {len(missing)}개: " + ", ".join(missing))


CITE_RE = re.compile(r"\[([^\[\]\n]{2,60}?(?:줄\s*\d+[^\[\]\n]*)?)\]")


def answer(md_text):
    """AI 답(마크다운)을 종이 위에. [근거] 표시는 작은 청색 꼬리표로. HTML은 먼저 이스케이프한다."""
    t = html.escape(str(md_text or ""), quote=False).replace("~", "\\~")
    t = CITE_RE.sub(lambda m: f'<span class="ra-cite">{m.group(1)}</span>', t)
    with st.container():
        st.markdown(f'<div class="ra-answer">\n\n{t}\n\n</div>', unsafe_allow_html=True)


def note(text):
    st.html(f'<p class="ra-note">{esc(text)}</p>')


def legend(marker_text=None, red_text=None):
    bits = []
    if marker_text:
        bits.append(f'<span class="m">형광펜</span> {esc(marker_text)}')
    if red_text:
        bits.append(f'<span class="r">줄긋기</span> {esc(red_text)}')
    st.html(f'<p class="ra-legend">{"&nbsp;&nbsp;&nbsp;".join(bits)}</p>')


def cards(items):
    """기사 포인트 카드들 (points.build_cards 결과)."""
    html_cards = []
    for c in items:
        body = [f"<h3>{esc(c['title'])}</h3>"]
        if c.get("empty"):
            body.append(f'<p class="empty">{esc(c["empty"])}</p>')
        else:
            if c.get("value"):
                body.append(f'<div class="val">{esc(c["value"])}</div>')
            cmp = []
            if c.get("prev"):
                cmp.append(f"비교 {esc(c['prev'])}")
            if c.get("change"):
                cmp.append(f"<b>{esc(c['change'])}</b>")
            if cmp:
                body.append(f'<p class="cmp">{", ".join(cmp)}</p>')
            if c.get("rows"):
                trs = []
                for label, text, line in c["rows"]:
                    ln = f"줄 {line:,}" if line else ""
                    if label:
                        trs.append(f'<tr><td class="l">{esc(label)}</td><td>{esc(text)}</td><td class="ln">{ln}</td></tr>')
                    else:
                        trs.append(f'<tr><td class="raw" colspan="2">{esc(text)}</td><td class="ln">{ln}</td></tr>')
                body.append(f"<table>{''.join(trs)}</table>")
            foot = [c.get("note") or "", ("출처: " + c["source"]) if c.get("source") else ""]
            foot = [f for f in foot if f]
            if foot:
                body.append(f'<p class="foot">{"<br>".join(esc(f) for f in foot)}</p>')
        html_cards.append(f'<article class="ra-card">{"".join(body)}</article>')
    st.html(f'<div class="ra-cards">{"".join(html_cards)}</div>')
