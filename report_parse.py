"""정기보고서(사업·반기·분기) 원문 나누기.

산업 취재 도우미(DART-Joongang app.py)의 split_main_sections · report_subsections · report_fin_note ·
extract_report_blocks를 옮겨 와, 모든 부분에 **원문 줄 번호**를 함께 붙였다.
Streamlit에 기대지 않는 순수 함수라 tests/에서 바로 시험한다.

줄 번호: 본문 파일(첨부 제외) 글을 줄바꿈으로 나눈 순서, 1부터 센다. AI 발췌와 화면 원문 보기가 같은 번호를 쓴다.
"""
import re

REPORT_UNI_ROMAN = {"Ⅰ": "I", "Ⅱ": "II", "Ⅲ": "III", "Ⅳ": "IV", "Ⅴ": "V", "Ⅵ": "VI", "Ⅶ": "VII", "Ⅷ": "VIII",
                    "Ⅸ": "IX", "Ⅹ": "X", "Ⅺ": "XI", "Ⅻ": "XII"}

# 대분류 (I~XII). 로마자 번호가 아니라 제목 글자로 찾는다 (재무제표 항목 'I. 매출액'과 헷갈리지 않게)
REPORT_MAIN_SECTIONS = [
    ("co", r"회사의\s*개요"), ("biz", r"사업의\s*내용"), ("fin", r"재무에\s*관한\s*사항"), ("mdna", r"이사의\s*경영진단"),
    ("audit", r"(?:회계)?감사인의\s*감사의견"), ("board", r"이사회\s*등\s*회사의\s*기관"), ("holder", r"주주에\s*관한\s*사항"),
    ("staff", r"임원\s*및\s*직원"), ("affil", r"계열회사\s*등에\s*관한"), ("related", r"대주주\s*등과의\s*거래"),
    ("etc", r"그\s*밖에\s*투자자\s*보호"), ("detail", r"상세표"),
]
MAIN_LABELS = {
    "co": "I. 회사의 개요", "biz": "II. 사업의 내용", "fin": "III. 재무에 관한 사항", "mdna": "IV. 이사의 경영진단 및 분석의견",
    "audit": "V. 회계감사인의 감사의견 등", "board": "VI. 이사회 등 회사의 기관에 관한 사항", "holder": "VII. 주주에 관한 사항",
    "staff": "VIII. 임원 및 직원 등에 관한 사항", "affil": "IX. 계열회사 등에 관한 사항", "related": "X. 대주주 등과의 거래내용",
    "etc": "XI. 그 밖에 투자자 보호를 위하여 필요한 사항", "detail": "XII. 상세표",
}
REPORT_SUB_SECTIONS = {
    "co": [("overview", r"회사의\s*개요"), ("history", r"회사의\s*연혁"), ("capital", r"자본금\s*변동사항"),
           ("shares", r"주식의\s*총수\s*등"), ("voting", r"의결권\s*현황"), ("dividend", r"배당에\s*관한\s*사항")],
    "biz": [("overview", r"사업의\s*개요"), ("products", r"주요\s*제품\s*및\s*서비스"), ("plant", r"원재료\s*및\s*생산설비"),
            ("sales", r"매출\s*및\s*수주상황"), ("risk", r"위험관리\s*및\s*파생거래"), ("rnd", r"주요계약\s*및\s*연구개발활동"),
            ("etc", r"기타\s*참고사항"), ("fin_ops", r"영업의\s*현황"), ("fin_deriv", r"파생상품거래\s*현황"),
            ("fin_equip", r"영업설비"), ("fin_health", r"재무건전성")],
    "fin": [("summary", r"요약재무정보"), ("dividend", r"배당에\s*관한\s*사항"), ("funding", r"증권의\s*발행을\s*통한\s*자금조달"),
            ("other", r"기타\s*재무에\s*관한\s*사항")],
    "audit": [("ext", r"외부감사에\s*관한\s*사항"), ("internal", r"내부통제에\s*관한\s*사항")],
    "board": [("board", r"이사회에\s*관한\s*사항"), ("auditcom", r"감사제도에\s*관한\s*사항")],
    "staff": [("people", r"임원\s*및\s*직원\s*등의\s*현황"), ("pay", r"임원의\s*보수\s*등")],
    "etc": [("progress", r"공시내용\s*진행\s*및\s*변경사항"), ("contingent", r"우발부채\s*등에\s*관한\s*사항"),
            ("sanction", r"제재\s*등과\s*관련된\s*사항"), ("after", r"작성기준일\s*이후\s*발생한\s*주요사항")],
    "detail": [("consol", r"연결대상\s*종속회사\s*현황"), ("affil", r"계열회사\s*현황"), ("invest", r"타법인출자\s*현황"),
               ("rnd", r"연구개발실적")],
}
REPORT_NOTES = {  # 재무 주석에서 따로 뽑는 항목: 블록 이름 -> 주석 제목 정규식
    "note_contingent": r"우발부채", "note_related": r"특수관계자", "note_segment": r"(?:영업)?부문(?:별)?\s*(?:보고|정보)|영업부문",
    "note_expense": r"비용의\s*성격별", "note_inventory": r"재고자산", "note_deriv": r"파생상품",
}

# 블록 이름 -> 화면·프롬프트 이름 (AI가 근거 위치를 적을 때도 이 이름을 쓴다)
REPORT_BLOCK_LABELS = {
    "co_shares": "I-4. 주식의 총수 등(자기주식)", "co_dividend": "I-6. 배당에 관한 사항",
    "biz_overview": "II-1. 사업의 개요", "biz_products": "II-2. 주요 제품 및 서비스", "biz_plant": "II-3. 원재료 및 생산설비",
    "biz_sales": "II-4. 매출 및 수주상황", "biz_risk": "II-5. 위험관리 및 파생거래", "biz_rnd": "II-6. 주요계약 및 연구개발활동",
    "biz_etc": "II-7. 기타 참고사항", "biz_fin_ops": "II(금융업). 영업의 현황", "biz_fin_equip": "II(금융업). 영업설비",
    "fin_summary": "III-1. 요약재무정보", "fin_dividend": "III-6. 배당에 관한 사항", "fin_funding": "III-7. 증권의 발행을 통한 자금조달",
    "mdna": "IV. 이사의 경영진단 및 분석의견",
    "audit_ext": "V-1. 외부감사에 관한 사항", "audit_internal": "V-2. 내부통제에 관한 사항",
    "board_board": "VI-1. 이사회에 관한 사항",
    "holder": "VII. 주주에 관한 사항",
    "staff_people": "VIII-1. 임원 및 직원 등의 현황", "staff_pay": "VIII-2. 임원의 보수 등",
    "affil": "IX. 계열회사 등에 관한 사항", "related": "X. 대주주 등과의 거래내용",
    "etc_contingent": "XI-2. 우발부채 등에 관한 사항", "etc_sanction": "XI-3. 제재 등과 관련된 사항",
    "etc_after": "XI-4. 작성기준일 이후 발생한 주요사항",
    "detail_consol": "XII-1. 연결대상 종속회사 현황(상세)", "detail_invest": "XII-3. 타법인출자 현황(상세)",
    "detail_rnd": "XII-4. 연구개발실적(상세)",
    "note_contingent": "재무 주석 > 우발부채와 약정사항", "note_related": "재무 주석 > 특수관계자와의 거래",
    "note_segment": "재무 주석 > 부문(영업부문) 정보", "note_expense": "재무 주석 > 비용의 성격별 분류",
    "note_inventory": "재무 주석 > 재고자산", "note_deriv": "재무 주석 > 파생상품",
}
# 블록마다 줄 수 상한 대신 글자 수 상한 (아주 긴 표가 있어도 이만큼만 AI에 보낸다). 없으면 DEFAULT_CAP
REPORT_BLOCK_CAPS = {
    "mdna": 45000, "holder": 30000, "related": 20000, "affil": 45000, "detail_invest": 20000, "detail_rnd": 20000,
    "detail_consol": 20000, "staff_people": 30000, "note_contingent": 12000, "note_related": 25000, "note_segment": 15000,
    "note_expense": 6000, "note_inventory": 6000, "note_deriv": 12000,
}
DEFAULT_CAP = 30000


class ParseError(Exception):
    """목차를 찾지 못함 등 — 화면에 그대로 보여 준다."""


def normalize(text):
    for k, v in REPORT_UNI_ROMAN.items():
        text = text.replace(k, v)
    return text.replace("\x0c", "\n")


def to_lines(text):
    """원문 글 -> 줄 목록 (0번 칸 = 1번 줄)."""
    return normalize(text).split("\n")


def is_heading_line(s):
    """제목 줄 후보: 짧고, 목차의 점선(…..)이 없는 줄."""
    return 0 < len(s) <= 80 and "…" not in s and "....." not in s and "·····" not in s


def main_spans(lines):
    """-> {대분류 키: (제목 줄 i, 끝 j)} (0부터, 본문은 i+1..j-1). 같은 제목이 목차에도 있으면 뒤 글이 가장 긴 쪽(본문)."""
    cands = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not is_heading_line(s):
            continue
        m = re.match(r"^[IVX]+\s*\.\s*(.+)$", s)
        if not m:
            continue
        for key, pat in REPORT_MAIN_SECTIONS:
            if re.match(pat, m.group(1)):
                cands.append((i, key))
                break
    if not cands:
        return {}
    nxt = {i: (cands[j + 1][0] if j + 1 < len(cands) else len(lines)) for j, (i, _) in enumerate(cands)}
    best = {}
    for i, key in cands:
        span = nxt[i] - i
        if key not in best or span > best[key][1]:
            best[key] = (i, span)
    starts = sorted((i, key) for key, (i, _) in best.items())
    out = {}
    for j, (i, key) in enumerate(starts):
        end = starts[j + 1][0] if j + 1 < len(starts) else len(lines)
        out[key] = (i, end)
    return out


def sub_spans(lines, start, end, main_key):
    """대분류 (start, end) 안의 '1. 제목' 소제목들 -> {소제목 키: [(i, j), ...]} (같은 제목이 여럿이면 모두, 예: 제조업·금융업)."""
    specs = REPORT_SUB_SECTIONS.get(main_key, [])
    heads = []
    for i in range(start + 1, end):
        s = lines[i].strip()
        if not is_heading_line(s):
            continue
        m = re.match(r"^\d{1,2}\s*\.\s*(?:\([^)]{1,12}\))?\s*(.+)$", s)
        if not m:
            continue
        for key, pat in specs:
            if re.match(pat, m.group(1)):
                heads.append((i, key))
                break
    out = {}
    for j, (i, key) in enumerate(heads):
        stop = heads[j + 1][0] if j + 1 < len(heads) else end
        out.setdefault(key, []).append((i, stop))
    return out


def note_span(lines, start, end, name_pat):
    """재무 주석 한 항목 ('16. 우발부채와 약정사항 (연결)') -> (i, j) 또는 None. 연결재무제표 주석을 먼저 찾는다."""
    found = []
    for i in range(start + 1, end):
        s = lines[i].strip()
        if not is_heading_line(s):
            continue
        m = re.match(r"^(\d{1,2})\s*\.\s*(?:" + name_pat + r").*$", s)
        if m:
            found.append((i, int(m.group(1)), "(연결)" in s))
    if not found:
        return None
    found.sort(key=lambda x: (not x[2], x[0]))
    i, n, _ = found[0]
    stop = end
    for k in range(i + 1, end):
        s = lines[k].strip()
        if is_heading_line(s) and re.match(rf"^{n + 1}\s*\.\s*\S", s):
            stop = k
            break
    return (i, stop)


def span_text(lines, spans, cap=None, numbered=False):
    """[(i, j)] 범위들의 글 (제목 줄 제외). numbered=True면 줄 앞에 '123: '(1부터 센 원문 줄 번호)."""
    out, n = [], 0
    for i, j in spans:
        for k in range(i + 1, j):
            raw = lines[k].strip()
            if not raw:
                continue
            row = f"{k + 1}: {raw}" if numbered else raw
            n += len(row) + 1
            if cap and n > cap:
                out.append("(이하 생략)")
                return "\n".join(out)
            out.append(row)
    return "\n".join(out)


def main_part(text):
    """doc_text_from_zip 결과에서 본문 파일 부분 (첨부는 빈 줄 두 개 뒤)."""
    return text.split("\n\n")[0]


def parse_report(text):
    """정기보고서 글 -> dict(lines, mains{키: (i, j)}, blocks{블록 이름: [(i, j)...]}).
    본문 파일에서 못 찾으면 첨부까지 포함한 전체 글에서 찾는다. 하나도 못 찾으면 ParseError."""
    lines = to_lines(main_part(text))
    mains = main_spans(lines)
    if not mains:
        lines = to_lines(text)
        mains = main_spans(lines)
    if not mains:
        raise ParseError("이 보고서에서 '사업의 내용', '재무에 관한 사항' 같은 목차를 찾지 못했어요. "
                         "정기보고서(사업·반기·분기)가 맞는지 확인하거나 DART 원문으로 보세요.")
    blocks = {}
    for main_key, (i, j) in mains.items():
        for sub_key, spans in sub_spans(lines, i, j, main_key).items():
            name = f"{main_key}_{sub_key}"
            if name in REPORT_BLOCK_LABELS:
                blocks[name] = spans
    for key in ("mdna", "holder", "related", "affil"):
        if key in mains:
            blocks[key] = [mains[key]]
    if "fin" in mains:
        fi, fj = mains["fin"]
        for key, pat in REPORT_NOTES.items():
            sp = note_span(lines, fi, fj, pat)
            if sp:
                blocks[key] = [sp]
    # 내용이 빈 블록은 뺀다
    blocks = {k: v for k, v in blocks.items() if span_text(lines, v, cap=200).strip()}
    return {"lines": lines, "mains": mains, "blocks": blocks}


def block_text(parsed, name, numbered=True, cap=None):
    spans = parsed["blocks"].get(name)
    if not spans:
        return ""
    return span_text(parsed["lines"], spans, cap=cap or REPORT_BLOCK_CAPS.get(name, DEFAULT_CAP), numbered=numbered)


def main_text(parsed, key, numbered=True, cap=None):
    sp = parsed["mains"].get(key)
    return span_text(parsed["lines"], [sp], cap=cap, numbered=numbered) if sp else ""


def block_first_line(parsed, name):
    """블록이 시작하는 원문 줄 번호(1부터). 없으면 None."""
    spans = parsed["blocks"].get(name)
    return spans[0][0] + 1 if spans else None
