"""AI 분석 항목 · 발췌 만들기 · 숫자 대조 · Gemini 호출.

분석 항목은 산업 취재 도우미의 PERIODIC_ANALYSES(9개)를 옮기고, 지면 기사 학습 결과로 '임원·직원'과 '주주환원'을 더했다.
원칙: 숫자는 AI가 만들지 않는다. 발췌의 줄 번호를 근거로 적게 하고, 답에 나온 숫자가 발췌에 정말 있는지 대조한다.
"""
import difflib
import re
import time

from report_parse import REPORT_BLOCK_LABELS, block_text, block_first_line

MAX_REPORT_CHARS = 75_000  # 한 번에 AI에 보내는 발췌 최대 글자 수
AI_TIMEOUT = 120


class AiError(Exception):
    def __init__(self, msg, quota=False):
        super().__init__(msg)
        self.quota = quota


REPORT_COMMON_FORMAT = (
    "아래 형식으로 써라. 발췌에 없는 항목은 건너뛰고, 있는데 '해당사항 없음'이면 그대로 적는다.\n"
    "**한 줄 요약**: 이 항목에서 기사로 가장 중요한 한 문장\n"
    "**핵심 포인트**: 3~6개 항목(- 로 시작). 숫자는 단위·기간과 함께 원문 그대로. "
    "각 항목 끝에 근거를 [부분 이름 · 줄 번호] 로 적는다 (예: [II-4. 매출 및 수주상황 · 줄 1234])\n"
    "**기사로 쓴다면 확인할 것**: 2~3개 항목(- 로 시작). 발췌만으로는 알 수 없는 배경·원인 중 취재로 확인할 질문"
)

AI_PERIODIC_SYSTEM = (
    "너는 중앙일보 산업부 기자를 돕는 정기보고서(사업·반기·분기보고서) 분석 보조자다. 사용자가 준 [발췌]에 적힌 내용만 근거로 쓴다. "
    "발췌에 없는 숫자·사실·원인·평가·전망을 절대 만들지 않는다. 숫자는 단위와 기간까지 원문 표기 그대로 옮기고 새로 계산하지 않는다. "
    "발췌의 각 줄 앞 '123: '은 원문 줄 번호다. 근거를 적을 때 이 번호를 쓴다. "
    "표는 칸을 ' | '로 구분해 줄로 나열한 것이다. 표 머리의 단위(백만원·천원·주·%)를 꼭 같이 읽는다. "
    "발췌에서 확인되지 않으면 '보고서에 없음'이라고 쓴다. 회사가 쓴 설명은 '회사는 ~라고 설명'처럼 회사의 주장으로 구분한다. "
    "위험하다는 평가는 하지 않고 사실만 쓴다. 의심되는 점은 '확인 필요'로만 표시한다. 한국어, 짧고 명확한 기사체로 쓴다."
)

# 분석 항목: 순서는 지면 기사 학습(2026.02~11, 76건) 빈도순. key, label, blocks, needs_prev, help, task
PERIODIC_ANALYSES = [
    dict(key="affil", label="출자·종속회사 변동", blocks=["detail_invest", "detail_consol", "affil"], needs_prev=False,
         help="타법인 출자 취득·처분(지분율·장부가), 연결 종속회사 수 증감, 계열회사 편입·제외 — 기사 최다(지분 매입·투자 수익·사업 철수)",
         task="① 타법인 출자 중 이번 기간 취득·처분·평가가 있었던 것(회사명, 출자 목적, 증감 주식 수·금액, 기말 지분율·장부가액, 최근 사업연도 순이익) "
              "② 연결대상 종속회사 수와 신규 편입·제외(이름) ③ 계열회사 수(상장·비상장) 증감을 정리해라. 증감 금액이 큰 순서로, M&A·지분 거래·철수의 단서를 우선한다."),
    dict(key="staff", label="임원·직원 (직원 수·평균 연봉·임원 보수)", blocks=["staff_people", "staff_pay"], needs_prev=False,
         help="직원 수(정규·기간제), 1인 평균 급여, 평균 근속, 임원 선임·사임, 5억 이상 개인별 보수",
         task="① 직원 수(사업부문·성별, 정규직·기간제)와 합계 ② 1인 평균 급여액·평균 근속연수 ③ 미등기임원 포함 임원 현황에서 눈에 띄는 선임·사임·외부 영입 "
              "④ 보수 5억원 이상 개인별 보수(이름·직위·총액, 급여·상여·퇴직소득 구분) ⑤ 임원 전체 보수 총액을 정리해라. 표의 단위(백만원·천원)를 꼭 함께 적는다."),
    dict(key="holder", label="주주·자사주·배당", blocks=["holder", "co_shares", "fin_dividend", "co_dividend"], needs_prev=False,
         help="최대주주·특수관계인 지분, 5% 이상 주주, 소액주주 수, 자기주식 취득·처분·소각, 배당금·배당성향",
         task="① 최대주주 및 특수관계인 지분(주식 수·지분율, 기초 대비 변동) ② 5% 이상 주주(국민연금 등) ③ 소액주주 수·지분율 "
              "④ 자기주식 취득·처분·소각(기초·증감·기말 주식 수, 소각 계획) ⑤ 주당 배당금·현금배당 총액·배당성향(당기·전기)을 정리해라."),
    dict(key="plant", label="생산능력·가동률·원재료·시설투자", blocks=["biz_plant", "biz_fin_equip"], needs_prev=False,
         help="제품별 생산능력·생산실적·가동률, 원재료 매입액·가격 변동, 공장 현황, 시설투자 계획",
         task="생산능력·생산실적·가동률(제품별·사업장별, 기간별 숫자), 주요 원재료 매입액과 가격 변동, 주요 생산설비(사업장, 신규·매각), "
              "시설투자(진행 중·계획 중 금액, 목적, 예상 완료 시기)를 정리해라. 기간별 표가 있으면 숫자를 시간순으로 적는다."),
    dict(key="rnd", label="연구개발·특허", blocks=["biz_rnd", "detail_rnd", "biz_etc"], needs_prev=False,
         help="연구개발비와 매출 대비 비율, 연구 조직 신설·변경, 주요 과제, 경영상 주요 계약, 특허 등 지식재산",
         task="연구개발비용(금액, 매출 대비 비율, 비용·자산 처리, 기간별 추이), 연구 조직·인력(신설·변경), 주요 연구개발 실적·과제, "
              "경영상 주요 계약(상대방·기간·내용), 지식재산권(특허 건수·지역)을 정리해라."),
    dict(key="sales", label="매출 구성·주요 고객", blocks=["biz_products", "biz_sales", "note_segment", "biz_fin_ops"], needs_prev=False,
         help="제품·지역별 매출과 비중, 주요 제품 가격 변동, 주요 매출처, 수주 잔고, 사업부문별 매출·이익",
         task="제품·서비스별/지역별 매출과 비중, 주요 제품 가격 변동, 판매경로, 주요 매출처(특정 고객 매출 비중), 수주 잔고, 사업부문별 매출·이익을 정리해라. "
              "한쪽(고객·지역·제품)으로 쏠린 정도를 짚고, 전기·전년 숫자가 표에 있으면 함께 적는다."),
    dict(key="fin", label="재무 주석 (비용·재고·파생)", blocks=["note_expense", "note_inventory", "note_deriv", "fin_funding"], needs_prev=False,
         help="비용의 성격별(인건비·원재료), 재고자산, 파생상품 부채, 증권 발행 자금조달",
         task="비용의 성격별 분류(종업원급여·원재료·감가상각 등 당기·전기), 재고자산 구성과 증감, 파생상품 자산·부채(계약 종류·금액), "
              "증권 발행을 통한 자금조달(사채·증자, 금액, 사용 계획)을 정리해라."),
    dict(key="mdna", label="경영진단 (실적 변동 원인·전망)", blocks=["mdna"], needs_prev=False,
         help="회사가 직접 설명하는 실적 변동 원인, 사업부문별 설명, 자금조달, 전망·위험 요인",
         task="이사의 경영진단 및 분석의견에서 ① 실적이 변한 이유로 회사가 든 요인 ② 사업부문별 설명 ③ 유동성·자금조달 ④ 향후 전망·계획·위험 요인을 정리해라. "
              "회사의 설명은 '회사는 ~라고 설명' 식으로 쓴다."),
    dict(key="risk", label="위험 신호 (감사·소송·제재)", blocks=["audit_ext", "audit_internal", "etc_contingent", "etc_sanction", "etc_after", "note_contingent"],
         needs_prev=False, help="감사의견, 핵심감사사항, 내부회계, 소송·우발채무·채무보증, 제재, 보고기간 이후 중요사항",
         task="항목마다 '있음/없음/확인 불가'와 내용을 적어라: 감사의견 종류, 강조사항, 핵심감사사항(KAM) 제목, 계속기업 불확실성, 내부회계관리제도 의견, "
              "소송(원고·피고·금액), 채무보증·담보·우발부채(금액), 제재(행정·사법·과태료), 작성기준일 이후 중요사항. 위험하다는 평가는 하지 않는다."),
    dict(key="related", label="특수관계자·대주주 거래", blocks=["related", "note_related"], needs_prev=False,
         help="특수관계자·대주주와의 거래 상대방·유형·금액, 채권·채무 잔액",
         task="특수관계자·대주주와의 거래를 거래액이 큰 순으로 정리해라: 상대방, 거래 유형(매출·매입·자금대여·지급보증 등), 금액, 채권·채무 잔액. "
              "지원성 거래를 의심할 만한 단서는 '확인 필요'로만 표시한다."),
    dict(key="board", label="이사회·사외이사", blocks=["board_board"], needs_prev=False,
         help="이사회 구성, 사외이사 경력, 이사회 안건과 찬반",
         task="이사회 구성(사내·사외이사 수), 사외이사의 주요 경력(출신 분야), 이사회 주요 안건과 반대·기권이 있었던 안건을 정리해라."),
]
DIFF_BLOCKS = ["biz_overview", "biz_products", "biz_plant", "biz_sales", "biz_risk", "biz_rnd", "biz_etc", "audit_ext",
               "etc_contingent", "etc_sanction"]
DIFF_SPEC = dict(key="diff", label="달라진 문장 정리", blocks=DIFF_BLOCKS, needs_prev=True,
                 help="직전 보고서와 비교해 새로 생기거나 사라진 문장 (신사업·공장·철수·위험·소송)",
                 task="아래는 직전 보고서와 이번 보고서를 부분별로 비교해 기계적으로 뽑은 '새로 생긴 문장'과 '없어진 문장'이다 (숫자만 바뀐 줄은 제외됨). "
                      "의미 있는 변화를 골라라: 신규 사업·제품·공장·투자 계획, 중단·철수·매각, 위험 요인 문구 변화, 소송·제재의 신규 발생이나 종결, 감사 관련 변화. "
                      "표현 다듬기와 날짜 갱신은 무시한다. 변화마다 '직전 → 이번' 형태로, 근거 줄 번호(이번 보고서 기준)를 적는다.")
ANALYSIS_BY_KEY = {a["key"]: a for a in PERIODIC_ANALYSES + [DIFF_SPEC]}


# ------------------------------------------------------------
# 발췌
# ------------------------------------------------------------
def analysis_input(parsed, spec):
    """-> (발췌 글, 읽은 부분 이름들, 못 찾은 부분 이름들, 잘렸는지). 각 줄 앞에 원문 줄 번호."""
    read, missing, parts, truncated, total = [], [], [], False, 0
    for key in spec["blocks"]:
        value = block_text(parsed, key, numbered=True)
        label = REPORT_BLOCK_LABELS[key]
        if not value:
            missing.append(label)
            continue
        room = MAX_REPORT_CHARS - total
        if room <= 0:
            truncated = True
            continue
        if len(value) > room:
            value, truncated = value[:room], True
        total += len(value)
        read.append(label)
        parts.append(f"[{label}]\n{value}")
    return "\n\n".join(parts), read, missing, truncated


def _prose_lines(text):
    """'123: 문장' 줄들 -> [(줄 번호, 문장, 비교 키)]. 한글 6자 이상인 문장 줄만, 숫자는 #로 바꿔 비교."""
    out = []
    for raw in text.split("\n"):
        m = re.match(r"^(\d+): (.*)$", raw)
        no, line = (int(m.group(1)), m.group(2)) if m else (None, raw)
        line = re.sub(r"\s+", " ", line).strip()
        if len(line) >= 15 and len(re.findall(r"[가-힣]", line)) >= 6:
            out.append((no, line, re.sub(r"[\d,.]+", "#", line)))
    return out


def diff_lines(prev_text, cur_text):
    """-> (새로 생긴 [(줄 번호, 문장)], 없어진 [(직전 줄 번호, 문장)]). 숫자만 다른 줄은 같은 줄로 본다."""
    a, b = _prose_lines(prev_text), _prose_lines(cur_text)
    sm = difflib.SequenceMatcher(None, [k for *_, k in a], [k for *_, k in b], autojunk=False)
    added, removed = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "delete"):
            removed += [(n, s) for n, s, _ in a[i1:i2]]
        if tag in ("replace", "insert"):
            added += [(n, s) for n, s, _ in b[j1:j2]]
    return added, removed


def report_diff(prev_parsed, cur_parsed, blocks=DIFF_BLOCKS):
    """부분별 비교 -> [{key, label, added, removed}] (바뀐 게 있는 부분만), 비교 못 한 부분 이름들."""
    out, missing = [], []
    for key in blocks:
        cur = block_text(cur_parsed, key, numbered=True, cap=10 ** 7)
        prev = block_text(prev_parsed, key, numbered=True, cap=10 ** 7)
        if not cur or not prev:
            missing.append(REPORT_BLOCK_LABELS[key])
            continue
        added, removed = diff_lines(prev, cur)
        if added or removed:
            out.append(dict(key=key, label=REPORT_BLOCK_LABELS[key], added=added, removed=removed))
    return out, missing


def diff_input(diffs, cap=MAX_REPORT_CHARS):
    parts = []
    for d in diffs:
        add = "\n".join(f"{n}: {s}" for n, s in d["added"]) or "(없음)"
        rem = "\n".join(f"(직전 {n}): {s}" for n, s in d["removed"]) or "(없음)"
        parts.append(f"[{d['label']}]\n<새로 생긴 문장>\n{add}\n<없어진 문장>\n{rem}")
    text = "\n\n".join(parts)
    return text[:cap], len(text) > cap


# ------------------------------------------------------------
# 숫자 대조 (AI 답에 나온 숫자가 발췌에 정말 있는지)
# ------------------------------------------------------------
def squash(text):
    return re.sub(r"[\s|]+", "", str(text or ""))


NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def unverified_numbers(answer, excerpt):
    """AI 답의 숫자 중 발췌에 그대로 없는 것 (줄 번호·연도·작은 수는 뺀다). -> 목록"""
    body = squash(re.sub(r"(?m)^\d+: ", "", excerpt))  # 줄 번호는 빼고 비교
    clean = re.sub(r"\[[^\]]*\]", " ", str(answer or ""))  # [근거 · 줄 123]은 대조 대상 아님
    out = []
    for n in NUM_RE.findall(clean):
        digits = n.replace(",", "")
        if len(digits.replace(".", "")) < 3 or re.fullmatch(r"(19|20)\d\d", digits):
            continue
        if n in body or digits in body.replace(",", ""):
            continue
        if n not in out:
            out.append(n)
    return out


def cited_lines(answer):
    """AI 답에서 '줄 123' 근거 번호들."""
    return sorted({int(x) for x in re.findall(r"줄\s*(\d+)", str(answer or ""))})


# ------------------------------------------------------------
# Gemini (무료 등급). 유료 Claude 대체는 쓰지 않는다 (추가 비용 금지).
# ------------------------------------------------------------
def call_gemini(session, api_key, model, prompt, system, fallback=None):
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 8192}}
    models = [model] + ([fallback] if fallback and fallback != model else [])
    res = None
    for m in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
        for attempt in range(3):
            try:
                res = session.post(url, json=body, headers={"x-goog-api-key": api_key}, timeout=AI_TIMEOUT)
            except Exception:
                res = None
            if res is not None and res.status_code not in (500, 502, 503, 504):
                break
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
        if res is not None and res.status_code not in (500, 502, 503, 504):
            break
    if res is None or res.status_code in (500, 502, 503, 504):
        raise AiError("AI 서버가 지금 붐비거나 응답이 없어요. 1~2분 뒤 다시 눌러 주세요.")
    if res.status_code == 429:
        raise AiError("AI 무료 사용량 한도를 넘었어요. 잠시 후 다시 시도해 주세요.", quota=True)
    if res.status_code in (401, 403):
        raise AiError("AI 키(Streamlit Secrets의 GEMINI_API_KEY)를 확인해 주세요.")
    if res.status_code == 404:
        raise AiError("AI 모델 이름(Secrets의 GEMINI_MODEL)을 확인해 주세요.")
    if res.status_code != 200:
        raise AiError(f"AI 응답 오류 [{res.status_code}]")
    data = res.json()
    cands = data.get("candidates") or []
    text = "".join(p.get("text", "") for c in cands[:1] for p in (c.get("content") or {}).get("parts", []) if not p.get("thought"))
    if not text.strip():
        raise AiError("AI가 답을 돌려주지 않았어요. 다시 시도해 주세요.")
    return text.strip()


def build_prompt(corp, row, spec, body, prev_row=None):
    head = f"기업: {corp}\n보고서: {str(row.get('report_nm', '')).strip()} (접수번호 {row.get('rcept_no')})\n분석 항목: {spec['label']}\n"
    if prev_row:
        head += f"비교 대상(직전 보고서): {str(prev_row.get('report_nm', '')).strip()}\n"
    return f"{head}\n{spec['task']}\n\n{REPORT_COMMON_FORMAT}\n\n[발췌]\n{body}"


def has_content(body, needs_prev=False):
    """발췌가 거의 없으면(해당사항 없음 등) AI를 부르지 않는다."""
    useful = re.sub(r"(?m)\[[^\]]*\]|^\d+: |\s+", "", body)
    return len(useful) >= (20 if needs_prev else 60)


__all__ = ["PERIODIC_ANALYSES", "DIFF_SPEC", "ANALYSIS_BY_KEY", "analysis_input", "report_diff", "diff_input",
           "unverified_numbers", "cited_lines", "call_gemini", "build_prompt", "has_content", "AiError",
           "AI_PERIODIC_SYSTEM", "MAX_REPORT_CHARS", "block_first_line"]
