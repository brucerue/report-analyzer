"""실제 DART 보고서로 목차 나누기를 확인한다 (골든 시험). GitHub Actions에서 DART_API_KEY로 돌린다.

python tools/golden.py           -> 보고서마다 찾은 목차·블록·표 샘플을 찍고, tests/golden/expected.json이 있으면 비교
python tools/golden.py --write   -> 지금 결과를 기대값으로 저장 (사람이 확인한 뒤에만)

기대값에는 블록 이름과 '필수 낱말'만 적는다 (원문은 저장하지 않음).
"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import dart_client as dc
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
]
CORRECTION_POOL = ["삼성전자", "현대자동차", "KB금융", "에코프로비엠", "LG에너지솔루션", "SK하이닉스", "POSCO홀딩스", "한국전력공사"]
SAMPLE_BLOCKS = ["staff_people", "staff_pay", "holder", "co_shares", "detail_invest", "detail_consol", "biz_plant", "biz_sales", "biz_rnd"]


def pick(rows, kind, period):
    rows = dc.latest_versions(rows)
    for r in rows:
        if dc.report_kind_of(r.get("report_nm")) == kind and (period is None or dc.report_period_of(r.get("report_nm")) == period):
            return r
    return None


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
            results[name] = {"corp": e["corp"], "report": e.get("report", ""), "rcept_no": e["rcept_no"], **s}
            return row
        c = dc.find_corps(corps, corp_name, limit=1)
        if not c:
            problems.append(f"{name}: 회사 '{corp_name}' 못 찾음")
            return None
        rows = dc.periodic_reports(session, cache, key, c[0]["corp_code"])
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
