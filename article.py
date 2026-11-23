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


# ------------------------------------------------------------
# 문체 틀 (Gemini 2번: 작성 -> 규칙 점검). 문체 규칙·예문은 style.py가 paper-private에서 읽는다.
# 틀은 바로 출고할 기사가 아니라 기자가 채워 넣을 뼈대다.
# ------------------------------------------------------------
KINDS = {"B": ("B · 실적 데일리", 1200), "C": ("C · 공시 한 건 스트레이트", 800)}

APP_RULES = (
    "[이 앱의 지시 — 문체 규칙보다 우선]\n"
    "1. 이 글은 바로 출고할 기사가 아니라 기자가 채워 넣을 '틀'이다.\n"
    "2. 날짜는 숫자로 쓰지 말고 'OO일'로 둔다. 앞날 일을 말할 때만 '전날'이라고 쓴다.\n"
    "3. 멘트(인용)와 【멘트 자리】는 만들지 않는다. 끝은 마지막 사실 단락으로 맺는다. 회사 설명은 [분석 결과]의 '회사 설명' 항목에 있는 문장만 큰따옴표로 쓸 수 있다.\n"
    "4. 출처 문장은 '○○가 OO일 공시한 {보고서}에 따르면' 틀로 쓴다('실적을 발표하며'를 쓰지 않는다).\n"
    "5. 비교 기준은 하나만 쓴다(기간 값은 전년 동기). 직전 분기 등 다른 비교는 꼭 필요할 때 한 문장만.\n"
    "6. 숫자는 [분석 결과]에 있는 값만, 표기 그대로 쓴다(퍼센트 소수점 0만 떼어 '59%'). 새로 계산하지 않는다. 없으면 【확인 필요: 무엇】.\n"
    "7. 원인·전망·평가는 [분석 결과]에 없으면 쓰지 않고 【확인 필요: 원인 등】으로 자리만 둔다. 리드 둘째 문장에 이유가 필요하면 그 자리에 【확인 필요: 실적 배경】을 둔다.\n"
    "8. '이번 분기 실적' 항목이 있으면 B형은 그 분기(예: 3분기 7∼9월) 실적을 제목·리드·첫 숫자 단락에 앞세우고, 누적(1∼9월) 실적은 한 문장으로만 쓴다.\n"
    "9. 비교는 전년 동기 하나로 쓴다. 직전 분기 비교는 이번 분기가 적자이거나 흑자로 돌아섰을 때 흐름을 보여 줄 때만 한 문장. 적자에서 바뀐 영업이익률(마이너스 이익률)은 쓰지 않는다.\n"
    "10. 같은 동사('기록했다' 등)를 되풀이하지 않는다. '지난해 같은 기간'·'전년 동기'로 쓰고 '2025년 1∼9월' 같은 연도 표기를 섞지 않는다.\n"
    "11. [분석 결과]의 세부 숫자를 다 쓰지 않는다. 기사 흐름에 필요한 핵심만 고르고 나머지는 버린다.\n"
)

DROP_ROWS = ("무형자산 취득", "부채총계")  # 기사에 거의 쓰지 않는 보조 줄 (AI가 다 써 버리지 않게 넘기지 않음)
QTR_ROW = re.compile(r"분기\(\d+∼\d+월\)")


def pct0(text):
    """'59.0%' -> '59%', '1.0%p' -> '1%p' (사내 표기: 소수점 0은 정수로)."""
    return re.sub(r"(\d)\.0(?=%)", r"\1", str(text or ""))


def facts(cards, picked, lead, corp, report_name, filed):
    """고른 카드 -> AI에 넘길 분석 결과(JSON 모양 dict). 기사 문장은 넣지 않는다 (숫자·기간·비교·원문 위치만)."""
    by = {c["key"]: c for c in cards if not c.get("empty")}
    order = [k for k in [lead] + [k for k in picked if k != lead] if k in by]
    items = []
    for k in order:
        c = by[k]
        q_rows = [r for r in c["rows"] if k == "income" and QTR_ROW.search(r[0])]
        if q_rows:  # 분기·반기 보고서: 이번 분기(3개월) 실적을 따로 앞세움
            items.append({"항목": "이번 분기 실적 · " + q_rows[0][0][:QTR_ROW.search(q_rows[0][0]).end()],
                          "리드": k == lead, "세부": [{"이름": a, "값": b} for a, b, _ in q_rows], "출처": c.get("source") or ""})
        one = {"항목": c["title"] + (" (누적)" if q_rows and "누적" not in c["title"] else ""), "리드": False if q_rows else k == lead}
        if c.get("value"):
            one["값"] = c["value"]
        if c.get("prev"):
            one["비교 대상"] = c["prev"]
        if c.get("change"):
            one["증감"] = c["change"]
        rows = [{"이름": a, "값": b, **({"원문 줄": n} if n else {})} for a, b, n in c["rows"][:8]
                if b and a not in DROP_ROWS and (a, b, n) not in q_rows]
        if rows:
            one["세부" if k != "reason" else "회사 설명"] = rows
        if c.get("note"):
            one["참고"] = c["note"]
        one["출처"] = c.get("source") or ""
        items.append(one)
    m = re.match(r"(사업보고서|반기보고서|분기보고서)\s*\((\d{4})\.(\d{2})\)", report_name or "")
    rname = report_name
    if m:
        y, mo = m.group(2), int(m.group(3))
        rname = {"사업보고서": f"{y}년 사업보고서", "반기보고서": f"{y}년 반기보고서"}.get(m.group(1), f"{y}년 {'1분기' if mo == 3 else '3분기'} 보고서")
    return {"회사": corp, "보고서": rname, "공시일": f"{filed[:4]}.{filed[4:6]}.{filed[6:8]}" if filed and len(filed) == 8 else "", "항목": items}


def write_prompt(style_rules, examples, kind, data):
    """작성 호출 -> (system, prompt)."""
    import json
    label, size = KINDS[kind]
    ex = "\n\n".join(f"[예문 {i + 1}]\n{t}" for i, t in enumerate(examples))
    prompt = (f"{APP_RULES}\n"
              f"기사 유형: {label}, 분량 약 {size}자(공백 포함).\n"
              f"'리드: true'인 항목을 기사의 중심으로 삼고, 나머지 항목은 순서대로 뒤에 둔다. 리드는 숫자 없이 흐름부터 쓴다.\n"
              "형식: 첫 줄 '제목: …', 빈 줄, 본문 단락들. 다른 설명은 쓰지 않는다.\n\n"
              "아래 예문은 문체·구성만 따르고 내용(회사·숫자·사실)은 쓰지 마라.\n\n"
              f"{ex or '(이 유형 예문 없음)'}\n\n"
              f"[분석 결과]\n{json.dumps(data, ensure_ascii=False, indent=1)}")
    return style_rules, prompt


CHECK_TASK = ("이 기사에서 규칙에 어긋난 문장만 고쳐라. 숫자·사실·인용 내용은 바꾸지 마라. 날짜 'OO일'과 【확인 필요】 표시는 그대로 둔다.\n"
              "형식: 첫 줄 '제목: …', 빈 줄, 고친 본문 단락들, 빈 줄, '[고친 곳]' 줄 다음에 '- 전 → 후' 목록(고친 곳이 없으면 '- 없음').")


def check_prompt(style_rules, draft_text):
    return style_rules, f"{APP_RULES}\n{CHECK_TASK}\n\n[기사]\n{draft_text}"


def split_check(text):
    """점검 답 -> (기사, 고친 곳 목록)."""
    t = str(text or "").strip()
    parts = re.split(r"\n\s*\[고친 곳\]\s*\n?", t, maxsplit=1)
    body = parts[0].strip()
    fixes = [re.sub(r"^\s*[-•]\s*", "", x).strip() for x in parts[1].splitlines() if x.strip()] if len(parts) > 1 else []
    fixes = [f for f in fixes if f and f != "없음"]
    return body, fixes


def body_chars(text):
    """제목 줄을 뺀 본문 글자 수 (공백 포함)."""
    lines = [x for x in str(text or "").splitlines() if not x.startswith("제목:")]
    return len("\n".join(lines).strip())
