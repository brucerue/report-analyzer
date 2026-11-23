"""실제 DART 보고서로 목차 나누기를 확인한다 (골든 시험). GitHub Actions에서 DART_API_KEY로 돌린다.

python tools/golden.py           -> 보고서마다 찾은 목차·블록·표 샘플을 찍고, tests/golden/expected.json이 있으면 비교
python tools/golden.py --write   -> 지금 결과를 기대값으로 저장 (사람이 확인한 뒤에만)

기대값에는 블록 이름과 '필수 낱말'만 적는다 (원문은 저장하지 않음).
"""
import json
import re
import os
import sys
import time

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import dart_client as dc
import plant
import points as pt
import report_parse as rp

HERE = os.path.dirname(os.path.abspath(__file__))
EXPECTED = os.path.join(HERE, "..", "tests", "golden", "expected.json")
# 이름: (회사, 보고서 종류, 기간) — 기간이 None이면 가장 최근
CASES = [
    ("대기업", "삼성전자", "사업보고서", None),
    ("금융업", "KB금융", "사업보고서", None),
    ("코스닥", "에코프로비엠", "사업보고서", None),
    ("반기", "현대자동차", "반기보고서", None),
    ("분기", "현대자동차", "분기보고서", (2026, 9)),  # 2026.11.17 연합뉴스 '현대차 공장 가동률 94→86%' 기사가 쓴 보고서
]
CORRECTION_POOL = ["삼성전자", "현대자동차", "KB금융", "에코프로비엠", "LG에너지솔루션", "SK하이닉스", "POSCO홀딩스", "한국전력공사"]
SAMPLE_BLOCKS = ["staff_people", "staff_pay", "holder", "co_shares", "detail_invest", "detail_consol", "biz_plant", "biz_sales", "biz_rnd"]


def pick(rows, kind, period):
    rows = dc.latest_versions(rows)
    for r in rows:
        if dc.report_kind_of(r.get("report_nm")) == kind and (period is None or dc.report_period_of(r.get("report_nm")) == period):
            return r
    return None


def probe(parsed):
    """카드 개선용: 부분별 원문 맛보기 (공개 보고서 원문이라 로그에 남겨도 됨)."""
    def dump(title, block, pat, after=8, limit=40):
        lines = pt.block_lines(parsed, block)
        out, used = [], set()
        for i, (no, t) in enumerate(lines):
            if re.search(pat, t):
                for no2, t2 in lines[max(0, i - 1):i + after]:
                    if no2 not in used:
                        used.add(no2)
                        out.append(f"      {no2}: {t2[:200]}")
            if len(out) >= limit:
                break
        print(f"--- 맛보기 {title} ({block}) ---")
        print("\n".join(out[:limit]) or "      (없음)")
    dump("가동률", "biz_plant", r"가동률", after=10, limit=45)
    dump("원재료 매입", "biz_plant", r"매입|원재료", after=3, limit=20)
    dump("시설투자", "biz_plant", r"투자", after=6, limit=25)
    dump("지역", "biz_sales", r"지역|미주|미국|북미|유럽|중국|아시아", after=6, limit=30)
    dump("부문 정보 지역", "note_segment", r"지역|미주|미국|북미|유럽|중국|아시아", after=6, limit=25)
    from collections import Counter
    rows = [(no, pt.cells(t)) for no, t in pt.block_lines(parsed, "detail_invest") if "|" in t]
    print("--- 맛보기 출자 표 칸 수 ---")
    print("      " + str(Counter(len(c) for _, c in rows).most_common(8)))
    moved = [(no, c) for no, c in rows if len(c) >= 12 and any(x not in ("-", "", "0") for x in c[8:11])]
    print(f"--- 맛보기 출자 표 증감 칸이 빈칸 아닌 행 ({len(moved)}개 중 앞 10개) ---")
    for no, c in moved[:10]:
        print(f"      {no}: [{len(c)}칸] " + " | ".join(c)[:220])


def show_plant(parsed, row, rows_all, session, cache, key):
    prev = dc.find_prev_periodic(dc.latest_versions(rows_all), row) if rows_all else None
    prev_parsed = rp.parse_report(dc.report_text(session, cache, key, str(prev["rcept_no"]))) if prev else None
    res = plant.compare(parsed, prev_parsed)
    print(f"--- 공장별 가동률 (비교: {prev.get('report_nm') if prev else '없음'}) ---")
    for one in res["sets"]:
        print(f"  [{one['label']} · {one['unit']}] 합산 {plant.pct((one['same'] or one['now'])['rate'])} / 1년 전 {plant.pct(one['prev']['rate']) if one['prev'] else '-'}")
        for r in one["rows"]:
            print(f"      {plant.label(r)}: 능력 {r['cap']:,} 실적 {r['prod']:,} 가동률 {plant.pct(r['rate'])} (다시 계산 {plant.pct(r['calc'])}) 1년 전 {plant.pct(r['prev_rate'])} {plant.pp(r['diff'])} (줄 {r['line']})")
        for line in plant.sentences(one, "올해"):
            print("      >", line)


def show_cards(parsed, corp_code, row, session, cache, key):
    year, reprt = pt.reprt_of(row)
    memo = {}

    def api(name):
        if name not in memo:
            call = lambda url, params: dc.call_dart(session, url, params)
            memo[name] = (pt.fetch_api(call, cache, key, name, corp_code, year, reprt),
                          pt.fetch_api(call, cache, key, name, corp_code, year - 1, reprt))
        return memo[name]

    print("--- 기사 포인트 카드 ---")
    for c in pt.build_cards(parsed, None, api if year and corp_code else None, reprt or "11011"):
        head = f"  [{c['title']}] {c['value'] or ''} | 비교 {c['prev'] or '-'} | {c['change'] or '-'}"
        print(head if not c.get("empty") else f"  [{c['title']}] (없음) {c['empty']}")
        for label, text, line in c["rows"][:6]:
            print(f"      {label} : {text[:120]} (줄 {line})")


def summarize(parsed):
    lines = parsed["lines"]
    mains = {k: [i + 1, j] for k, (i, j) in parsed["mains"].items()}
    blocks = {k: {"start": rp.block_first_line(parsed, k), "chars": len(rp.block_text(parsed, k, numbered=False, cap=10 ** 7))}
              for k in parsed["blocks"]}
    return {"lines": len(lines), "mains": mains, "blocks": blocks}


def show(name, row, parsed, summary):
    print(f"\n==================== [{name}] {row.get('corp_name')} {row.get('report_nm')} ({row.get('rcept_no')}) ====================")
    print(f"원문 {summary['lines']:,}줄")
    print("대분류:", ", ".join(f"{k}({a}~{b})" for k, (a, b) in sorted(summary["mains"].items(), key=lambda x: x[1][0])))
    print("블록:", ", ".join(f"{k}@{v['start']}:{v['chars']:,}자" for k, v in summary["blocks"].items()))
    missing = [k for k in rp.REPORT_BLOCK_LABELS if k not in summary["blocks"]]
    print("못 찾은 블록:", ", ".join(missing) or "없음")
    # 소제목 후보: 대분류 안의 '1. ~' 줄 중 우리가 모르는 제목 (목차가 다른 회사 찾기용)
    for mk, (i, j) in parsed["mains"].items():
        known = rp.REPORT_SUB_SECTIONS.get(mk, [])
        heads = []
        for k in range(i + 1, j):
            s = parsed["lines"][k].strip()
            if rp.is_heading_line(s) and rp.re.match(r"^\d{1,2}\s*\.\s*\S", s) and len(s) < 40:
                if not any(rp.re.match(p, rp.re.sub(r"^\d{1,2}\s*\.\s*(?:\([^)]{1,12}\))?\s*", "", s)) for _, p in known):
                    heads.append(f"{k + 1}:{s}")
        if heads and mk not in ("fin", "detail"):
            print(f"  {mk} 안의 모르는 소제목: " + " / ".join(heads[:12]))
    for b in SAMPLE_BLOCKS:
        if b in parsed["blocks"]:
            text = rp.block_text(parsed, b, numbered=True, cap=10 ** 7).split("\n")
            print(f"--- 샘플 {b} (앞 15줄) ---")
            for line in text[:15]:
                print("   ", line[:180])


def main():
    key = os.environ.get("DART_API_KEY")
    if not key:
        sys.exit("DART_API_KEY가 없어요 (GitHub Secrets).")
    session, cache = requests.Session(), dc.Cache()
    corps = dc.load_corp_list(session)
    results, problems = {}, []

    fixed = json.load(open(EXPECTED, encoding="utf-8")) if os.path.exists(EXPECTED) and "--write" not in sys.argv else {}

    def run(name, corp_name, kind, period, need_correction=False):
        if name in fixed:  # 기대값이 있으면 그때 확인한 바로 그 보고서(접수번호)로 다시 본다
            e = fixed[name]
            row = {"rcept_no": e["rcept_no"], "report_nm": e.get("report", ""), "corp_name": e["corp"]}
            try:
                parsed = rp.parse_report(dc.report_text(session, cache, key, e["rcept_no"]))
            except (dc.DartApiError, rp.ParseError) as err:
                problems.append(f"{name}: {err}")
                return None
            s = summarize(parsed)
            show(name, row, parsed, s)
            c = dc.find_corps(corps, e["corp"], limit=1)
            show_cards(parsed, c[0]["corp_code"] if c else None, row, session, cache, key)
            if c:
                show_plant(parsed, row, dc.periodic_reports(session, cache, key, c[0]["corp_code"]), session, cache, key)
            if "--probe" in sys.argv:
                probe(parsed)
            results[name] = {"corp": e["corp"], "report": e.get("report", ""), "rcept_no": e["rcept_no"], **s}
            return row
        c = dc.find_corps(corps, corp_name, limit=1)
        if not c:
            problems.append(f"{name}: 회사 '{corp_name}' 못 찾음")
            return None
        rows = dc.periodic_reports(session, cache, key, c[0]["corp_code"])
        all_rows = rows
        if need_correction:
            rows = [r for r in dc.latest_versions(rows) if r.get("versions", 1) > 1]
        row = pick(rows, kind, period) if not need_correction else (rows[0] if rows else None)
        if not row:
            return None
        row = dict(row, corp_name=c[0]["corp_name"])
        try:
            parsed = rp.parse_report(dc.report_text(session, cache, key, str(row["rcept_no"])))
        except (dc.DartApiError, rp.ParseError) as e:
            problems.append(f"{name}: {e}")
            return None
        s = summarize(parsed)
        show(name, row, parsed, s)
        show_cards(parsed, c[0]["corp_code"], row, session, cache, key)
        show_plant(parsed, row, all_rows, session, cache, key)
        results[name] = {"corp": c[0]["corp_name"], "report": row.get("report_nm"), "rcept_no": row.get("rcept_no"), **s}
        time.sleep(1)
        return row

    for name, corp, kind, period in CASES:
        if not run(name, corp, kind, period):
            problems.append(f"{name}: {corp} {kind} 없음")
    for corp in ([None] if "정정본" in fixed else CORRECTION_POOL):
        if run("정정본", corp, None, None, need_correction=True):
            break
    else:
        problems.append("정정본: 후보 회사들에서 정정 보고서를 못 찾음")

    print("\n==================== 여러 회사 비교 (반도체·전자 2025 사업보고서) ====================")
    import compare as cp
    found, missing = cp.resolve(corps, ["삼성전자", "SK하이닉스", "LG전자", "삼성전기"])
    call = lambda url, params: dc.call_dart(session, url, params)
    fetch = lambda api, code, y, r: pt.fetch_api(call, cache, key, api, code, y, r)
    for _, c in found[:2]:  # 직원 현황 원자료 (합계 줄 모양 확인용)
        jo = fetch("empSttus", c["corp_code"], 2025, "11011")
        print("  empSttus", c["corp_name"])
        for r in pt.dart_rows(jo, ["sm"])[:30]:
            print("     ", {k: r.get(k) for k in ("fo_bbm", "sexdstn", "rgllbr_co", "cnttk_co", "sm", "avrg_cnwk_sdytrn", "fyer_salary_totamt", "jan_salary_am")})
    rows = cp.collect(fetch, found, 2025, "11011")
    for r in rows:
        print("  ", r["name"], {k: cp.fmt(k, r.get(k)) for k in ("emp", "emp_chg", "pay", "pay_chg", "top_pay", "holder", "minor", "div")}, r.get("top_pay_who"), r.get("error") or "")
    for k in ("pay", "emp_chg", "top_pay", "div"):
        print("   >", cp.rank_sentence(rows, k))

    print("\n==================== 요약 ====================")
    for name, r in results.items():
        print(f"{name}: {r['corp']} {r['report']} 대분류 {len(r['mains'])}개, 블록 {len(r['blocks'])}개")
    for p in problems:
        print("문제:", p)

    exp = {n: {"corp": r["corp"], "report": r["report"], "rcept_no": r["rcept_no"], "mains": sorted(r["mains"]), "blocks": sorted(r["blocks"])} for n, r in results.items()}
    print("\n기대값 후보(JSON):")
    print(json.dumps(exp, ensure_ascii=False))
    if "--write" in sys.argv:
        os.makedirs(os.path.dirname(EXPECTED), exist_ok=True)
        with open(EXPECTED, "w", encoding="utf-8") as f:
            json.dump(exp, f, ensure_ascii=False, indent=1)
        print("기대값 저장:", EXPECTED)
        return
    if os.path.exists(EXPECTED):
        exp = json.load(open(EXPECTED, encoding="utf-8"))
        fails = []
        for n, e in exp.items():
            r = results.get(n)
            if not r:
                fails.append(f"{n}: 결과 없음")
                continue
            for k in set(e["mains"]) - set(r["mains"]):
                fails.append(f"{n}: 대분류 {k} 사라짐")
            for k in set(e["blocks"]) - set(r["blocks"]):
                fails.append(f"{n}: 블록 {k} 사라짐")
        print("\n골든 비교:", "통과" if not fails else "실패")
        for f in fails:
            print("  ", f)
        if fails:
            sys.exit(1)


if __name__ == "__main__":
    main()
