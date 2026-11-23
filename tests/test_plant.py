"""공장별 가동률 시험. 표 모양은 현대차 2026 반기·삼성전자 2025 사업보고서 원문 그대로. 실행: python tests/test_plant.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import plant
import report_parse as rp


def report(rows, period="2026년 3분기 (제59기)"):
    return f"""II. 사업의 내용
3. 원재료 및 생산설비
(3) 가동률
가동률은 생산능력 대비 생산실적을 단순 역산하여 나타낸 수치입니다.
| (단위 : 대, 시간) |
사업부문 | 법인명 | 소재지 | {period} |
생산능력 | 생산실적 | 가동률(%) |
{rows}
기타부문(시간) | 현대로템 | 한국 | 1,000 | 800 | 80.0% |
4. 매출 및 수주상황
매출 | 1 |
III. 재무에 관한 사항
1. 요약재무정보
x | 1 |
"""


NOW = """차량부문(대수) | HMC | 한국 | 1,337,000 | 1,252,000 | 93.6% |
HMMA | 미국 | 270,000 | 272,700 | 101.0% |
HMGMA | 미국 | 84,500 | 35,000 | 41.4% |
HMMI | 인도네시아 | 106,000 | 37,900 | 35.8% |"""
PREV = """차량부문(대수) | HMC | 한국 | 1,365,000 | 1,388,000 | 101.7% |
HMMA | 미국 | 270,000 | 268,400 | 99.4% |
HMGMA | 미국 | 76,400 | 52,000 | 68.1% |
HMMI | 인도네시아 | 106,000 | 55,900 | 52.7% |"""


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("ok -", msg)


def test_rows():
    p = rp.parse_report(report(NOW))
    rows = plant.rate_rows(p)
    check([r["name"] for r in rows] == ["HMC", "HMMA", "HMGMA", "HMMI", "현대로템"], "가동률 표 줄 읽기 (이어지는 줄 포함)")
    check(rows[1]["group"] == "차량부문(대수)" and rows[4]["group"] == "기타부문(시간)", "사업부문 이어 붙이기")
    check(rows[2]["cap"] == 84500 and rows[2]["prod"] == 35000 and rows[2]["rate"] == 41.4 and abs(rows[2]["calc"] - 41.42) < 0.01, "능력·실적·가동률(공장별은 보고서 값, 다시 계산한 값도 둠)")
    check("HMGMA" in p["lines"][rows[2]["line"] - 1], "줄 번호")


def test_compare_and_sentences():
    res = plant.compare(rp.parse_report(report(NOW)), rp.parse_report(report(PREV, "2025년 3분기 (제58기)")))
    car = res["sets"][0]
    check(car["label"] == "차량부문(대수)" and len(car["rows"]) == 4 and len(res["sets"]) == 2, "합산은 사업부문·단위가 같은 줄끼리")
    check(abs(car["same"]["rate"] - 1597600 / 1797500 * 100) < 1e-6 and abs(car["prev"]["rate"] - 1764300 / 1817400 * 100) < 1e-6, "전체 가동률 = 실적 합 ÷ 능력 합")
    check(car["now_dom"]["n"] == 1 and car["now_abr"]["n"] == 3, "국내·해외 나누기 (소재지 한국)")
    hm = next(r for r in car["rows"] if r["name"] == "HMGMA")
    check(round(hm["diff"], 1) == -26.7, "공장별 1년 전 대비 %p")
    s = plant.sentences(car, "올해 1∼9월")
    print("\n".join("    " + x for x in s))
    check(car["unit"] == "대" and res["sets"][1]["unit"] == "시간", "단위가 '대, 시간'이면 사업부문 이름으로 고름")
    check(any(x.startswith("국내 공장 가동률은 지난해 101.7%에서 올해 93.6%로 8.1%p 하락") for x in s), "공장 하나면 보고서 값")
    check(s[0].startswith("올해 1∼9월 4개 생산거점의 전체 가동률은 88.9%로 지난해 같은 기간(97.1%)보다 8.2%p 하락했다"), "첫 문장")
    check("생산량은 176만4천대에서 159만7천대로" in s[1], "생산량 기사체")
    check(any(x.startswith("하락 폭이 가장 큰 곳은 HMGMA(미국)로 68.1%에서 41.4%로 26.7%p 하락") for x in s), "하락 폭 최대")
    check(any("반면 HMMA(미국)은 99.4%에서 101.0%로 1.6%p 상승" in x for x in s), "상승한 곳")
    check(any("가장 낮은 곳은 HMMI(인도네시아)(35.8%)" in x for x in s), "최저·최고")


def test_samsung_shape():
    text = """II. 사업의 내용
3. 원재료 및 생산설비
(가동률)
(단위 : 천대) |
부 문 | 품 목 | 제57기 |
생산능력 대수 | 실제 생산 대수 | 가동률 |
DX 부문 | TV, 모니터 등 | 56,283 | 44,361 | 78.8% |
스마트폰 등 | 270,050 | 214,259 | 79.3% |
DS 부문의 메모리 사업은 24시간 3교대 작업을 실시하고 있습니다.
(단위 : 시간) |
부 문 | 품 목 | 제57기 |
가동 가능 시간 | 실제 가동 시간 | 가동률 |
DS 부문 | 메모리 | 87,600 | 87,600 | 100% |
III. 재무에 관한 사항
1. 요약재무정보
x | 1 |
"""
    res = plant.compare(rp.parse_report(text), None)
    check([(s["label"], s["unit"], len(s["rows"])) for s in res["sets"]] == [("DX 부문", "천대", 2), ("DS 부문", "시간", 1)], "삼성: 부문·단위별 묶음")
    s = plant.sentences(res["sets"][0], "2025년")
    check("2개 품목의 전체 가동률은 79.3%다" in s[0], "1년 전 없으면 이번 값만")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("모두 통과")
