"""업종별 골든 점검: 여러 업종 대표 회사의 최근 정기보고서로 카드·기사 문장·기사 초안을 앱과 같은 방식으로 만들어 찍고,
이상해 보이는 값(빈 카드, 'None' 글자, 너무 큰 부채비율·가동률 등)을 '점검' 줄로 표시한다. 기대값 비교는 하지 않는다.

python tools/sweep.py 1        -> 묶음 1 (GROUPS 참고), 'all'이면 전부
환경변수 DART_API_KEY 필요 (GitHub Actions 'sweep'에서 돌림, 공개 저장소라 무료). 공개 보고서 숫자만 찍는다.
"""
import os
import re
import sys
import time

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import article as art
import dart_client as dc
import plant
import points as pt
import report_parse as rp

# 묶음: [(업종, 회사)] — 한 묶음씩 따로 돌려 시간 제한 안에
GROUPS = {
    "1": [("반도체", "SK하이닉스"), ("디스플레이", "LG디스플레이"), ("2차전지", "LG에너지솔루션"), ("화학", "LG화학"), ("정유", "S-Oil")],
    "2": [("철강", "현대제철"), ("조선", "HD현대중공업"), ("건설", "현대건설"), ("자동차부품", "현대모비스"), ("방산", "한화에어로스페이스")],
    "3": [("항공", "대한항공"), ("해운", "HMM"), ("통신", "SK텔레콤"), ("유통", "이마트"), ("식품", "CJ제일제당")],
    "4": [("바이오", "삼성바이오로직스"), ("제약", "유한양행"), ("게임", "엔씨소프트"), ("인터넷", "NAVER"), ("전력", "한국전력공사")],
    "5": [("보험", "삼성화재"), ("증권", "미래에셋증권"), ("기계·에너지", "두산에너빌리티"), ("코스닥 장비", "리노공업"), ("코스닥 화장품", "에이피알")],
}


def period_phrase(r):  # app.py와 같은 규칙
    per, kind = dc.report_period_of(r.get("report_nm")), dc.report_kind_of(r.get("report_nm"))
    if not per:
        return "이번 기간"
    y, m = per
    if "사업" in kind:
        return f"{y}년"
    return {6: f"{y}년 상반기", 3: f"{y}년 1분기", 9: f"{y}년 1∼9월"}.get(m, f"{y}년 {m}월까지")


def checks(cards, is_fin):
    """이상해 보이는 곳 -> [문장]."""
    out = []
    for c in cards:
        txt = " ".join([str(c.get("title")), str(c.get("value")), str(c.get("prev")), str(c.get("change"))]
                       + [f"{a} {b}" for a, b, _ in c["rows"]] + c.get("sentences", []))
        if re.search(r"None|nan|\{|\}", txt):
            out.append(f"[{c['key']}] 'None/nan/괄호' 글자: {txt[:160]}")
        if c.get("value") and not c.get("sentences") and c["key"] not in ("plan", "consol") and not c.get("empty"):
            out.append(f"[{c['key']}] 값은 있는데 기사 문장이 없음")
        d = c.get("data") or {}
        if c["key"] == "debt" and d.get("now", {}).get("debt_ratio") and d["now"]["debt_ratio"] > 800 and not is_fin:
            out.append(f"[debt] 부채비율 {d['now']['debt_ratio']:.0f}% (확인 필요)")
        if c["key"] == "staff" and d.get("now") and not (10 <= (d["now"].get("count") or 0) <= 300000):
            out.append(f"[staff] 직원 수 {d['now'].get('count')} (확인 필요)")
        if c["key"] == "staff" and d.get("now") and d["now"].get("avg") and not (2e7 <= d["now"]["avg"] <= 3e8):
            out.append(f"[staff] 평균 급여 {d['now']['avg']:,.0f}원 (확인 필요)")
        if c["key"] == "rnd" and c.get("value"):
            v = pt.to_num(str(c["value"]).rstrip("%"))
            if v is not None and v > 60:
                out.append(f"[rnd] R&D 비율 {v}% (확인 필요)")
        if c["key"] == "plant":
            for s in (d.get("set") or {}).get("rows", []):
                if s.get("rate") and s["rate"] > 150:
                    out.append(f"[plant] 가동률 {s['rate']}% {plant.label(s)} (확인 필요)")
        if c["key"] == "income" and d.get("now") and d["now"].get("rev") is None:
            out.append("[income] 매출 없음")
        if c["key"] == "region" and d.get("tot"):
            share = sum(v for k, v in d["reg"]["now"] if k != "합계") / d["tot"] * 100
            if not 95 <= share <= 105:
                out.append(f"[region] 지역 합이 합계의 {share:.0f}% (확인 필요)")
    return out


def one(session, cache, key, corps, sector, name):
    c = dc.find_corps(corps, name, limit=1)
    if not c:
        print(f"\n######## [{sector}] {name}: 회사 못 찾음")
        return [f"{sector} {name}: 회사 못 찾음"]
    corp = c[0]
    rows = dc.latest_versions(dc.periodic_reports(session, cache, key, corp["corp_code"]))
    if not rows:
        return [f"{sector} {name}: 보고서 없음"]
    row = rows[0]  # 가장 최근 정기보고서 (앱 기본값과 같음)
    year, reprt = pt.reprt_of(row)
    period = period_phrase(row)
    print(f"\n######## [{sector}] {corp['corp_name']} {row.get('report_nm')} ({row.get('rcept_no')}, {period})")
    t0 = time.time()
    try:
        parsed = rp.parse_report(dc.report_text(session, cache, key, str(row["rcept_no"])))
    except (dc.DartApiError, rp.ParseError) as e:
        print("  원문 실패:", e)
        parsed = None
    prev_row = dc.find_prev_periodic(rows, row)
    prev_parsed = None
    if prev_row and parsed:
        try:
            prev_parsed = rp.parse_report(dc.report_text(session, cache, key, str(prev_row["rcept_no"])))
        except (dc.DartApiError, rp.ParseError) as e:
            print("  1년 전 원문 실패:", e)
    print(f"  원문 {len(parsed['lines']) if parsed else 0:,}줄 · 1년 전 {prev_row.get('report_nm') if prev_row else '없음'} · {time.time() - t0:.0f}초")
    if parsed:
        missing = [k for k in ("biz_sales", "biz_plant", "biz_rnd", "staff_people", "holder", "detail_invest", "detail_consol", "mdna") if k not in parsed["blocks"]]
        print("  못 찾은 주요 블록:", ", ".join(missing) or "없음")

    call = lambda url, params: dc.call_dart(session, url, params)
    memo = {}

    def api(n):
        if n not in memo:
            memo[n] = (pt.fetch_api(call, cache, key, n, corp["corp_code"], year, reprt),
                       pt.fetch_api(call, cache, key, n, corp["corp_code"], year - 1, reprt))
        return memo[n]

    def fin_api():
        if "fin" not in memo:
            frows, fs = pt.fetch_fin(call, cache, key, corp["corp_code"], year, reprt)
            out = dict(pt.fin_stats(frows), fs="연결" if fs == "CFS" else "별도") if frows else None
            if out and reprt in ("11012", "11013", "11014"):
                out["prevq"] = pt.prev_quarter(lambda y, r: pt.fetch_fin(call, cache, key, corp["corp_code"], y, r)[0], year, reprt)
            memo["fin"] = out
        return memo["fin"]

    cards = pt.build_cards(parsed, prev_parsed, api, reprt, fin_api, period=period)
    for cd in cards:
        if cd.get("empty"):
            print(f"  [{cd['title']}] (없음) {cd['empty'][:90]}")
            continue
        print(f"  [{cd['title']}] {cd['value'] or ''} | 비교 {cd['prev'] or '-'} | {cd['change'] or '-'}")
        for label, text, line in cd["rows"][:5]:
            print(f"      {label} : {text[:130]}" + (f" (줄 {line})" if line else ""))
        for s in cd.get("sentences", []):
            print(f"      > {s}")
    ch = art.choices(cards)
    if ch:
        keys = [k for k, _ in ch]
        lead = "income" if "income" in keys else keys[0]
        d = art.compose(cards, keys[:5], lead, corp["corp_name"], dc.strip_correction(row.get("report_nm")), str(row.get("rcept_dt", "")))
        print("  --- 기사 초안 (요소 앞 5개, 리드 실적) ---")
        print("  제목:", d["title"])
        for p in d["paragraphs"]:
            print("   ", p)
    is_fin = bool(parsed and any(k.startswith("biz_fin") for k in parsed["blocks"]))
    found = checks(cards, is_fin)
    for f in found:
        print("  !! 점검:", f)
    return [f"{sector} {corp['corp_name']}: {f}" for f in found]


def main():
    key = os.environ.get("DART_API_KEY")
    if not key:
        sys.exit("DART_API_KEY가 없어요 (GitHub Secrets).")
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    todo = [x for g, xs in GROUPS.items() if which in ("all", g) for x in xs]
    session, cache = requests.Session(), dc.Cache()
    corps = dc.load_corp_list(session)
    problems = []
    for sector, name in todo:
        try:
            problems += one(session, cache, key, corps, sector, name)
        except Exception as e:  # 한 회사가 터져도 나머지는 계속
            import traceback
            traceback.print_exc()
            problems.append(f"{sector} {name}: 오류 {type(e).__name__}: {e}")
        time.sleep(1)
    print("\n==================== 점검 요약 ====================")
    print("\n".join(problems) or "이상 없음")


if __name__ == "__main__":
    main()
