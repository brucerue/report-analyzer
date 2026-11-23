"""기사 포인트 카드 시험. 표 줄은 실제 보고서(삼성전자·현대차 2025~2026)의 모양 그대로. 실행: python tests/test_points.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import points as pt
import report_parse as rp

REPORT = """II. 사업의 내용
3. 원재료 및 생산설비
(단위 : 대, %) |
구 분 | 2026년 상반기 | 2025년 |
가동률 | 국내공장 | 86.2 | 94.4 |
6. 주요계약 및 연구개발활동
(2) 연구개발비용
(단위 : 백만원) |
과 목 | 2026년 상반기(제59기) | 2025년(제58기) | 2024년(제57기) | 비 고 |
연구개발비용 계 | 2,388,938 | 4,589,424 | 3,973,573 | - |
(정부보조금) | (4,519) | (2,977) | (4,708) | - |
연구개발비/매출액 비율[연구개발비용계÷당기매출액×100] | 2.5% | 2.6% | 2.4% | - |
4. 매출 및 수주상황
미주 | 1,234 | 1,000 |
III. 재무에 관한 사항
1. 요약재무정보
매출 | 1 |
XII. 상세표
1. 연결대상 종속회사 현황(상세)
당사의 연결대상 종속기업은 2025년말 현재 308개사입니다. 전년말 대비 91개 기업이 증가하고 11개 기업이 감소하였습니다.
| (단위 : 백만원) |
상호 | 설립일 | 주소 | 주요사업 | 최근사업연도말자산총액 | 지배관계 근거 | 주요종속회사 여부 |
Samsung Electronics America, Inc. (SEA) | 1978. 07 | 700 Sylvan Ave, Englewood Cliffs | 전자제품 판매 | 52,966,362 | 의결권의 과반수 소유 | O |
NEWCO{x} | 2025. 03 | Seoul | 투자 | 1,000 | 상동 | X |
3. 타법인출자 현황(상세)
☞ 본문 위치로 이동 |
(기준일 : | 2025년 12월 31일 | ) | (단위 : 백만원, 천주, %) |
법인명 | 상장여부 | 최초취득일자 | 출자목적 | 최초취득금액 | 기초잔액 | 증가(감소) | 기말잔액 | 최근사업연도재무현황 |
수량 | 지분율 | 장부가액 | 취득(처분) | 평가손익 | 수량 | 지분율 | 장부가액 | 총자산 | 당기순손익 |
삼성전기㈜ | 상장 | 1977.01.01 | 경영참여 | 250 | 17,693 | 23.7 | 445,244 | - | - | - | 17,693 | 23.7 | 445,244 | 14,594,779 | 730,990 |
삼성SDI㈜ | 상장 | 1977.01.01 | 경영참여 | 304 | 13,463 | 19.6 | 1,242,605 | 2,201 | 371,799 | - | 15,664 | 19.4 | 1,614,404 | 42,105,029 | -554,933 |
삼성중공업㈜ | 상장 | 1977.09.01 | 경영참여 | 125 | 134,027 | 15.2 | 1,514,508 | - | - | 1,715,549 | 134,027 | 15.2 | 3,230,057 | 14,948,900 | 535,800 |
삼성바이오로직스㈜ | 상장 | 2011.04.21 | 경영참여 | 30,000 | 22,217 | 31.2 | 1,595,892 | -7,767 | -185,788 | - | 14,450 | 31.2 | 1,410,104 | 11,060,742 | 1,792,237 |
삼성에피스홀딩스㈜ | 상장 | 2025.11.01 | 경영참여 | 185,788 | - | - | - | 7,767 | 185,788 | - | 7,767 | 31.2 | 185,788 | 7,709,210 | 8,332 |
"""


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("ok -", msg)


def test_numbers():
    check(pt.to_num("(4,519)") == -4519 and pt.to_num("△1,234") == -1234 and pt.to_num("2.5%") == 2.5 and pt.to_num("-") is None, "숫자 읽기")
    check(pt.won_text(371_799 * 1e6) == "3,717억원" and pt.won_text(1.6144e12) == "1조6144억원" and pt.won_text(158_000_000) == "1억5800만원", "기사체 금액")
    check(pt.unit_of("(기준일 : | 2025년 | ) | (단위 : 백만원, 천주, %) |") == ("백만원", "천주"), "단위 읽기")


def test_invest_and_consol():
    p = rp.parse_report(REPORT.replace("{x}", ""))
    rows, money, shares = pt.invest_changes(p)
    check([r["name"] for r in rows] == ["삼성SDI㈜", "삼성바이오로직스㈜", "삼성에피스홀딩스㈜"], "출자 변동: 취득·처분만, 금액 큰 순(같으면 원문 순) (평가손익만 바뀐 삼성중공업 뺌)")
    kinds = {r["name"]: r["kind"] for r in rows}
    check(kinds["삼성에피스홀딩스㈜"] == "신규 취득" and kinds["삼성바이오로직스㈜"] == "일부 처분" and kinds["삼성SDI㈜"] == "추가 취득", "변동 종류")
    check(money == "백만원" and shares == "천주", "표 단위")
    check("삼성SDI" in p["lines"][rows[0]["line"] - 1], "줄 번호가 그 행을 가리킴")
    names, summary = pt.consol_list(p)
    check(len(names) == 2 and summary and "308개사" in summary[1], "종속회사 행 세기와 요약 문장")
    prev = rp.parse_report(REPORT.replace("NEWCO{x} | 2025. 03 | Seoul | 투자 | 1,000 | 상동 | X |\n", "").replace("{x}", ""))
    cards = pt.build_cards(p, prev, None)
    c = next(c for c in cards if c["key"] == "consol")
    check(c["value"] == "2곳" and c["change"] == "+1곳" and any(r[0] == "새로 들어옴" and r[1] == "NEWCO" for r in c["rows"]), "종속회사 1년 전과 대조 (새로 들어온 회사)")


def test_rnd_plant_region():
    p = rp.parse_report(REPORT.replace("{x}", ""))
    r = pt.rnd_ratio(p)
    check(r["cost"][:2] == (2388938, 4589424) and r["ratio"][:2] == (2.5, 2.6) and r["unit"] == "백만원", "R&D 비용·비율 (당기가 앞 칸, 정부보조금 줄 무시)")
    cards = {c["key"]: c for c in pt.build_cards(p, None, None)}
    check(cards["rnd"]["value"] == "2.5%" and cards["rnd"]["change"] == "0.10%p 하락", "R&D 카드")
    check("86.2" in cards["plant"]["rows"][0][1] and cards["plant"]["rows"][0][2], "가동률 원문 줄 (계산 없이)")
    check(any("미주" in r[1] for r in cards["region"]["rows"]), "지역별 매출 원문 줄")


def test_api_cards():
    emp_now = {"list": [{"fo_bbm": "DX", "sexdstn": "남", "sm": "1,000", "fyer_salary_totamt": "158,000,000,000", "avrg_cnwk_sdytrn": "12.0"},
                        {"fo_bbm": "DX", "sexdstn": "여", "sm": "1,000", "fyer_salary_totamt": "158,000,000,000", "avrg_cnwk_sdytrn": "10.0"},
                        {"fo_bbm": "합계", "sexdstn": "", "sm": "2,000", "fyer_salary_totamt": "316,000,000,000"}]}
    emp_prev = {"list": [{"fo_bbm": "DX", "sexdstn": "남", "sm": "1,900", "fyer_salary_totamt": "247,000,000,000"}]}
    hy = {"list": [{"nm": "삼성생명보험㈜", "relate": "최대주주 본인", "stock_knd": "보통주", "bsis_posesn_stock_qota_rt": "8.51", "trmend_posesn_stock_qota_rt": "8.51"},
                   {"nm": "계", "relate": "-", "stock_knd": "보통주", "bsis_posesn_stock_qota_rt": "20.08", "trmend_posesn_stock_qota_rt": "19.92"}]}
    mr = {"list": [{"se": "소액주주", "shrholdr_co": "4,240,000", "hold_stock_rate": "70.1"}]}
    mr0 = {"list": [{"se": "소액주주", "shrholdr_co": "4,000,000", "hold_stock_rate": "70.0"}]}
    pay = {"list": [{"nm": "이원진", "ofcps": "사장", "mendng_totamt": "7,305,000,000"}, {"nm": "노 태문", "ofcps": "사장", "mendng_totamt": "6,125,000,000"}]}
    ts = {"list": [{"stock_knd": "보통주", "acqs_mth1": "총계", "bsis_qy": "0", "change_qy_acqs": "100", "change_qy_dsps": "0", "change_qy_incnr": "50", "trmend_qy": "50"}]}
    al = {"list": [{"se": "현금배당금총액(백만원)", "thstrm": "11,000,000", "frmtrm": "9,800,000"},
                   {"se": "주당 현금배당금(원)", "stock_knd": "보통주", "thstrm": "1,668", "frmtrm": "1,446"},
                   {"se": "(연결)현금배당성향(%)", "thstrm": "33.0", "frmtrm": "29.0"}]}
    data = {"empSttus": (emp_now, emp_prev), "hyslrSttus": (hy, None), "mrhlSttus": (mr, mr0), "hmvAuditIndvdlBySttus": (pay, None),
            "indvdlByPay": (None, None), "tesstkAcqsDspsSttus": (ts, None), "alotMatter": (al, None)}
    p = rp.parse_report(REPORT.replace("{x}", ""))
    cards = {c["key"]: c for c in pt.build_cards(p, None, lambda n: data.get(n, (None, None)))}
    check(cards["staff"]["value"] == "2,000명" and cards["staff"]["change"] == "5.3% 증가", "직원 수 (합계 줄 빼고 더함)")
    check("1억5800만원" in cards["staff"]["rows"][0][1] and "1억3000만원" in cards["staff"]["rows"][0][1], "1인 평균 급여와 1년 전")
    check(cards["pay"]["value"] == "이원진 73억500만원".replace("73억500만원", pt.won_text(7_305_000_000)), "최고 보수")
    check(cards["holder"]["value"] == "19.92%" and cards["holder"]["change"] == "0.16%p 하락", "최대주주 지분 (기초 대비)")
    check(any("4,240,000명" in r[1] and "6.0% 증가" in r[1] for r in cards["holder"]["rows"]), "소액주주 수 변화")
    check(any(r[0] == "현금배당 총액" and "11조원" in r[1] for r in cards["return"]["rows"]) and cards["return"]["value"] == "소각 50주", "자사주·배당")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("모두 통과")
