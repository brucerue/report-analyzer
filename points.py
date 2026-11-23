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


def won_text(v):
    """원 -> 기사체 (1조2345억원 / 7200억원 / 3억5000만원 / 1,234원)."""
    if v is None:
        return "-"
    sign, v = ("-" if v < 0 else ""), abs(v)
    jo, eok, man = int(v // 1e12), int(v % 1e12 // 1e8), int(v % 1e8 // 1e4)
    if jo:
        return f"{sign}{jo:,}조" + (f"{eok}억원" if eok else "원")
    if eok:
        return f"{sign}{eok:,}억" + (f"{man}만원" if man and eok < 100 else "원")
    if man:
        return f"{sign}{man:,}만원"
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


def card(key, title, value=None, prev=None, change=None, note=None, rows=None, source=None, lines=None, empty=None):
    return dict(key=key, title=title, value=value, prev=prev, change=change, note=note, rows=rows or [],
                source=source, lines=lines or [], empty=empty)


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
    rows, money, shares = [], None, None
    for no, t in block_lines(parsed, "detail_invest"):
        if money is None and "단위" in t:
            money, shares = unit_of(t)
        c = cells(t)
        if len(c) != 16 or c[1].replace(" ", "") not in ("상장", "비상장"):
            continue
        q0, q_chg, amt, q1 = to_num(c[5]), to_num(c[8]), to_num(c[9]), to_num(c[11])
        if not q_chg and not amt:
            continue  # 평가손익만 바뀐 것은 뺀다
        if not q0 and q1:
            kind = "신규 취득"
        elif q0 and not q1:
            kind = "전량 처분"
        elif (q_chg or 0) > 0 or (amt or 0) > 0:
            kind = "추가 취득"
        else:
            kind = "일부 처분"
        rows.append(dict(line=no, name=c[0], kind=kind, purpose=c[3], qty_change=q_chg, amount=amt,
                         rate0=c[6], rate1=c[12], book1=to_num(c[13])))
    rows.sort(key=lambda r: -abs(r["amount"] or 0))
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


def find_lines(parsed, blocks, pattern, limit=8):
    """블록들에서 pattern이 있고 숫자가 든 줄 -> [(줄 번호, 글)]."""
    out = []
    for b in blocks:
        for no, t in block_lines(parsed, b):
            if re.search(pattern, t) and re.search(r"\d", t):
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
    return str(text or "").replace(" ", "") in ("합계", "총계", "계", "전체", "소계")


def parse_years(text):
    t = str(text or "").replace(",", "").strip()
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*년?\s*(?:(\d+)\s*개월)?\s*$", t)
    return float(m.group(1)) + (int(m.group(2)) / 12 if m.group(2) else 0) if m else None


def employee_stats(jo):
    """직원 현황 -> {count, avg(1인 평균 급여, 원), tenure}. 부문·성별 표에서 합계 줄은 빼고 더한다."""
    rows = dart_rows(jo, ["sm", "fyer_salary_totamt"])
    detail = [r for r in rows if not is_total(r.get("fo_bbm")) and not is_total(r.get("sexdstn"))]
    if not detail:
        detail = [r for r in rows if not is_total(r.get("fo_bbm"))]
    if not detail:
        detail = rows
    count = sum(to_num(r.get("sm")) or 0 for r in detail)
    total = sum(to_num(r.get("fyer_salary_totamt")) or 0 for r in detail)
    out = {"count": count or None, "avg": total / count if count and total else None, "tenure": None}
    w = [(parse_years(r.get("avrg_cnwk_sdytrn")), to_num(r.get("sm")) or 0) for r in detail]
    w = [(y, n) for y, n in w if y is not None and n]
    if w:
        out["tenure"] = sum(y * n for y, n in w) / sum(n for _, n in w)
    return out


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
def build_cards(parsed, prev_parsed, api, reprt="11011"):
    """parsed: 이번 보고서, prev_parsed: 1년 전 같은 기간 보고서(없으면 None),
    api(name) -> (이번 응답, 1년 전 응답) 를 돌려주는 함수 (없으면 None).
    -> 카드 목록 (기사 빈도순)."""
    out = []

    # 1) 출자 변동
    rows, money, shares = invest_changes(parsed)
    if rows:
        lines = []
        for r in rows[:6]:
            amt = money_text(r["amount"], money)
            lines.append((f"{r['name']} — {r['kind']}", f"{amt} · 지분율 {pct_or_dash(r['rate0'])} → {pct_or_dash(r['rate1'])}", r["line"]))
        out.append(card("invest", "타법인 출자 변동", value=f"{len(rows)}곳", note="취득·처분 금액이 큰 순 (평가손익만 바뀐 곳은 뺌)",
                        rows=lines, source=f"{rp.REPORT_BLOCK_LABELS['detail_invest']} · 단위 {money or '?'}"))
    elif "detail_invest" in parsed["blocks"]:
        out.append(card("invest", "타법인 출자 변동", empty="이번 기간에 취득·처분한 출자가 없거나 표 모양을 읽지 못했어요."))

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
                        source=rp.REPORT_BLOCK_LABELS["detail_consol"]))

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
                            note="반기·분기 급여는 그 기간 누적이라 연봉과 바로 비교하면 안 돼요." if reprt != "11011" else None,
                            source="DART 정기보고서 주요정보 · 직원 현황", lines=[rp.block_first_line(parsed, "staff_people")]))
        # 4) 최고 보수
        a1, b1 = api("hmvAuditIndvdlBySttus")[0], api("indvdlByPay")[0]
        top = top_pay(a1, b1)
        if top:
            out.append(card("pay", "보수 5억원 이상 (상위)", value=f"{top[0][0]} {won_text(top[0][2])}",
                            rows=[(f"{n} {p}".strip(), won_text(a), None) for n, p, a in top[:5]],
                            source="DART 정기보고서 주요정보 · 개인별 보수", lines=[rp.block_first_line(parsed, "staff_pay")]))
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
                            source="DART 정기보고서 주요정보 · 최대주주 현황", lines=[rp.block_first_line(parsed, "holder")]))
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
                            source="DART 정기보고서 주요정보 · 자기주식·배당", lines=[rp.block_first_line(parsed, "co_shares")]))

    # 7) 가동률 (계산 안 함)
    hits = plant_lines(parsed)
    if hits:
        out.append(card("plant", "가동률 (원문 줄)", rows=[("", t, no) for no, t in hits],
                        note="회사마다 표 모양이 달라 계산하지 않고 원문 줄을 그대로 보여 줘요.", source=rp.REPORT_BLOCK_LABELS["biz_plant"]))
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
                        rows=rows8, lines=[ratio[2]] if ratio else [], source=rp.REPORT_BLOCK_LABELS["biz_rnd"]))
    # 9) 지역별 매출 (계산 안 함)
    hits = find_lines(parsed, ["biz_sales", "note_segment"], r"미주|미국|북미|유럽|중국|아시아|인도|중남미|중동|아프리카|일본", limit=8)
    if len(hits) < 3:
        more = find_lines(parsed, ["biz_sales", "note_segment"], r"국내|내수|수출|해외", limit=8)
        hits += [h for h in more if h not in hits][:8 - len(hits)]
    if hits:
        out.append(card("region", "지역별 매출 (원문 줄)", rows=[("", t, no) for no, t in hits],
                        note="지역 이름이 든 줄을 찾아 보여 줘요. 비중은 원문 표로 확인하세요.", source="II-4. 매출 및 수주상황 · 부문 정보 주석"))
    return out
