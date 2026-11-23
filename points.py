"""기사 포인트 카드: 보고서에서 기사가 자주 되는 숫자를 뽑아 직전 보고서와 비교한다 (AI 없음).

숫자 출처는 두 가지뿐이다.
  - DART 정기보고서 주요정보 API (직원·보수·최대주주·소액주주·자사주·배당) — 산업 취재 도우미에서 검증된 계산을 옮김
  - 원문 표 (타법인출자·종속회사·R&D 비율) — 표 한 행이 한 줄이라 칸을 ' | '로 나눠 읽고, 원문 줄 번호를 같이 단다
표 모양이 회사마다 제각각인 가동률·지역별 매출은 계산하지 않고 '원문에서 찾은 줄'만 보여 준다.
카드 순서는 지면 기사 학습(2026.02~11, 76건) 빈도순.
"""
import re

import report_parse as rp

API_URL = "https://opendart.fss.or.kr/api/{}.json"
REPRT = {"사업보고서": "11011", "반기보고서": "11012"}
API_ALIASES = {  # 2026년 5월 이후 제출분은 V2 주소로만 나오는 것이 있다
    "hmvAuditIndvdlBySttus": ["hmvAuditIndvdlBySttus", "hmvAuditIndvdlBySttusV2"],
    "indvdlByPay": ["indvdlByPay", "indvdlByPayV2"],
}


# ------------------------------------------------------------
# 숫자
# ------------------------------------------------------------
def to_num(x):
    """'1,234' '(1,234)' '△1,234' '-1,234' '12.5%' -> 숫자. 못 읽으면 None."""
    s = str(x if x is not None else "").replace(",", "").replace(" ", "").replace("%", "").strip()
    if s in ("", "-", "nan", "None", "－"):
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg, s = True, s[1:-1]
    if s and s[0] in "△▲-−":
        neg, s = True, s[1:]
    try:
        v = float(s)
    except ValueError:
        return None
    v = -v if neg else v
    return int(v) if v.is_integer() else v


def won_text(v, man=False):
    """원 -> 기사체 (1조2345억원 / 7200억원 / 3억5000만원 / 1,234원).
    man=True(보수·급여)면 반올림하지 않고 억 아래 만원까지 (248억4000만원)."""
    if v is None:
        return "-"
    sign, v = ("-" if v < 0 else ""), abs(v)
    if v >= 1e10 and not man:  # 100억원 이상은 억 단위로 반올림 (기사 표기)
        v = round(v / 1e8) * 1e8
    jo, eok, mn = int(v // 1e12), int(v % 1e12 // 1e8), int(v % 1e8 // 1e4)
    if jo:  # 기사 표기: 억·만 앞엔 쉼표를 쓰지 않는다 (7200억원, 7000만원)
        return f"{sign}{jo:,}조" + (f"{eok}억원" if eok else "원")
    if eok:
        return f"{sign}{eok}억" + (f"{mn}만원" if mn and (eok < 100 or man) else "원")
    if mn:
        return f"{sign}{mn}만원"
    return f"{sign}{int(v):,}원"


UNIT_MULT = {"원": 1, "천원": 1e3, "만원": 1e4, "백만원": 1e6, "억원": 1e8, "십억원": 1e9, "조원": 1e12}


def unit_of(text):
    """'(단위 : 백만원, 천주, %)' -> ('백만원', '천주'). 금액 단위·주식 단위, 못 찾으면 None."""
    m = re.search(r"단위\s*[:：]\s*([^)]*)\)", str(text or ""))
    if not m:
        return None, None
    parts = [p.strip() for p in re.split(r"[,/]", m.group(1))]
    money = next((p for p in parts if p in UNIT_MULT), None)
    shares = next((p for p in parts if p in ("주", "천주", "백만주")), None)
    return money, shares


def change_text(now, prev, pct=True):
    if now is None or prev is None:
        return None
    if pct:
        if not prev:
            return None
        c = (now - prev) / abs(prev) * 100
        return f"{abs(c):.1f}% {'증가' if c >= 0 else '감소'}"
    d = round(now - prev, 4)
    if d == 0:
        return "변동 없음"
    return f"{abs(d):,.2f}%p {'상승' if d >= 0 else '하락'}".replace(".00%p", "%p")


def card(key, title, value=None, prev=None, change=None, note=None, rows=None, source=None, lines=None, empty=None, data=None):
    """data = 카드에 쓴 숫자 그대로 (writer.py가 이것으로 기사 문장을 만든다)."""
    return dict(key=key, title=title, value=value, prev=prev, change=change, note=note, rows=rows or [],
                source=source, lines=lines or [], empty=empty, data=data or {}, sentences=[])


# ------------------------------------------------------------
# 원문 표 읽기
# ------------------------------------------------------------
def cells(line):
    """'a | b | c |' -> ['a', 'b', 'c'] (앞뒤 빈 칸 뺌)."""
    parts = [c.strip() for c in str(line).split("|")]
    while parts and parts[-1] == "":
        parts.pop()
    while parts and parts[0] == "":
        parts.pop(0)
    return parts


def block_lines(parsed, name):
    """블록의 [(줄 번호, 글)]."""
    out = []
    for i, j in parsed["blocks"].get(name, []):
        for k in range(i + 1, j):
            t = parsed["lines"][k].strip()
            if t:
                out.append((k + 1, t))
    return out


def invest_changes(parsed):
    """XII-3 타법인출자 현황(상세) -> (변동 목록, 금액 단위, 주식 단위). 변동 = 취득·처분이 있었던 법인.
    표준 서식 16칸: 법인명·상장·최초취득일·목적·최초취득금액·기초(수량·지분율·장부)·증감(수량·금액·평가손익)·기말(수량·지분율·장부)·총자산·순손익"""
    rows, money, shares, seen = [], None, None, 0
    for no, t in block_lines(parsed, "detail_invest"):
        if money is None and "단위" in t:
            money, shares = unit_of(t)
        c = cells(t)
        if len(c) != 16 or c[1].replace(" ", "") not in ("상장", "비상장"):
            continue
        seen += 1
        q0, q_chg, amt, q1 = to_num(c[5]), to_num(c[8]), to_num(c[9]), to_num(c[11])
        b0, b1 = to_num(c[7]), to_num(c[13])
        if not q_chg and not amt:
            continue  # 평가손익만 바뀐 것은 뺀다
        had, has = bool(q0 or b0), bool(q1 or b1)  # 수량 칸이 '-'인 조합·투자주식은 장부가로 판단
        if not had and has:
            kind = "신규 취득"
        elif had and not has:
            kind = "전량 처분"
        elif (q_chg or 0) > 0 or (amt or 0) > 0:
            kind = "추가 취득"
        else:
            kind = "일부 처분"
        rows.append(dict(line=no, name=c[0], kind=kind, purpose=c[3], qty_change=q_chg, amount=amt,
                         rate0=c[6], rate1=c[12], book1=to_num(c[13])))
    rows.sort(key=lambda r: -abs(r["amount"] or 0))
    invest_changes.seen = seen  # 읽은 표준 행 수 (카드 안내문용)
    return rows, money, shares


def pct_or_dash(x):
    v = to_num(x)
    return "-" if v is None else f"{x.rstrip('%')}%"


def money_text(v, unit):
    if v is None:
        return "-"
    if unit in UNIT_MULT:
        return won_text(v * UNIT_MULT[unit])
    return f"{v:,}{unit or ''}"


def consol_list(parsed):
    """XII-1 연결대상 종속회사 현황(상세) -> (회사 이름 목록, 요약 문장(줄, 글) 또는 None)."""
    names, summary, ncol = [], None, None
    for no, t in block_lines(parsed, "detail_consol"):
        if summary is None and "|" not in t and re.search(r"\d+\s*개", t) and re.search(r"종속", t):
            summary = (no, t)
        c = cells(t)
        if ncol is None and c and c[0].replace(" ", "").startswith(("상호", "회사명", "법인명")):
            ncol = len(c)  # 첫 표의 머리글 칸 수
            continue
        if ncol is None:
            continue
        if names and "|" not in t:
            break  # 첫 표가 끝남 (뒤의 변동 내역 표 등은 세지 않는다)
        if len(c) == ncol and re.search(r"\d", " ".join(c[1:])):
            names.append((no, c[0]))
    return names, summary


def stated_count(summary):
    """'연결대상 종속기업은 2025년말 현재 308개사입니다' -> 308."""
    m = re.search(r"(\d[\d,]*)\s*개\s*(?:사|회사|법인|기업)", summary[1]) if summary else None
    return to_num(m.group(1)) if m else None


def row_numbers(t):
    return [to_num(x) for x in cells(t)[1:] if to_num(x) is not None]


def rnd_ratio(parsed):
    """II-6 연구개발비용 표 -> dict(cost=(당기, 전기, 줄), ratio=(당기, 전기, 줄), unit) 또는 None. 표는 당기가 앞 칸."""
    out, unit = {}, None
    for no, t in block_lines(parsed, "biz_rnd"):
        if "단위" in t and unit is None:
            unit = unit_of(t)[0]
        key = re.sub(r"\s+", "", cells(t)[0]) if cells(t) else ""
        if "cost" not in out and key.startswith("연구개발비용") and ("계" in key or "합계" in key):
            nums = row_numbers(t)
            if nums:
                out["cost"] = (nums[0], nums[1] if len(nums) > 1 else None, no)
        if "ratio" not in out and "매출액" in key and ("비율" in key or "대비" in key):
            nums = row_numbers(t)
            if nums:
                out["ratio"] = (nums[0], nums[1] if len(nums) > 1 else None, no)
    if not out:
        return None
    out["unit"] = unit
    return out


def plant_lines(parsed, limit=10):
    """'가동률'이 든 줄과, 그 바로 뒤 표 줄(숫자가 든 '|' 줄, 6줄까지)."""
    lines = block_lines(parsed, "biz_plant")
    out, seen = [], set()
    for idx, (no, t) in enumerate(lines):
        if "가동률" not in t:
            continue
        group = [(no, t)]
        for no2, t2 in lines[idx + 1:idx + 9]:
            if "|" in t2 and re.search(r"\d", t2):
                group.append((no2, t2))
            if len(group) >= 7:
                break
        for no2, t2 in group:
            if no2 not in seen:
                seen.add(no2)
                out.append((no2, t2[:220]))
        if len(out) >= limit:
            break
    return out[:limit]


PERIOD_NOW = ("당기", "당반기", "당분기", "당기말")
PERIOD_PREV = ("전기", "전반기", "전분기", "전기말")


def region_sales(parsed):
    """재무 주석 '지역에 대한 공시' 표 -> dict(unit, now=[(지역, 금액)], prev=[...], line_now, line_prev) 또는 None.
    머리글이 여러 줄로 겹친 표(삼성전자·현대차 확인):
        | 국내 | 외국 |                                  <- 둘째 줄: 맨 앞 칸(국내·본사 소재지 국가)만 값이 있음
        | 미주 | 유럽 | 아시아 및 아프리카 | 중국 |          <- 마지막 줄: 외국의 세부 지역
        순매출액 | 46,641,151 | 133,274,793 | ... | 333,605,938 |   <- 마지막 값은 합계
    자산(비유동자산) 표는 건너뛴다."""
    lines = block_lines(parsed, "note_segment")
    out, i = {}, 0
    in_region, unit, period = False, None, None
    heads = []
    while i < len(lines):
        no, t = lines[i]
        flat = re.sub(r"\s+", "", t)
        if "지역" in flat and "공시" in flat:
            in_region = "자산" not in flat
            heads, period = [], None
        elif in_region:
            c = cells(t)
            first = re.sub(r"\s+", "", c[0]) if c else ""
            if first in PERIOD_NOW + PERIOD_PREV:
                period = "now" if first in PERIOD_NOW else "prev"
                unit = unit_of(t)[0] or unit
                heads = []
            elif t.lstrip().startswith("|") and period:
                heads.append([x for x in c if x])
            elif period and c and "매출" in first and len(c) > 2:
                vals = [to_num(x) for x in c[1:]]
                if heads and all(v is not None for v in vals):
                    leaf = heads[-1]
                    upper = heads[-2] if len(heads) >= 2 else []
                    names = None
                    if len(vals) == len(leaf) + 2 and upper:
                        names = [upper[0]] + leaf + ["합계"]
                    elif len(vals) == len(leaf) + 1:
                        names = leaf + ["합계"]
                    elif len(vals) == len(leaf):
                        names = leaf
                    if names and period not in out:
                        names = ["국내" if re.search(r"본사|국내", n) else n for n in names]
                        out[period] = list(zip(names, vals))
                        out["line_" + period] = no
                period = None
        i += 1
    if "now" not in out:
        return None
    out["unit"] = unit or "백만원"
    return out


def find_lines(parsed, blocks, pattern, limit=8, table_only=True):
    """블록들에서 pattern이 있고 숫자가 든 줄 -> [(줄 번호, 글)]. table_only면 표 줄('|')만 (판매경로 같은 긴 설명 문장을 뺀다)."""
    out = []
    for b in blocks:
        for no, t in block_lines(parsed, b):
            if re.search(pattern, t) and re.search(r"\d", t) and (not table_only or "|" in t):
                out.append((no, t[:220]))
                if len(out) >= limit:
                    return out
    return out


# ------------------------------------------------------------
# DART 구조화 자료 (산업 취재 도우미 employee_stats·dividend_summary·treasury_summary를 옮김)
# ------------------------------------------------------------
def dart_rows(jo, need):
    """응답 안에서 need 항목을 가진 행 (옛 'list' 모양·V2 'group' 모양 모두). 당기 행만."""
    out = []

    def walk(node):
        if isinstance(node, dict):
            if all(k in node for k in need):
                out.append({k: v for k, v in node.items() if not isinstance(v, (list, dict))})
            for v in node.values():
                if isinstance(v, (list, dict)):
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(jo or {})
    return [r for r in out if str(r.get("fscl_year", "") or "").strip() in ("", "당기", "-")]


def is_total(text):
    """'합계'·'성별합계'·'총계'·'소계'·'계'·'전체' 같은 합계 칸 (삼성전자 2025: 사업부문 칸에 '성별합계')."""
    t = str(text or "").replace(" ", "")
    return t in ("계", "전체") or any(w in t for w in ("합계", "총계", "소계"))


def parse_years(text):
    t = str(text or "").replace(",", "").strip()
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*년?\s*(?:(\d+)\s*개월)?\s*$", t)
    return float(m.group(1)) + (int(m.group(2)) / 12 if m.group(2) else 0) if m else None


def _weighted(rows, col, conv=to_num):
    w = [(conv(r.get(col)), to_num(r.get("sm")) or 0) for r in rows]
    w = [(v, n) for v, n in w if v is not None and n]
    return sum(v * n for v, n in w) / sum(n for _, n in w) if w else None


def employee_stats(jo):
    """직원 현황 -> {count, avg(1인 평균 급여, 원), tenure, avg_how}.
    - 직원 수: 합계 줄을 뺀 세부 줄의 합 (세부 줄이 없으면 합계 줄). 삼성전자처럼 '성별합계' 줄이 섞여도 두 번 세지 않는다.
    - 1인 평균 급여: 보고서에 적힌 '1인 평균 급여액'(jan_salary_am)을 직원 수로 가중 평균 — 기사가 쓰는 값과 같은 방식
      (SK하이닉스 2025: 남 1억9800만원·여 1억5900만원 -> 1억8500만원). 이 값이 비어 있는 줄은 건너뛰고,
      어디에도 없으면 급여 총액 ÷ 직원 수."""
    rows = dart_rows(jo, ["sm"])
    if not rows:
        return {"count": None, "avg": None, "tenure": None, "avg_how": None}
    tot = [r for r in rows if is_total(r.get("fo_bbm")) or is_total(r.get("sexdstn"))]
    detail = [r for r in rows if r not in tot]
    grand = [r for r in tot if (is_total(r.get("fo_bbm")) or not str(r.get("fo_bbm") or "").strip())
             and (is_total(r.get("sexdstn")) or not str(r.get("sexdstn") or "").strip())]
    base = detail or tot
    count = sum(to_num(r.get("sm")) or 0 for r in base) or None
    if grand and to_num(grand[0].get("sm")) and not detail:
        count = to_num(grand[0].get("sm"))
    avg, how = None, None
    if grand and to_num(grand[0].get("jan_salary_am")):
        avg, how = to_num(grand[0]["jan_salary_am"]), "보고서 합계 값"
    else:
        for group in (detail, tot):  # 세부 줄에 값이 있으면 세부, 없으면 합계 줄(성별합계 등)로 가중 평균
            if any(to_num(r.get("jan_salary_am")) for r in group):
                avg, how = _weighted([r for r in group if to_num(r.get("jan_salary_am"))], "jan_salary_am"), "1인 평균 급여액 가중 평균"
                break
    if avg is None and count:
        total = sum(to_num(r.get("fyer_salary_totamt")) or 0 for r in (detail if any(to_num(r.get("fyer_salary_totamt")) for r in detail) else tot))
        if total:
            avg, how = total / count, "급여 총액 ÷ 직원 수"
    tenure = _weighted(detail, "avrg_cnwk_sdytrn", parse_years) or _weighted(tot, "avrg_cnwk_sdytrn", parse_years)
    return {"count": count, "avg": avg, "tenure": tenure, "avg_how": how}


def top_pay(*jos):
    """개인별 보수(5억 이상) 목록들 -> [(이름, 직위, 금액(원))] 큰 순."""
    people = {}
    for jo in jos:
        for r in dart_rows(jo, ["nm", "mendng_totamt"]):
            raw = [x.strip() for x in str(r.get("nm", "")).split("\n") if x.strip()]
            name = raw[-1] if raw else ""  # '회장\n정의선', '전) 부사장\n김동욱' -> 마지막 줄이 이름
            amt, nm = to_num(r.get("mendng_totamt")), re.sub(r"\s+", "", name)
            ofcps = re.sub(r"\s+", " ", str(r.get("ofcps", "") or "")).strip()
            if nm and amt is not None and (nm not in people or amt > people[nm][2]):
                people[nm] = (name, ofcps, amt)
    return sorted(people.values(), key=lambda p: -p[2])


def holder_stats(jo):
    """최대주주 현황 -> {name, rate(최대주주 본인 보통주 기말 %), total(특수관계인 포함 '계' 기말 %), total0(기초 %)}."""
    rows = dart_rows(jo, ["nm", "trmend_posesn_stock_qota_rt"])
    common = [r for r in rows if "보통" in str(r.get("stock_knd", ""))] or rows
    if not common:
        return None
    total = next((r for r in common if is_total(r.get("nm"))), None)
    main = next((r for r in common if "최대주주" in str(r.get("relate", "")) and not is_total(r.get("nm"))), None) or common[0]
    return {"name": str(main.get("nm", "")).strip(), "rate": to_num(main.get("trmend_posesn_stock_qota_rt")),
            "total": to_num(total.get("trmend_posesn_stock_qota_rt")) if total else None,
            "total0": to_num(total.get("bsis_posesn_stock_qota_rt")) if total else None}


def minority_stats(jo):
    rows = dart_rows(jo, ["shrholdr_co"])
    if not rows:
        return None
    r = rows[0]
    return {"count": to_num(r.get("shrholdr_co")), "rate": to_num(r.get("hold_stock_rate"))}


def dividend_stats(jo):
    """배당에 관한 사항 -> {"now": {total(원), dps(원), payout(%)}, "prev": {...}}."""
    rows = dart_rows(jo, ["se", "thstrm"])

    def find(word, common=False):
        c = [r for r in rows if word in re.sub(r"[\s()（）]", "", str(r.get("se")))]
        if common:
            c = [r for r in c if "보통" in str(r.get("stock_knd", ""))] or c
        if word == "현금배당성향":
            c = [r for r in c if "연결" in str(r.get("se"))] or c
        return c[0] if c else None

    total, dps, payout = find("현금배당금총액"), find("주당현금배당금", True), find("현금배당성향")
    out = {}
    for k, col in (("now", "thstrm"), ("prev", "frmtrm")):
        t = to_num(total.get(col)) if total else None
        out[k] = {"total": t * 1e6 if t is not None else None,  # 공시 단위: 백만원
                  "dps": to_num(dps.get(col)) if dps else None, "payout": to_num(payout.get(col)) if payout else None}
    return out


def treasury_stats(jo):
    """자기주식 취득·처분 현황 -> 보통주 {start, acq, disp, burn, end} (주)."""
    rows = dart_rows(jo, ["stock_knd", "trmend_qy"])
    common = [r for r in rows if "보통" in str(r.get("stock_knd", ""))] or rows
    key = lambda r, i: re.sub(r"\s+", "", str(r.get(f"acqs_mth{i}", "")))
    total = [r for r in common if any(w in key(r, 1) for w in ("총계", "합계"))]
    pick = total[:1] or [r for r in common if not any(w in key(r, i) for i in (1, 2, 3) for w in ("소계", "총계", "합계"))]
    if not pick:
        return None
    cols = {"start": "bsis_qy", "acq": "change_qy_acqs", "disp": "change_qy_dsps", "burn": "change_qy_incnr", "end": "trmend_qy"}
    return {k: sum(to_num(r.get(c)) or 0 for r in pick) for k, c in cols.items()}


# ------------------------------------------------------------
# DART 재무제표 (fnlttSinglAcntAll) — 부채·차입·현금, 시설투자(유형자산의 취득)
#  산업 취재 도우미 BS_ITEMS·BORROW_NAMES·pick·borrow_total을 옮김 (표준 계정 코드 먼저, 없으면 띄어쓰기 없앤 이름)
# ------------------------------------------------------------
FIN_URL = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
FIN_ITEMS = {  # key: (이름들, 표준 코드들, 재무제표)
    "liab": (["부채총계"], ["ifrs-full_Liabilities", "ifrs_Liabilities"], ("BS",)),
    "equity": (["자본총계"], ["ifrs-full_Equity", "ifrs_Equity"], ("BS",)),
    "cash": (["현금및현금성자산"], ["ifrs-full_CashAndCashEquivalents", "ifrs_CashAndCashEquivalents"], ("BS",)),
    "capex": (["유형자산의취득", "유형자산취득"], ["ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
                                       "ifrs-full_PurchaseOfPropertyPlantAndEquipment"], ("CF",)),
    "intangible": (["무형자산의취득", "무형자산취득"], ["ifrs-full_PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities"], ("CF",)),
}
INCOME_ITEMS = {  # 산업 취재 도우미 REVENUE/OPERATING/NET 이름·코드를 옮김
    "rev": (["매출액", "수익(매출액)", "영업수익", "매출", "수익", "매출액및기타수익", "매출및기타수익", "매출액(영업수익)"],
            ["ifrs-full_Revenue", "ifrs_Revenue"]),
    "op": (["영업이익", "영업이익(손실)", "영업손익", "영업손실", "영업손실(이익)"], ["dart_OperatingIncomeLoss"]),
    "net": (["당기순이익", "당기순이익(손실)", "당기순손익", "당기순손실", "당기순손실(이익)", "연결당기순이익", "분기순이익",
             "분기순이익(손실)", "분기순손실", "반기순이익", "반기순이익(손실)", "반기순손실", "당기순이익(순손실)", "분기순이익(순손실)",
             "반기순이익(순손실)", "분기순손익", "반기순손익", "연결분기순이익", "연결반기순이익", "연결당기순이익(손실)"],
            ["ifrs-full_ProfitLoss", "ifrs_ProfitLoss"]),
}
LOSS_ONLY_NAMES = {"영업손실", "당기순손실", "분기순손실", "반기순손실"}  # 이 이름이면 양수로 적혀도 손실


def income_pick(rows, key, col):
    names, ids = INCOME_ITEMS[key]
    sj = ("IS", "CIS")
    cand = [r for r in rows if str(r.get("account_id", "")).strip() in ids and r.get("sj_div") in sj]
    if not cand:
        cand = [r for r in rows if _nm(r) in names and r.get("sj_div") in sj]
    for r in cand:
        v = to_num(r.get(col))
        if v is not None:
            return -v if v > 0 and _nm(r) in LOSS_ONLY_NAMES else v
    return None


def income_stats(rows):
    """손익 -> {cum: {now, prev}, qtr: {now, prev}}. cum = 누적(사업보고서는 1년, 분기·반기는 그해 초부터),
    qtr = 그 분기 3개월(분기·반기보고서만, 사업보고서는 None). 값마다 rev·op·net(원)."""
    def get(col, alt=None):
        d = {}
        for k in INCOME_ITEMS:
            v = income_pick(rows, k, alt) if alt else None
            d[k] = v if v is not None else income_pick(rows, k, col)
        return d
    has_add = any(str(r.get("thstrm_add_amount") or "").strip() not in ("", "-") for r in rows if r.get("sj_div") in ("IS", "CIS"))
    out = {"cum": {"now": get("thstrm_amount", "thstrm_add_amount"), "prev": get("frmtrm_amount", "frmtrm_add_amount")}, "qtr": None}
    if has_add:
        out["qtr"] = {"now": get("thstrm_amount"), "prev": get("frmtrm_amount", "frmtrm_q_amount")}  # 전년 같은 분기는 frmtrm_q_amount
    return out


def signed(v, loss_word):
    """줄 이름이 이미 '순이익'일 때: 흑자면 금액만, 적자면 '순손실 810억원'."""
    return f"{loss_word} {won_text(abs(v))}" if v < 0 else won_text(v)


def pl_text(kind, v):
    """('영업', -34e9) -> '영업손실 340억원', ('영업', 5e11) -> '영업이익 5000억원', ('순', …) -> 순이익/순손실."""
    return f"{kind}{'손실' if v < 0 else '이익'} {won_text(abs(v))}"


def profit_change(now, prev):
    """이익 증감: 흑자 전환 / 적자 전환 / 적자 지속 / 적자 축소 / n% 증가·감소."""
    if now is None or prev is None:
        return None
    if prev < 0 <= now:
        return "흑자 전환"
    if now < 0 <= prev:
        return "적자 전환"
    if now < 0 and prev < 0:
        return "적자 축소" if now > prev else "적자 확대"
    return change_text(now, prev)


def mdna_reason_lines(parsed, limit=5):
    """IV. 경영진단에서 실적이 왜 변했는지 회사가 쓴 문장 (원문 줄, 계산 안 함)."""
    out = []
    for no, t in block_lines(parsed, "mdna"):
        if "|" in t or len(t) < 25:
            continue
        if re.search(r"매출|영업이익|영업손실|순이익", t) and re.search(r"증가|감소|개선|악화|하락|상승|확대|축소|전환", t):
            out.append((no, t[:240]))
            if len(out) >= limit:
                break
    return out


BORROW_NAMES = ["단기차입금", "유동성장기부채", "유동성장기차입금", "유동성사채", "유동성전환사채", "단기사채", "차입금", "유동성차입금",
                "장기차입금", "비유동차입금", "사채", "장기사채", "전환사채", "신주인수권부사채", "교환사채"]


def fetch_fin(call, cache, api_key, corp_code, year, reprt):
    """재무제표 전체 (연결 먼저, 없으면 별도). -> (행 목록, 'CFS'|'OFS') 또는 ([], None). 6시간 저장."""
    key = ("fin", corp_code, year, reprt)
    hit = cache.get(key, 6 * 3600)
    if hit is not None:
        return hit
    out = ([], None)
    for fs in ("CFS", "OFS"):
        jo = call(FIN_URL, {"crtfc_key": api_key, "corp_code": corp_code, "bsns_year": str(year), "reprt_code": reprt, "fs_div": fs})
        rows = (jo or {}).get("list") or []
        if rows:
            out = (rows, fs)
            break
    return cache.put(key, out)


def _nm(r):
    return re.sub(r"\s+", "", str(r.get("account_nm", "")))


def fin_pick(rows, key, col="thstrm_amount"):
    names, ids, sj = FIN_ITEMS[key]
    cand = [r for r in rows if str(r.get("account_id", "")).strip() in ids and r.get("sj_div") in sj]
    if not cand:
        cand = [r for r in rows if _nm(r) in names and r.get("sj_div") in sj]
    for r in cand:
        v = to_num(r.get(col))
        if v is not None:
            return abs(v) if key in ("capex", "intangible") else v
    return None


def borrow_sum(rows, col="thstrm_amount"):
    seen, total = set(), None
    for r in rows:
        if r.get("sj_div") != "BS" or _nm(r) not in BORROW_NAMES or _nm(r) in seen:
            continue
        v = to_num(r.get(col))
        if v is None:
            continue
        seen.add(_nm(r))
        total = (total or 0) + abs(v)
    return total


def fin_stats(rows):
    """재무제표 행 -> {now: {...}, prev: {...}}. 재무상태는 기말 vs 전기말, 현금흐름은 당기(누적) vs 전기 같은 기간(누적)."""
    out = {}
    for k, col in (("now", "thstrm_amount"), ("prev", "frmtrm_amount")):
        d = {key: fin_pick(rows, key, col) for key in FIN_ITEMS}
        d["borrow"] = borrow_sum(rows, col)
        d["debt_ratio"] = d["liab"] / d["equity"] * 100 if d["liab"] is not None and d["equity"] else None
        d["net_borrow"] = d["borrow"] - d["cash"] if d["borrow"] is not None and d["cash"] is not None else None
        out[k] = d
    out["income"] = income_stats(rows)
    return out


# ------------------------------------------------------------
# 원재료 매입액 (II-3 '주요 원재료' 표)
# ------------------------------------------------------------
def material_table(parsed):
    """II-3의 매입액 표 -> dict(total, unit, items=[(이름, 금액, 비중, 줄)], line_total) 또는 None.
    표 모양 (확인): 삼성전자 '부 문 | 품 목 | 구체적 용도 | 매입액 | 비중 | 주요 매입처', 소계 줄이 부문마다
                    현대차 '부문 | 구분 | 매입유형 | 주요품목 | 매입액 | 비율(%) | 비고', 맨 끝 '합 계 | 740,872 | 100.0 |'
                    에코프로비엠 '품 목 | 구체적 용도 | 매입액 | 비율 |', '합계 | 1,930,253 | 100% |'"""
    lines = block_lines(parsed, "biz_plant")
    start, unit = None, None
    for i, (no, t) in enumerate(lines):
        if "단위" in t:
            unit = unit_of(t)[0] or unit or (re.search(r"단위\s*[:：]?\s*(억원|백만원|천원|원)", t) or [None, None])[1]
        if "|" in t and "매입액" in t and start is None:
            start = i
            break
    if start is None:
        return None
    items, subtotal, total, line_total = [], [], None, None
    for no, t in lines[start + 1:]:
        if "|" not in t:
            break  # 표 끝
        c = cells(t)
        nums = [(j, to_num(x)) for j, x in enumerate(c) if to_num(x) is not None]
        if not nums:
            continue
        texts = [x for x in c[:nums[0][0]] if x and x != "-"]
        flat = re.sub(r"\s+", "", " ".join(texts))
        amount = nums[0][1]
        share = nums[1][1] if len(nums) > 1 and nums[1][1] is not None and nums[1][1] <= 100 else None
        first = re.sub(r"\s+", "", texts[0]) if texts else ""
        if any(w in flat for w in ("합계", "총계")):
            total, line_total = amount, no
        elif "소계" in flat:
            subtotal.append(amount)
        elif first == "계":
            continue  # 현대차 '계 | 부품 | …' 같은 중간 합계 줄
        elif texts and not re.fullmatch(r"기타", texts[-1]):
            items.append((" · ".join(texts[-3:]), amount, share, no))  # 공장·유형·품목 (현대차) / 부문·품목·용도 (삼성전자)
    if total is None and subtotal:
        total = sum(subtotal)
    if total is None and not items:
        return None
    items.sort(key=lambda x: -(x[1] or 0))
    return dict(total=total, unit=unit or "", items=items, line_total=line_total)


def invest_plan_lines(parsed, limit=6):
    """II-3 안의 투자 계획·실적 줄 (계산하지 않고 원문 줄만): '투자' 글이 있고 숫자가 든 표 줄과 그 바로 앞 표 머리."""
    out = []
    lines = block_lines(parsed, "biz_plant")
    for i, (no, t) in enumerate(lines):
        if "투자" in t and ("계획" in t or "실적" in t or "현황" in t) and re.search(r"\d", t):
            for no2, t2 in lines[i:i + 8]:
                if "|" in t2 and re.search(r"\d", t2):
                    out.append((no2, t2[:200]))
                if len(out) >= limit:
                    return out
    return out


def reprt_of(row):
    """보고서 행 -> (사업연도, 보고서 코드). 분기는 3월=1분기(11013), 9월=3분기(11014)."""
    import dart_client as dc
    per, kind = dc.report_period_of(row.get("report_nm")), dc.report_kind_of(row.get("report_nm"))
    if not per:
        return None, None
    if kind in REPRT:
        return per[0], REPRT[kind]
    return per[0], {3: "11013", 9: "11014"}.get(per[1], "11013")


def fetch_api(call, cache, api_key, api, corp_code, year, reprt):
    """정기보고서 주요정보 API 한 개 (V2 주소도 시도). call = dart_client.call_dart(session, url, params) 같은 함수."""
    key = ("api", api, corp_code, year, reprt)
    hit = cache.get(key, 6 * 3600)
    if hit is not None:
        return hit or None
    jo = None
    for name in API_ALIASES.get(api, [api]):
        jo = call(API_URL.format(name), {"crtfc_key": api_key, "corp_code": corp_code, "bsns_year": str(year), "reprt_code": reprt})
        if jo:
            break
    cache.put(key, jo or {})
    return jo


# ------------------------------------------------------------
# 카드 만들기
# ------------------------------------------------------------
def period_labels(period, reprt):
    """기간 이름: '2026년 1∼9월'(3분기보고서) -> 이번·작년 같은 기간·누적 제목·이번 분기(3개월) 이름.
    사업보고서 '2025년' -> 이번 '2025년', 작년 '2024년'. 기간을 모르면 '이번 기간'·'전년 같은 기간'."""
    m = re.match(r"(\d{4})년", period or "")
    y = int(m.group(1)) if m else None
    q = {"11014": "3분기(7∼9월)", "11012": "2분기(4∼6월)"}.get(reprt)
    return dict(now=period if y else "이번 기간", prev=period.replace(f"{y}년", f"{y - 1}년", 1) if y else "전년 같은 기간",
                title=(period + (" 누적" if reprt in ("11012", "11014") else "")) if y else "",
                q_now=f"{y}년 {q}" if q and y else None, q_prev=f"{y - 1}년 {q.split('(')[0]}" if q and y else "전년 같은 분기")


EMPTY = {"lines": [], "mains": {}, "blocks": {}}
FAST_KEYS = {"income", "staff", "pay", "holder", "return", "capex", "debt"}  # 원문 없이 DART 자료만으로 나오는 카드


def build_cards(parsed, prev_parsed, api, reprt="11011", fin_api=None, part="all", period=None):
    """part='fast'면 원문 없이 나오는 카드만(parsed 없어도 됨), 'doc'이면 원문 카드만, 'all'이면 모두.
    카드마다 writer.py가 같은 규칙으로 기사 문장(sentences)을 붙인다. period = '2025년'·'2026년 1∼9월' 같은 기간 표현."""
    import writer
    out = _build(parsed or EMPTY, prev_parsed, api if part != "doc" else None, reprt, fin_api if part != "doc" else None, period)
    for c in out:
        c["sentences"] = writer.sentences(c, period or "이번 기간", annual=reprt == "11011")
    if part == "fast":
        return [c for c in out if c["key"] in FAST_KEYS]
    if part == "doc":
        return [c for c in out if c["key"] not in FAST_KEYS]
    return out


def _build(parsed, prev_parsed, api, reprt="11011", fin_api=None, period=None):
    """parsed: 이번 보고서, prev_parsed: 1년 전 같은 기간 보고서(없으면 None),
    api(name) -> (이번 응답, 1년 전 응답) 를 돌려주는 함수 (없으면 None).
    fin_api() -> fin_stats 결과 + fs('CFS'|'OFS') (없으면 None).
    -> 카드 목록 (기사 빈도순)."""
    out = []
    fin = fin_api() if fin_api else None
    L = period_labels(period, reprt)

    # 0) 실적 (DART 재무제표 손익) — 기사 집계 1위 주제
    if fin and fin.get("income"):
        cum, qtr = fin["income"]["cum"], fin["income"]["qtr"]
        n, p = cum["now"], cum["prev"]
        if n["rev"] is not None or n["op"] is not None:
            margin = n["op"] / n["rev"] * 100 if n["op"] is not None and n["rev"] else None
            pmargin = p["op"] / p["rev"] * 100 if p["op"] is not None and p["rev"] else None
            rows0 = [("매출", won_text(n["rev"]) + (f" ({L['prev']} {won_text(p['rev'])}, {change_text(n['rev'], p['rev'])})" if p["rev"] else ""), None),
                     ("순이익", (signed(n["net"], "순손실") if n["net"] is not None else "-")
                      + (f" ({L['prev']} {signed(p['net'], '순손실')}, {profit_change(n['net'], p['net'])})" if p["net"] is not None and n["net"] is not None else ""), None)]
            if margin is not None:
                rows0.append(("영업이익률", f"{margin:.1f}%" + (f" ({L['prev']} {pmargin:.1f}%)" if pmargin is not None else ""), None))
            if qtr and reprt in ("11012", "11014") and (qtr["now"]["rev"] is not None or qtr["now"]["op"] is not None):
                q, qp = qtr["now"], qtr["prev"]
                rows0.append((f"{L['q_now'] or '이번 분기(3개월)'} 매출", won_text(q["rev"]) + (f" ({L['q_prev']} 대비 {change_text(q['rev'], qp['rev'])})" if qp["rev"] else ""), None))
                rows0.append((f"{L['q_now'] or '이번 분기(3개월)'} 영업이익", (signed(q["op"], "영업손실") if q["op"] is not None else "-")
                              + (f" ({L['q_prev']} 대비 {profit_change(q['op'], qp['op'])})" if qp["op"] is not None and q["op"] is not None else ""), None))
            rows0 = [r for r in rows0 if not (r[1] == "-" or r[1].startswith("- "))]  # 값 없음만 숨김 (마이너스 숫자는 남김)
            out.append(card("income", f"실적 · {L['title']}" if L["title"] else "실적", value=pl_text("영업", n["op"]) if n["op"] is not None else None,
                            prev=f"{L['prev']} {pl_text('영업', p['op'])}" if p["op"] is not None else None,
                            change=profit_change(n["op"], p["op"]), rows=rows0,
                            note="DART 재무제표 손익계산서 값이에요. 실적 변동 이유는 아래 '회사 설명' 카드(경영진단 원문 줄)를 보세요.",
                            source=f"DART 재무제표({fin.get('fs', '')}) · 손익계산서",
                            data=dict(now=n, prev=p, qtr=qtr if reprt in ("11012", "11014") else None, margin=margin, pmargin=pmargin, fs=fin.get("fs", ""),
                                      q_label=L["q_now"].split(" ", 1)[1] if L["q_now"] else "분기(3개월)")))
    reasons = mdna_reason_lines(parsed)
    if reasons:
        out.append(card("reason", "실적 변동 이유 (회사 설명, 원문 줄)", rows=[("", t, no) for no, t in reasons],
                        note="회사가 경영진단(IV)에 쓴 문장이에요. 회사의 주장이니 '회사는 ~라고 설명'으로 쓰세요.",
                        source=rp.REPORT_BLOCK_LABELS["mdna"], data=dict(quotes=[t for _, t in reasons])))

    # 1) 출자 변동
    rows, money, shares = invest_changes(parsed)
    if rows:
        lines = []
        for r in rows[:6]:
            amt = money_text(r["amount"], money)
            lines.append((f"{r['name']} — {r['kind']}", f"{amt} · 지분율 {pct_or_dash(r['rate0'])} → {pct_or_dash(r['rate1'])}", r["line"]))
        out.append(card("invest", "타법인 출자 변동", value=f"{len(rows)}곳", note="취득·처분 금액이 큰 순 (평가손익만 바뀐 곳은 뺌)",
                        rows=lines, source=f"{rp.REPORT_BLOCK_LABELS['detail_invest']} · 단위 {money or '?'}", data=dict(rows=rows, unit=money)))
    elif "detail_invest" in parsed["blocks"]:
        n = getattr(invest_changes, "seen", 0)
        raw = " ".join(t for _, t in block_lines(parsed, "detail_invest"))
        if n:
            msg = f"출자 {n}곳을 확인했는데, 이번 기간에 취득·처분한 곳은 없어요 (평가손익만 바뀐 곳은 뺐어요)."
        elif reprt in ("11013", "11014") or "생략" in raw or "|" not in raw:
            msg = "이 보고서엔 타법인출자 상세표가 실려 있지 않아요 (분기보고서는 생략하는 경우가 많아요). 반기·사업보고서에서 확인하세요."
        else:
            msg = "타법인출자 표의 모양을 읽지 못했어요. '목차별 보기 > XII. 상세표'에서 원문을 확인하세요."
        out.append(card("invest", "타법인 출자 변동", empty=msg))

    # 2) 종속회사
    names, summary = consol_list(parsed)
    if names:
        prev_names = consol_list(prev_parsed)[0] if prev_parsed else []
        rows2, note = [], None
        if summary:
            rows2.append(("보고서 설명", summary[1][:160], summary[0]))
        if prev_names:
            pn = {re.sub(r"\s+", "", n) for _, n in prev_names}
            cn = {re.sub(r"\s+", "", n) for _, n in names}
            new = [(no, n) for no, n in names if re.sub(r"\s+", "", n) not in pn]
            gone = [n for _, n in prev_names if re.sub(r"\s+", "", n) not in cn]
            for no, n in new[:5]:
                rows2.append(("새로 들어옴", n, no))
            if len(new) > 5:
                rows2.append(("새로 들어옴", f"외 {len(new) - 5}곳", None))
            if gone:
                rows2.append(("빠짐", ", ".join(gone[:5]) + (f" 외 {len(gone) - 5}곳" if len(gone) > 5 else ""), None))
            note = "회사 이름으로 1년 전 보고서 표와 대조했어요 (이름이 바뀐 회사는 들어옴·빠짐으로 함께 보일 수 있어요)."
        said = stated_count(summary)
        if said and said != len(names):
            note = (note + " " if note else "") + f"표의 행은 {len(names)}곳이에요 (보고서 문장의 숫자를 위에 적었어요)."
        out.append(card("consol", "연결 종속회사", value=f"{said or len(names)}곳", prev=f"1년 전 표 {len(prev_names)}곳" if prev_names else None,
                        change=(f"{len(names) - len(prev_names):+d}곳 (표 행 기준)" if prev_names else None), note=note, rows=rows2,
                        source=rp.REPORT_BLOCK_LABELS["detail_consol"],
                        data=dict(count=said or len(names), rows_now=len(names), rows_prev=len(prev_names) if prev_names else None,
                                  new=[n for _, n in new] if prev_names else [], gone=gone if prev_names else [])))

    if api:
        # 3) 직원
        now, prev = api("empSttus")
        e1, e0 = employee_stats(now), employee_stats(prev)
        if e1["count"]:
            rows3 = [("1인 평균 급여", f"{won_text(e1['avg'])}" + (f" (1년 전 {won_text(e0['avg'])}, {change_text(e1['avg'], e0['avg'])})" if e0['avg'] else ""), None)]
            if e1["tenure"]:
                rows3.append(("평균 근속", f"{e1['tenure']:.1f}년", None))
            out.append(card("staff", "직원", value=f"{e1['count']:,}명", prev=f"1년 전 {e0['count']:,}명" if e0["count"] else None,
                            change=change_text(e1["count"], e0["count"]), rows=rows3,
                            note=" ".join(x for x in (
                                "반기·분기 급여는 그 기간 누적이라 연봉과 바로 비교하면 안 돼요." if reprt != "11011" else "",
                                "1인 평균 급여는 보고서의 성별·부문별 1인 평균 급여액을 직원 수로 가중 평균한 값이라, 회사가 원문에 적은 전체 평균과 수십만 원 다를 수 있어요."
                                if e1.get("avg_how") == "1인 평균 급여액 가중 평균" else "") if x) or None,
                            source="DART 정기보고서 주요정보 · 직원 현황", lines=[rp.block_first_line(parsed, "staff_people")],
                            data=dict(now=e1, prev=e0)))
        # 4) 최고 보수
        a1, b1 = api("hmvAuditIndvdlBySttus")[0], api("indvdlByPay")[0]
        top = top_pay(a1, b1)
        if top:
            out.append(card("pay", "보수 5억원 이상 (상위)", value=f"{top[0][0]} {won_text(top[0][2], man=True)}",
                            rows=[(f"{n} {p}".strip(), won_text(a, man=True), None) for n, p, a in top[:5]],
                            source="DART 정기보고서 주요정보 · 개인별 보수", lines=[rp.block_first_line(parsed, "staff_pay")],
                            data=dict(top=top[:3])))
        # 5) 최대주주·소액주주
        h1, h0 = holder_stats(api("hyslrSttus")[0]), holder_stats(api("hyslrSttus")[1])
        if h1:
            rows5 = []
            if h1["rate"] is not None:
                rows5.append((f"최대주주 {h1['name']}", f"{h1['rate']}%", None))
            m1, m0 = minority_stats(api("mrhlSttus")[0]), minority_stats(api("mrhlSttus")[1])
            if m1 and m1["count"]:
                rows5.append(("소액주주", f"{m1['count']:,}명" + (f" (1년 전 {m0['count']:,}명, {change_text(m1['count'], m0['count'])})" if m0 and m0["count"] else ""), None))
            base = h1["total0"] if h1["total0"] is not None else (h0["total"] if h0 else None)
            out.append(card("holder", "최대주주·특수관계인 지분 (보통주)", value=f"{h1['total']}%" if h1["total"] is not None else "-",
                            prev=(f"기초 {base}%" if h1["total0"] is not None else f"1년 전 {base}%") if base is not None else None,
                            change=change_text(h1["total"], base, pct=False) if h1["total"] is not None and base is not None else None,
                            rows=rows5,
                            source="DART 정기보고서 주요정보 · 최대주주 현황", lines=[rp.block_first_line(parsed, "holder")],
                            data=dict(h=h1, base=base, base_kind="기초" if h1["total0"] is not None else "1년 전", m1=m1, m0=m0)))
        # 6) 자사주·배당
        t1 = treasury_stats(api("tesstkAcqsDspsSttus")[0])
        d = dividend_stats(api("alotMatter")[0])
        rows6 = []
        if t1:
            rows6 += [("자사주 취득", f"{t1['acq']:,}주", None), ("자사주 소각", f"{t1['burn']:,}주", None), ("기말 보유", f"{t1['end']:,}주", None)]
        if d["now"]["total"]:
            cmp = f" (전기 대비 {change_text(d['now']['total'], d['prev']['total'])})" if d["prev"]["total"] and reprt == "11011" else ""
            rows6.append(("현금배당 총액" if reprt == "11011" else "현금배당 총액(이번 기간)", won_text(d["now"]["total"]) + cmp, None))
        if d["now"]["dps"]:
            rows6.append(("주당 배당금(보통주)", f"{d['now']['dps']:,}원", None))
        if d["now"]["payout"] is not None:
            rows6.append(("배당성향(연결)", f"{d['now']['payout']}%", None))
        if rows6:
            out.append(card("return", "자사주·배당", value=(f"소각 {t1['burn']:,}주" if t1 and t1["burn"] else None), rows=rows6,
                            source="DART 정기보고서 주요정보 · 자기주식·배당", lines=[rp.block_first_line(parsed, "co_shares")],
                            data=dict(t=t1, d=d)))

    # 7) 가동률: '능력 | 실적 | 가동률%' 표가 있으면 공장별 계산(plant.py), 없으면 원문 줄만
    import plant
    pres = plant.compare(parsed, prev_parsed)
    main = max(pres["sets"], key=lambda x: x["now"]["cap"] if x["unit"] in ("대", "천대") else 0, default=None) if pres["sets"] else None
    hits = plant_lines(parsed) if not main else []
    if main:
        now = main["same"] or main["now"]
        ranked = sorted(main["rows"], key=lambda r: (r["diff"] is None, r["diff"] if r["diff"] is not None else 0))
        rows7 = []
        for r in ranked[:6]:
            before = f"{r['prev_rate']:.1f}% → " if r["prev_rate"] is not None else ""
            rows7.append((plant.label(r), f"{before}{r['rate']:.1f}%" + (f" ({plant.pp(r['diff'])})" if r["diff"] is not None else ""), r["line"]))
        out.append(card("plant", f"가동률 · {main['label']}" + (f" · {L['title']}" if L["title"] else ""), value=f"{now['rate']:.1f}%",
                        prev=f"{L['prev']} {main['prev']['rate']:.1f}%" if main["prev"] else None,
                        change=plant.pp(now["rate"] - main["prev"]["rate"]) if main["prev"] else None, rows=rows7,
                        note=f"{now['n']}곳 합산 = 생산실적 합 ÷ 생산능력 합 (단위 {main['unit']}). 공장별은 보고서에 적힌 가동률. 하락 폭 큰 순.",
                        source=rp.REPORT_BLOCK_LABELS["biz_plant"], data=dict(set=main)))
    if hits:
        out.append(card("plant", "가동률 (원문 줄)", rows=[("", t, no) for no, t in hits],
                        note="회사마다 표 모양이 달라 계산하지 않고 원문 줄을 그대로 보여 줘요.", source=rp.REPORT_BLOCK_LABELS["biz_plant"]))
    # 7-2) 원재료 매입액 (원문 표)
    mat = material_table(parsed)
    if mat and mat["total"]:
        pm = material_table(prev_parsed) if prev_parsed else None
        rows_m = [(name, money_text(v, mat["unit"]) + (f" · 비중 {sh:g}%" if sh is not None else ""), no) for name, v, sh, no in mat["items"][:5]]
        out.append(card("material", "원재료 매입액" + (f" · {L['title']}" if L["title"] else ""), value=money_text(mat["total"], mat["unit"]),
                        prev=f"{L['prev']} {money_text(pm['total'], pm['unit'])}" if pm and pm["total"] else None,
                        change=change_text(mat["total"], pm["total"]) if pm and pm["total"] and pm["unit"] == mat["unit"] else None,
                        rows=rows_m, lines=[mat["line_total"]] if mat["line_total"] else [],
                        note=("합계 줄이 없어 부문 소계를 더했어요. " if not mat["line_total"] else "") + "비중은 표에 적힌 값이에요(부문 안 비중일 수 있어요).", source=rp.REPORT_BLOCK_LABELS["biz_plant"] + " · 주요 원재료 표",
                        data=dict(mat=mat, prev=pm if pm and pm["total"] and pm["unit"] == mat["unit"] else None)))

    # 7-3) 시설투자: 현금흐름표 '유형자산의 취득'(DART 재무제표) — 원문 투자 계획 줄은 따로 'plan' 카드(원문 카드)
    plan = invest_plan_lines(parsed)
    if plan:
        out.append(card("plan", "투자 계획·실적 (원문 줄)", rows=[("", t, no) for no, t in plan],
                        note="원문의 투자 계획·실적 표를 그대로 보여 줘요(계산 안 함). 단위는 표 위 '단위' 줄을 확인하세요.",
                        source=rp.REPORT_BLOCK_LABELS["biz_plant"]))
    if fin:
        f1, f0 = fin["now"], fin["prev"]
        plan = []
        if f1["capex"] is not None:
            rows7 = []
            if f1["intangible"]:
                rows7.insert(0, ("무형자산 취득", won_text(f1["intangible"]) + (f" ({L['prev']} {won_text(f0['intangible'])})" if f0["intangible"] else ""), None))
            out.append(card("capex", f"시설투자 (유형자산의 취득) · {L['title']}" if L["title"] else "시설투자 (유형자산의 취득)", value=won_text(f1["capex"]) if f1["capex"] is not None else None,
                            prev=f"{L['prev']} {won_text(f0['capex'])}" if f0["capex"] else None, change=change_text(f1["capex"], f0["capex"]),
                            rows=rows7, note=("현금흐름표 금액이에요" + ("" if reprt == "11011" else " (그해 초부터 누적)") + "."),
                            source=f"DART 재무제표({fin['fs']}) · 현금흐름표", data=dict(now=f1, prev=f0)))
        # 부채·차입·현금 (은행·보험·지주 같은 금융업은 예금·보험부채 때문에 부채비율이 의미 없어 뺀다)
        financial = ("biz_fin_ops" in parsed["blocks"] and "biz_plant" not in parsed["blocks"]) or (
            f1["cash"] is None and f1["debt_ratio"] is not None and f1["debt_ratio"] > 500)  # 원문 없이도: 은행·지주는 현금 계정 없이 부채비율이 매우 높다
        if f1["liab"] is not None and f1["equity"] and not financial:
            rows_d = [("부채총계", won_text(f1["liab"]), None), ("차입금(사채 포함)", won_text(f1["borrow"]) + (f" (전기말 {won_text(f0['borrow'])})" if f0["borrow"] else ""), None),
                      ("현금및현금성자산", won_text(f1["cash"]) + (f" (전기말 {won_text(f0['cash'])})" if f0["cash"] else ""), None)]
            rows_d = [r for r in rows_d if not (r[1] == "-" or r[1].startswith("- "))]
            if f1["net_borrow"] is not None:
                rows_d.append(("순차입금(차입금-현금)", won_text(f1["net_borrow"]) if f1["net_borrow"] >= 0 else "순현금 " + won_text(-f1["net_borrow"]), None))
            out.append(card("debt", "부채비율·차입금·현금", value=f"부채비율 {f1['debt_ratio']:.1f}%",
                            prev=f"전기말 {f0['debt_ratio']:.1f}%" if f0["debt_ratio"] is not None else None,
                            change=change_text(f1["debt_ratio"], f0["debt_ratio"], pct=False) if f0["debt_ratio"] is not None else None,
                            rows=rows_d, note="부채비율 = 부채총계 ÷ 자본총계. 차입금은 단기·장기차입금과 사채 계정을 더한 값(리스부채 제외).",
                            source=f"DART 재무제표({fin['fs']}) · 재무상태표", data=dict(now=f1, prev=f0)))

    # 8) R&D
    r = rnd_ratio(parsed)
    if r:
        rows8 = []
        if "cost" in r:
            c, c0, no = r["cost"]
            if reprt == "11011":
                extra = f" (전기 {money_text(c0, r['unit'])}, {change_text(c, c0)})" if c0 else ""
            else:  # 반기·분기 표의 둘째 칸은 직전 사업연도 전체라 증감을 내지 않는다
                extra = f" (직전 사업연도 전체 {money_text(c0, r['unit'])})" if c0 else ""
            rows8.append(("연구개발비", money_text(c, r["unit"]) + extra, no))
        ratio = r.get("ratio")
        note8 = None if reprt == "11011" else "반기·분기 비율을 직전 사업연도 전체 비율과 비교한 값이에요."
        out.append(card("rnd", "연구개발비 / 매출액", note=note8, value=f"{ratio[0]}%" if ratio else None, prev=(f"전기 {ratio[1]}%" if reprt == "11011" else f"직전 사업연도 {ratio[1]}%") if ratio and ratio[1] is not None else None,
                        change=change_text(ratio[0], ratio[1], pct=False) if ratio and ratio[1] is not None else None,
                        rows=rows8, lines=[ratio[2]] if ratio else [], source=rp.REPORT_BLOCK_LABELS["biz_rnd"], data=dict(r=r)))
    # 9) 지역별 매출: 재무 주석 '지역에 대한 공시' 표 (당기·전기 같은 기간), 없으면 원문 줄
    reg = region_sales(parsed)
    if reg:
        now = dict(reg["now"])
        prev = dict(reg.get("prev") or [])
        tot = now.get("합계") or sum(v for k, v in reg["now"] if k != "합계")
        rows9 = []
        for name, v in reg["now"]:
            if name == "합계":
                continue
            share = f"비중 {v / tot * 100:.1f}%" if tot else ""
            p0 = prev.get(name)
            chg = f", {'전기' if reprt == '11011' else '1년 전 같은 기간'} 대비 {change_text(v, p0)}" if p0 else ""
            rows9.append((name, f"{money_text(v, reg['unit'])} · {share}{chg}", reg["line_now"]))
        top = max((x for x in reg["now"] if x[0] != "합계"), key=lambda x: x[1])
        out.append(card("region", "지역별 매출 (연결)", value=f"{top[0]} {top[1] / tot * 100:.1f}%" if tot else top[0],
                        rows=rows9, note="합계 " + money_text(tot, reg["unit"]) + ". 비중이 가장 큰 지역을 위에 적었어요.",
                        source="재무 주석 > 부문 정보 > 지역에 대한 공시", data=dict(reg=reg, tot=tot)))
    hits = [] if reg else find_lines(parsed, ["biz_sales", "note_segment"], r"미주|미국|북미|유럽|중국|아시아|인도|중남미|중동|아프리카|일본", limit=8)
    if not reg and len(hits) < 3:
        more = find_lines(parsed, ["biz_sales", "note_segment"], r"국내|내수|수출|해외", limit=8)
        hits += [h for h in more if h not in hits][:8 - len(hits)]
    if hits:
        out.append(card("region", "지역별 매출 (원문 줄)", rows=[("", t, no) for no, t in hits],
                        note="지역 이름이 든 줄을 찾아 보여 줘요. 비중은 원문 표로 확인하세요.", source="II-4. 매출 및 수주상황 · 부문 정보 주석"))
    return out
