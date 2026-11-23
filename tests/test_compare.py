"""여러 회사 비교 시험 (가짜 DART 응답). 실행: python tests/test_compare.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import compare as cp


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("ok -", msg)


def emp(n, total):
    return {"list": [{"fo_bbm": "전사", "sexdstn": "남", "sm": f"{n:,}", "fyer_salary_totamt": f"{total:,}", "avrg_cnwk_sdytrn": "10"}]}


DATA = {  # (회사코드, 연도, API) -> 응답
    ("A", 2025, "empSttus"): emp(1000, 158_000_000_000), ("A", 2024, "empSttus"): emp(1000, 130_000_000_000),
    ("B", 2025, "empSttus"): emp(500, 92_500_000_000), ("B", 2024, "empSttus"): emp(400, 64_000_000_000),
    ("C", 2025, "empSttus"): emp(300, 21_000_000_000),
    ("A", 2025, "hmvAuditIndvdlBySttus"): {"list": [{"nm": "회장\n홍길동", "ofcps": "회장", "mendng_totamt": "24,840,000,000"}]},
    ("A", 2025, "alotMatter"): {"list": [{"se": "현금배당금총액(백만원)", "thstrm": "1,000,000", "frmtrm": "900,000"}]},
}


def fake_fetch(api, corp_code, year, reprt):
    if corp_code == "X":
        raise RuntimeError("DART 응답 오류 [800]")
    return DATA.get((corp_code, year, api))


def test_resolve():
    corps = [{"corp_code": "00164742", "corp_name": "현대자동차", "stock_code": "005380"},
             {"corp_code": "00106641", "corp_name": "기아", "stock_code": "000270"},
             {"corp_code": "1", "corp_name": "LG에너지솔루션", "stock_code": "373220"}]
    found, missing = cp.resolve(corps, cp.split_names("현대차, 기아\nLG엔솔 · 없는회사 , 현대자동차"))
    check([c["corp_name"] for _, c in found] == ["현대자동차", "기아", "LG에너지솔루션"] and missing == ["없는회사"], "이름 풀기 (줄임말·중복·못 찾은 회사)")
    check(len(cp.INDUSTRY_GROUPS) == 16 and "현대자동차" in cp.INDUSTRY_GROUPS["자동차"], "업종 묶음")


def test_collect_and_rank():
    corps = [("a", {"corp_code": "A", "corp_name": "SK하이닉스"}), ("b", {"corp_code": "B", "corp_name": "LG에너지솔루션"}),
             ("c", {"corp_code": "C", "corp_name": "삼성전자"}), ("x", {"corp_code": "X", "corp_name": "오류회사"})]
    rows = cp.collect(fake_fetch, corps, 2025, "11011")
    by = {r["name"]: r for r in rows}
    check(by["SK하이닉스"]["pay"] == 158_000_000 and round(by["SK하이닉스"]["pay_chg"], 1) == 21.5, "1인 평균 급여·증감률")
    check(by["LG에너지솔루션"]["emp_chg"] == 25.0 and by["삼성전자"]["emp_chg"] is None, "1년 전 자료가 없으면 증감률 비움")
    check(by["SK하이닉스"]["top_pay_who"] == "홍길동 회장" and by["SK하이닉스"]["div"] == 1e12, "최고 보수·배당")
    check(by["오류회사"]["error"] and by["오류회사"].get("pay") is None, "한 회사 오류가 전체를 멈추지 않음")
    s = cp.rank_sentence(rows, "pay")
    check(s == "1인 평균 급여는 LG에너지솔루션이 1억8500만원으로 가장 많았고, SK하이닉스(1억5800만원), 삼성전자(7000만원) 순이었다.", "순위 문장 (조사 이/가, 기사체 금액)")
    one = cp.rank_sentence(rows, "top_pay")
    check(one == "최고 보수는 SK하이닉스가 248억4000만원으로 가장 많았다.", "한 곳뿐이면 짧게")
    check(cp.rank_sentence(rows, "rnd") is None, "값이 없으면 문장 없음")
    t = cp.table_rows(rows, ["emp", "pay", "div", "top_pay"])
    check(t[0]["1인 평균 급여 (만원)"] == 15800 and t[0]["현금배당 총액 (억원)"] == 10000 and t[0]["최고 보수 받은 사람"] == "홍길동 회장", "표: 만원·억원, 숫자 그대로")
    check("비고" in t[3], "오류 회사는 비고")


def test_change_sentence():
    rows = [{"name": "가", "emp_chg": -2.1}, {"name": "나", "emp_chg": 3.0}, {"name": "다", "emp_chg": -2.2}]
    check(cp.rank_sentence(rows, "emp_chg") == "직원 수 증감률은 나(+3.0%), 가(-2.1%), 다(-2.2%) 순이었다. 3곳 중 1곳이 늘었다.", "증감률은 나열 문장")
    import plant
    check(plant.josa("12.5%", "으로/로") == "12.5%로", "퍼센트 조사")


def test_four_sentence():
    rows = [{"name": n, "pay": v} for n, v in (("가", 4e8), ("나", 3e8), ("다", 2e8), ("라", 1e8))]
    check(cp.rank_sentence(rows, "pay").endswith("가장 적은 곳은 라(1억원)였다."), "4곳 이상이면 가장 적은 곳도")


def test_doc_metrics():
    import report_parse as rp
    from test_plant import NOW, report
    from test_points import SEG
    p = rp.parse_report(report(NOW))
    m = cp.doc_metrics(p)
    check(m["util_label"] == "차량부문(대수)" and abs(m["util"] - 1597600 / 1797500 * 100) < 1e-6, "가동률 합산 (주력 부문)")
    a = cp.doc_metrics(rp.parse_report(SEG))
    check(abs(a["abroad"] - (333605938 - 46641151) / 333605938 * 100) < 1e-6, "해외 매출 비중")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("모두 통과")
