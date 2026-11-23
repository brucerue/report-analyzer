"""여러 회사 비교 (4단계): 같은 기간 보고서의 같은 지표를 회사별 한 줄로 모으고, 순위 문장을 숫자로만 만든다 (AI 없음).

기본 지표 = DART 정기보고서 주요정보 API (원문을 받지 않아 빠름): 직원·보수·최대주주·소액주주·배당·자사주.
원문 지표(선택, 회사마다 원문을 받아 느림) = R&D 비율(II-6), 가동률 합산(plant.py), 해외 매출 비중(주석 지역 공시).
계산은 points.py·plant.py와 같은 함수를 쓴다 — 카드와 비교표의 숫자가 다르지 않게.
"""
import re
from concurrent.futures import ThreadPoolExecutor

import points as pt

# 산업 취재 도우미(DART-Joongang app.py) INDUSTRY_GROUPS를 옮김 (2026.11.23)
INDUSTRY_GROUPS = {
    "자동차": ["현대자동차", "기아", "현대모비스"],
    "타이어": ["한국앤컴퍼니", "한국타이어앤테크놀로지", "금호타이어", "넥센타이어"],
    "배터리": ["LG에너지솔루션", "삼성SDI", "에스케이온", "포스코퓨처엠", "엘앤에프", "에코프로비엠", "에코프로"],
    "조선·해운": ["HD현대", "HD한국조선해양", "HD현대중공업", "한화오션", "삼성중공업", "HMM", "팬오션"],
    "방산": ["한화에어로스페이스", "한국항공우주", "LIG디펜스앤에어로스페이스", "현대로템"],
    "철강": ["POSCO홀딩스", "현대제철", "동국제강"],
    "정유·석화": ["SK이노베이션", "S-Oil", "GS칼텍스", "에이치디현대오일뱅크", "롯데케미칼", "LG화학", "한화솔루션", "금호석유화학"],
    "에너지": ["효성", "HS효성", "대한전선", "엘에스일렉트릭", "LS", "LS전선", "고려아연", "OCI", "OCI홀딩스", "HD현대일렉트릭"],
    "반도체": ["삼성전자", "SK하이닉스", "한미반도체"],
    "전자": ["삼성전자", "LG전자", "삼성전기", "LG이노텍", "삼성에스디에스", "LG디스플레이"],
    "항공": ["대한항공", "한진칼", "아시아나항공", "진에어", "제주항공", "에어부산", "트리니티항공"],
    "IT·통신": ["SK텔레콤", "KT", "LG유플러스", "NAVER", "카카오"],
    "유통": ["롯데쇼핑", "신세계", "이마트", "현대백화점", "BGF리테일", "GS리테일", "호텔신라", "CJ대한통운", "제일기획", "이노션"],
    "식품": ["CJ제일제당", "오리온", "농심", "삼양식품", "롯데웰푸드", "오뚜기", "하이트진로", "롯데칠성음료", "대상", "샘표식품"],
    "뷰티·패션": ["아모레퍼시픽", "LG생활건강", "에이피알", "코스맥스", "한국콜마", "F&F", "한섬", "LF"],
    "제약·바이오": ["삼성바이오로직스", "셀트리온", "에스케이바이오팜", "SK바이오사이언스", "유한양행", "한미약품", "알테오젠", "녹십자", "대웅제약", "종근당"],
}
# 흔히 쓰는 줄임말 -> DART 이름
ALIASES = {"현대차": "현대자동차", "LG엔솔": "LG에너지솔루션", "SK온": "에스케이온", "포스코홀딩스": "POSCO홀딩스", "에쓰오일": "S-Oil",
           "네이버": "NAVER", "KAI": "한국항공우주", "한국항공우주산업": "한국항공우주", "LIG넥스원": "LIG디펜스앤에어로스페이스",
           "HD현대오일뱅크": "에이치디현대오일뱅크", "LS일렉트릭": "엘에스일렉트릭", "SK바이오팜": "에스케이바이오팜"}
KINDS = {"사업보고서": ("11011", 12), "반기보고서": ("11012", 6), "1분기보고서": ("11013", 3), "3분기보고서": ("11014", 9)}
MAX_CORPS = 12

# 지표: key, 이름, 단위 표시, 큰 값이 '많다/높다' 중 어느 말인지, 원문 지표인지
METRICS = [
    ("rev", "매출", "원", "많", False),
    ("rev_chg", "매출 증감률", "%", "높", False),
    ("op", "영업이익", "원", "많", False),
    ("op_chg", "영업이익 증감률", "%", "높", False),
    ("op_margin", "영업이익률", "%", "높", False),
    ("emp", "직원 수", "명", "많", False),
    ("emp_chg", "직원 수 증감률", "%", "높", False),
    ("pay", "1인 평균 급여", "원", "많", False),
    ("pay_chg", "평균 급여 증감률", "%", "높", False),
    ("tenure", "평균 근속", "년", "길", False),
    ("top_pay", "최고 보수", "원", "많", False),
    ("holder", "최대주주·특수관계인 지분", "%", "높", False),
    ("minor", "소액주주 수", "명", "많", False),
    ("minor_chg", "소액주주 증감률", "%", "높", False),
    ("div", "현금배당 총액", "원", "많", False),
    ("dps", "주당 배당금(보통주)", "원", "많", False),
    ("burn", "자사주 소각", "주", "많", False),
    ("debt_ratio", "부채비율", "%", "높", False),
    ("borrow", "차입금", "원", "많", False),
    ("cash", "현금및현금성자산", "원", "많", False),
    ("capex", "시설투자(유형자산 취득)", "원", "많", False),
    ("capex_chg", "시설투자 증감률", "%", "높", False),
    ("rnd", "연구개발비/매출액", "%", "높", True),
    ("util", "가동률(주력 부문 합산)", "%", "높", True),
    ("abroad", "해외 매출 비중", "%", "높", True),
]
METRIC_BY_KEY = {m[0]: m for m in METRICS}


def resolve(corps, names):
    """입력 이름들 -> ([(입력, 기업 dict)], [못 찾은 입력]). 같은 회사는 한 번만."""
    import dart_client as dc
    found, missing, seen = [], [], set()
    for raw in names:
        q = ALIASES.get(raw.strip(), raw.strip())
        if not q:
            continue
        hit = dc.find_corps(corps, q, limit=1)
        if not hit:
            missing.append(raw.strip())
        elif hit[0]["corp_code"] not in seen:
            seen.add(hit[0]["corp_code"])
            found.append((raw.strip(), hit[0]))
    return found[:MAX_CORPS], missing


def split_names(text):
    return [x.strip() for x in re.split(r"[,\n·/]+", str(text or "")) if x.strip()]


def pct_change(now, prev):
    return (now - prev) / abs(prev) * 100 if now is not None and prev else None


def api_metrics(fetch, corp_code, year, reprt):
    """fetch(api, corp_code, year, reprt) -> 응답. -> 기본 지표 dict (없는 값은 None)."""
    get = lambda api, y=year: fetch(api, corp_code, y, reprt)
    e1, e0 = pt.employee_stats(get("empSttus")), pt.employee_stats(get("empSttus", year - 1))
    top = pt.top_pay(get("hmvAuditIndvdlBySttus"), get("indvdlByPay"))
    h = pt.holder_stats(get("hyslrSttus"))
    m1, m0 = pt.minority_stats(get("mrhlSttus")), pt.minority_stats(get("mrhlSttus", year - 1))
    d = pt.dividend_stats(get("alotMatter"))
    t = pt.treasury_stats(get("tesstkAcqsDspsSttus"))
    return {
        "emp": e1["count"], "emp_chg": pct_change(e1["count"], e0["count"]),
        "pay": e1["avg"], "pay_chg": pct_change(e1["avg"], e0["avg"]), "tenure": e1["tenure"],
        "top_pay": top[0][2] if top else None, "top_pay_who": f"{top[0][0]} {top[0][1]}".strip() if top else None,
        "holder": h["total"] if h else None,
        "minor": m1["count"] if m1 else None, "minor_chg": pct_change(m1["count"], m0["count"]) if m1 and m0 else None,
        "div": d["now"]["total"], "dps": d["now"]["dps"], "burn": t["burn"] if t else None,
    }


def doc_metrics(parsed):
    """원문에서 R&D 비율·가동률 합산·해외 매출 비중. -> dict (못 찾으면 None)."""
    import plant
    out = {"rnd": None, "util": None, "util_label": None, "abroad": None}
    r = pt.rnd_ratio(parsed)
    if r and r.get("ratio"):
        out["rnd"] = r["ratio"][0]
    res = plant.compare(parsed, None)
    main = max(res["sets"], key=lambda x: x["now"]["cap"] if x["unit"] in plant.COUNTABLE else -1, default=None)
    if main and main["now"]["rate"] is not None:
        out["util"], out["util_label"] = main["now"]["rate"], main["label"]
    reg = pt.region_sales(parsed)
    if reg:
        now = dict(reg["now"])
        tot = now.get("합계") or sum(v for k, v in reg["now"] if k != "합계")
        dom = now.get("국내")
        if tot and dom is not None:
            out["abroad"] = (tot - dom) / tot * 100
    return out


def fin_metrics(fin_fetch, corp_code, year, reprt):
    rows, fs = fin_fetch(corp_code, year, reprt)
    if not rows:
        return {}
    f = pt.fin_stats(rows)
    n, p = f["now"], f["prev"]
    inc = f["income"]["cum"]
    i1, i0 = inc["now"], inc["prev"]
    both_pos = i1["op"] is not None and i0["op"] is not None and i1["op"] > 0 and i0["op"] > 0
    return {"debt_ratio": n["debt_ratio"], "borrow": n["borrow"], "cash": n["cash"], "capex": n["capex"],
            "capex_chg": pct_change(n["capex"], p["capex"]), "fs": "연결" if fs == "CFS" else "별도",
            "rev": i1["rev"], "rev_chg": pct_change(i1["rev"], i0["rev"]), "op": i1["op"],
            "op_chg": pct_change(i1["op"], i0["op"]) if both_pos else None,  # 흑자·적자가 바뀌면 %가 뜻이 없어 비움
            "op_turn": pt.profit_change(i1["op"], i0["op"]) if not both_pos else None,
            "op_margin": i1["op"] / i1["rev"] * 100 if i1["op"] is not None and i1["rev"] else None}


def collect(fetch, corps, year, reprt, workers=6, fin_fetch=None):
    """여러 회사의 기본 지표를 동시에. corps = [(입력, 기업 dict)] -> [dict(name, corp_code, stock_code, ...지표)]."""
    def one(item):
        _, c = item
        try:
            m = api_metrics(fetch, c["corp_code"], year, reprt)
            err = None
            if fin_fetch:
                try:  # 재무제표가 안 와도 기본 지표는 남긴다
                    m.update(fin_metrics(fin_fetch, c["corp_code"], year, reprt))
                except Exception as e:
                    err = f"재무제표: {e}"
        except Exception as e:  # DART 오류 한 회사 때문에 전체가 멈추지 않게
            m, err = {}, str(e)
        return dict(name=c["corp_name"], corp_code=c["corp_code"], stock_code=c.get("stock_code", ""), error=err, **m)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, corps))


def fmt(key, v):
    """지표 값 -> 화면·문장 글자."""
    if v is None:
        return "-"
    unit = METRIC_BY_KEY[key][2]
    if unit == "원":
        return pt.won_text(v, man=key in ("pay", "top_pay"))
    if unit == "%":
        return f"{v:+.1f}%" if key.endswith("_chg") else f"{v:.1f}%"
    if unit == "년":
        return f"{v:.1f}년"
    return f"{v:,.0f}{unit}"


def _ga(name):
    """'삼성전자' -> '삼성전자가', 'SK하이닉스' -> 'SK하이닉스가', 'LG에너지솔루션' -> 'LG에너지솔루션이'."""
    import plant
    return plant.josa(name, "이/가")


def rank_sentence(rows, key, top_n=3, label=None):
    """한 지표의 순위 문장 (값이 있는 회사만, AI 없음).
    예: '1인 평균 급여는 SK하이닉스가 1억8500만원으로 가장 많았고, 삼성전자(1억5800만원), LG전자(1억1700만원) 순이었다.'"""
    import plant
    _, name, _, word, _ = METRIC_BY_KEY[key]
    have = sorted([r for r in rows if r.get(key) is not None], key=lambda r: -r[key])
    if not have:
        return None
    if key.endswith("_chg"):  # 증감률은 음수가 섞여 '가장 높았다'가 어색하다 -> 순서대로 나열
        lst = ", ".join(f"{r['name']}({fmt(key, r[key])})" for r in have)
        up = sum(1 for r in have if r[key] > 0)
        return f"{plant.josa(label or name, '은/는')} {lst} 순이었다. {len(have)}곳 중 {up}곳이 늘었다."
    first = have[0]
    v = fmt(key, first[key])
    s = f"{plant.josa(label or name, '은/는')} {_ga(first['name'])} {plant.josa(v, '으로/로')} 가장 {word}았"
    rest = [f"{r['name']}({fmt(key, r[key])})" for r in have[1:top_n]]
    s += ("고, " + ", ".join(rest) + " 순이었다.") if rest else "다."
    if len(have) > top_n:
        low = have[-1]
        least = {"많": "적은", "높": "낮은", "길": "짧은"}[word]
        s += f" 가장 {least} 곳은 {low['name']}({fmt(key, low[key])})였다."
    return s


SCALE = {"rev": (1e8, " (억원)"), "op": (1e8, " (억원)"), "pay": (1e4, " (만원)"), "top_pay": (1e4, " (만원)"), "div": (1e8, " (억원)"), "dps": (1, " (원)"),
         "borrow": (1e8, " (억원)"), "cash": (1e8, " (억원)"), "capex": (1e8, " (억원)")}


def table_rows(rows, keys):
    """화면 표용: 회사별 dict. 숫자는 숫자 그대로 둬서 표 머리를 눌러 정렬되게 (금액은 만원·억원으로 줄임)."""
    out = []
    for r in rows:
        row = {"회사": r["name"]}
        for k in keys:
            v = r.get(k)
            div, suffix = SCALE.get(k, (1, ""))
            if v is not None and div != 1:
                v = round(v / div)
            elif v is not None and isinstance(v, float):
                v = round(v, 2)
            row[METRIC_BY_KEY[k][1] + suffix] = v
        if "op_chg" in keys and r.get("op_turn"):
            row["영업이익 전환"] = r["op_turn"]
        if "top_pay" in keys:
            row["최고 보수 받은 사람"] = r.get("top_pay_who") or "-"
        if "util" in keys:
            row["가동률 부문"] = r.get("util_label") or "-"
        if r.get("error"):
            row["비고"] = "DART 오류: " + r["error"][:40]
        out.append(row)
    return out
