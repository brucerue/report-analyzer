"""기사 쓰기: 기자가 고른 요소(카드)를 리드 요소부터 차례로 엮어 기사 초안을 만든다.

- 재료는 writer.py가 카드마다 만든 숫자 문장뿐이다 (AI 없음, 숫자는 DART 자료·원문 그대로).
- 첫 문장: '{회사}가 {일}일 공시한 {보고서}에 따르면, {리드 요소 첫 문장}' (기사 첫머리 관행).
- 리드 요소의 나머지 문장 → 고른 순서대로 다른 요소 문단.
- 선택: Gemini로 기사체 다듬기. 다듬은 글의 숫자가 재료에 그대로 있는지 대조해 없으면 경고 (analyses.unverified_numbers).
"""
import re

import plant

TITLE_WORDS = {  # 제목 후보에 쓰는 짧은 이름
    "income": "실적", "staff": "직원", "pay": "보수", "holder": "지분", "return": "주주환원", "capex": "시설투자",
    "debt": "부채비율", "invest": "출자", "consol": "종속회사", "plant": "가동률", "material": "원재료",
    "rnd": "R&D", "region": "지역별 매출", "reason": "실적 배경",
}


def choices(cards):
    """기사에 넣을 수 있는 요소 = 문장이 있는 카드. -> [(key, 이름)] (카드 순서)."""
    out, seen = [], set()
    for c in cards:
        if c.get("sentences") and c["key"] not in seen:
            seen.add(c["key"])
            out.append((c["key"], c["title"]))
    return out


def intro(corp, report_name, filed):
    """'삼성전자가 10일 공시한 2025년 사업보고서에 따르면,' (filed = 'YYYYMMDD')."""
    day = f"{int(filed[6:8])}일 " if filed and len(filed) == 8 else ""
    name = report_name
    m = re.match(r"(사업보고서|반기보고서|분기보고서)\s*\((\d{4})\.(\d{2})\)", report_name or "")
    if m:
        kind, y, mo = m.group(1), m.group(2), int(m.group(3))
        name = {"사업보고서": f"{y}년 사업보고서", "반기보고서": f"{y}년 반기보고서"}.get(kind, f"{y}년 {'1분기' if mo == 3 else '3분기'} 보고서")
    return f"{plant.josa(corp, '이/가')} {day}공시한 {name}에 따르면"


def compose(cards, picked, lead, corp, report_name, filed):
    """picked = 고른 요소 key들(순서대로), lead = 맨 앞에 올 key. -> dict(title, paragraphs, text, source)."""
    by = {c["key"]: c for c in cards if c.get("sentences")}
    order = [lead] + [k for k in picked if k != lead and k in by]
    paras, source = [], []
    for i, k in enumerate(order):
        sents = list(by[k]["sentences"])
        source += sents
        if i == 0:
            sents[0] = f"{intro(corp, report_name, filed)} {sents[0]}"
        paras.append(" ".join(sents))
    title = make_title(by[lead], corp, [by[k] for k in order[1:3]])
    return dict(title=title, paragraphs=paras, text="\n\n".join(paras), source="\n".join(source))


def make_title(lead_card, corp, others):
    """제목 후보 (숫자는 카드 값 그대로): '삼성전자 영업이익 43조6011억원…33.2% 증가 / 가동률 79.3%'."""
    def label(c):  # 값이 숫자로 시작하면 무엇의 숫자인지 이름을 붙인다 ('가동률 88.9%'), '영업이익 …'처럼 이름이 있으면 그대로
        word, v = TITLE_WORDS.get(c["key"], c["title"]), c.get("value")
        if not v:
            return word
        return f"{word} {v}" if re.match(r"^[-\d]", str(v)) else str(v)

    ch = lead_card.get("change")
    head = f"{corp} {label(lead_card)}" + (f"…{ch}" if ch else "")
    tail = [label(c) for c in others if c.get("value") and c["key"] != "reason"]
    return head + (" / " + " · ".join(tail[:2]) if tail else "")


AI_SYSTEM = (
    "너는 중앙일보 산업부 기자의 기사 초안을 다듬는 편집 보조자다. 사용자가 준 [재료] 문장에 있는 사실과 숫자만 쓴다. "
    "숫자·단위·기간·회사명·인명은 재료 표기 그대로 옮기고, 새로 계산하거나 반올림하지 않는다. 재료에 없는 원인·전망·평가를 만들지 않는다. "
    "따옴표로 인용된 회사 설명은 '회사는 ~라고 설명했다' 형식을 유지한다. 한국어 신문 기사체로, 짧고 명확하게 쓴다."
)


def ai_prompt(draft, corp):
    return (f"아래 [초안]은 {corp} 정기보고서 숫자로 만든 기사 초안이고, [재료]는 쓸 수 있는 문장 전부다.\n"
            "초안의 문단 순서(첫 문단이 리드)를 지키면서 자연스러운 기사체로 다듬어라. 문장을 합치거나 순서를 조금 바꿔도 되지만 "
            "재료에 없는 내용은 넣지 마라.\n"
            "형식: 첫 줄에 '제목: …'(25자 안팎), 빈 줄, 본문 문단들.\n\n"
            f"[초안]\n{draft['text']}\n\n[재료]\n{draft['source']}")
