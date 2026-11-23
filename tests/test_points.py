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
(3) 가동률
공장 | 2026년 상반기 | 2025년 |
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
한국항공우주산업 | 상장 | 2000.02.16 | 단순투자 | 151,086 | - | - | 153,522 | - | -264,806 | 111,284 | - | - | - | 5,866,555 | 53,040 |
SVIC 33호 신기술투자조합 | 비상장 | 2016.11.11 | 경영참여 | 4,950 | 1 | 99.0 | 112,524 | -1 | -79,982 | - | 0 | 99.0 | 32,542 | 190,421 | -9,040 |
"""


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("ok -", msg)


def test_numbers():
    check(pt.to_num("(4,519)") == -4519 and pt.to_num("△1,234") == -1234 and pt.to_num("2.5%") == 2.5 and pt.to_num("-") is None, "숫자 읽기")
    check(pt.won_text(371_799 * 1e6) == "3718억원" and pt.won_text(70_000_000) == "7000만원" and pt.won_text(133_274_793 * 1e6) == "133조2748억원" and pt.won_text(1.6144e12) == "1조6144억원" and pt.won_text(158_000_000) == "1억5800만원" and pt.won_text(24_840_000_000, man=True) == "248억4000만원" and pt.won_text(24_840_000_000) == "248억원", "기사체 금액 (보수는 만원까지)")
    check(pt.unit_of("(기준일 : | 2025년 | ) | (단위 : 백만원, 천주, %) |") == ("백만원", "천주"), "단위 읽기")


def test_invest_and_consol():
    p = rp.parse_report(REPORT.replace("{x}", ""))
    rows, money, shares = pt.invest_changes(p)
    check([r["name"] for r in rows][:4] == ["삼성SDI㈜", "한국항공우주산업", "삼성바이오로직스㈜", "삼성에피스홀딩스㈜"], "출자 변동: 취득·처분만, 금액 큰 순(같으면 원문 순) (평가손익만 바뀐 삼성중공업 뺌)")
    kinds = {r["name"]: r["kind"] for r in rows}
    check(kinds["한국항공우주산업"] == "전량 처분" and kinds["SVIC 33호 신기술투자조합"] == "일부 처분", "수량 칸이 '-'·0이어도 장부가로 전량/일부 처분 판단")
    check(kinds["삼성에피스홀딩스㈜"] == "신규 취득" and kinds["삼성바이오로직스㈜"] == "일부 처분" and kinds["삼성SDI㈜"] == "추가 취득", "변동 종류")
    check(money == "백만원" and shares == "천주", "표 단위")
    check("삼성SDI" in p["lines"][rows[0]["line"] - 1], "줄 번호가 그 행을 가리킴")
    names, summary = pt.consol_list(p)
    check(len(names) == 2 and summary and "308개사" in summary[1] and pt.stated_count(summary) == 308, "종속회사 행 세기(첫 표만)와 문장 속 숫자")
    prev = rp.parse_report(REPORT.replace("NEWCO{x} | 2025. 03 | Seoul | 투자 | 1,000 | 상동 | X |\n", "").replace("{x}", ""))
    cards = pt.build_cards(p, prev, None)
    c = next(c for c in cards if c["key"] == "consol")
    check(c["value"] == "308곳" and c["change"] == "+1곳 (표 행 기준)" and "표의 행은 2곳" in c["note"] and any(r[0] == "새로 들어옴" and r[1] == "NEWCO" for r in c["rows"]), "종속회사 1년 전과 대조 (새로 들어온 회사)")


def test_invest_none():
    text = REPORT.replace("{x}", "").split("삼성전기㈜")[0] + "국민은행 | 비상장 | 2008.09.29 | 설립시 주식이전 | 12,227,020 | 404,379,116 | 100 | 14,821,721 | - | - | - | 404,379,116 | 100 | 14,821,721 | 584,934,967 | 3,852,166 |\n"
    c = {x["key"]: x for x in pt.build_cards(rp.parse_report(text), None, None)}["invest"]
    q = {x["key"]: x for x in pt.build_cards(rp.parse_report(text.split("국민은행")[0].split("법인명 |")[0] + "기재 생략\n"), None, None, reprt="11014")}["invest"]
    check(q["empty"].startswith("이 보고서엔 타법인출자 상세표가 실려 있지 않아요"), "분기보고서 상세표 생략 안내")
    check(c["empty"].startswith("출자 1곳을 확인했는데, 이번 기간에 취득·처분한 곳은 없어요"), "취득·처분이 없으면 확인한 곳 수와 함께 (KB금융 2025)")


def test_rnd_plant_region():
    p = rp.parse_report(REPORT.replace("{x}", ""))
    r = pt.rnd_ratio(p)
    check(r["cost"][:2] == (2388938, 4589424) and r["ratio"][:2] == (2.5, 2.6) and r["unit"] == "백만원", "R&D 비용·비율 (당기가 앞 칸, 정부보조금 줄 무시)")
    cards = {c["key"]: c for c in pt.build_cards(p, None, None)}
    check(cards["rnd"]["value"] == "2.5%" and cards["rnd"]["change"] == "0.10%p 하락", "R&D 카드")
    half = {c["key"]: c for c in pt.build_cards(p, None, None, reprt="11012")}
    check("직전 사업연도 전체" in half["rnd"]["rows"][0][1] and "감소" not in half["rnd"]["rows"][0][1], "반기 R&D는 연간 금액과 증감을 내지 않음")
    check(pt.change_text(30.67, 30.67, pct=False) == "변동 없음", "변동 없음")
    check(cards["plant"]["rows"][0][1] == "(3) 가동률" and any("86.2" in r[1] and r[2] for r in cards["plant"]["rows"]), "가동률 제목 줄과 그 아래 표 줄 (계산 없이)")
    check(any("미주" in r[1] for r in cards["region"]["rows"]), "지역별 매출 원문 줄")


SEG = """II. 사업의 내용
4. 매출 및 수주상황
매출 | 1 |
III. 재무에 관한 사항
5. 재무제표 주석
30. 부문별 보고 (연결)
|
순매출액의 지역별 공시 |
당기 | (단위 : 백만원) |
| 지역 | 지역 합계 |
| 국내 | 외국 |
| 미주 | 유럽 | 아시아 및 아프리카 | 중국 |
순매출액 | 46,641,151 | 133,274,793 | 53,327,193 | 53,047,987 | 47,314,814 | 333,605,938 |
|
전기 | (단위 : 백만원) |
| 지역 | 지역 합계 |
| 국내 | 외국 |
| 미주 | 유럽 | 아시아 및 아프리카 | 중국 |
순매출액 | 39,826,088 | 118,828,546 | 50,118,754 | 48,171,377 | 43,926,138 | 300,870,903 |
|
비유동자산의 지역별 공시 |
당기 | (단위 : 백만원) |
| 국내 | 외국 |
| 미주 | 유럽 | 아시아 및 아프리카 | 중국 |
비유동자산 | 182,111,025 | 32,989,995 | 7,614,552 | 9,884,452 | 9,850,058 | 242,450,082 |
31. 법인세
x | 1 |
"""


def test_region():
    p = rp.parse_report(SEG)
    r = pt.region_sales(p)
    check([n for n, _ in r["now"]] == ["국내", "미주", "유럽", "아시아 및 아프리카", "중국", "합계"] and r["unit"] == "백만원", "겹친 머리글 풀기 (삼성전자 모양)")
    check(dict(r["prev"])["미주"] == 118828546 and "순매출액" in p["lines"][r["line_now"] - 1], "전기 값과 줄 번호, 자산 표는 건너뜀")
    hy = SEG.replace("당기 |", "당반기 |").replace("전기 |", "전반기 |").replace("| 국내 | 외국 |", "| 본사 소재지 국가 | 외국 |").replace("순매출액", "매출액")
    check(pt.region_sales(rp.parse_report(hy))["now"][0][0] == "국내", "현대차 모양 (당반기·본사 소재지 국가)")
    c = {x["key"]: x for x in pt.build_cards(p, None, None)}["region"]
    check(c["value"] == "미주 39.9%" and any(r[0] == "미주" and "133조2748억원" in r[1] and "12.2% 증가" in r[1] for r in c["rows"]), "지역별 매출 카드 (비중·전기 대비)")


def test_employee_real_shapes():
    sam = {"list": [  # 삼성전자 2025 사업보고서 empSttus 그대로 ('성별합계' 줄이 섞임)
        {"fo_bbm": "DX", "sexdstn": "남", "sm": "38,119", "avrg_cnwk_sdytrn": "      17.4", "fyer_salary_totamt": "-", "jan_salary_am": "-"},
        {"fo_bbm": "DX", "sexdstn": "여", "sm": "12,698", "avrg_cnwk_sdytrn": "      14.4", "fyer_salary_totamt": "-", "jan_salary_am": "-"},
        {"fo_bbm": "DS", "sexdstn": "남", "sm": "56,154", "avrg_cnwk_sdytrn": "      11.7", "fyer_salary_totamt": "-", "jan_salary_am": "-"},
        {"fo_bbm": "DS", "sexdstn": "여", "sm": "21,910", "avrg_cnwk_sdytrn": "      12.1", "fyer_salary_totamt": "-", "jan_salary_am": "-"},
        {"fo_bbm": "성별합계", "sexdstn": "남", "sm": "94,273", "avrg_cnwk_sdytrn": "      14.0", "fyer_salary_totamt": "15,562,454,000,000", "jan_salary_am": "167,000,000"},
        {"fo_bbm": "성별합계", "sexdstn": "여", "sm": "34,608", "avrg_cnwk_sdytrn": "      13.0", "fyer_salary_totamt": "4,237,308,000,000", "jan_salary_am": "130,000,000"}]}
    e = pt.employee_stats(sam)
    check(e["count"] == 128881, "삼성전자: '성별합계' 줄을 두 번 세지 않음 (12만8881명)")
    check(abs(e["avg"] - (167e6 * 94273 + 130e6 * 34608) / 128881) < 1 and e["avg_how"] == "1인 평균 급여액 가중 평균", "삼성전자: 합계 줄의 1인 평균 급여액 가중 평균")
    hy = {"list": [
        {"fo_bbm": "반도체", "sexdstn": "남", "sm": "23,037", "avrg_cnwk_sdytrn": "12.3", "fyer_salary_totamt": "4,376,624,000,000", "jan_salary_am": "198,000,000"},
        {"fo_bbm": "반도체", "sexdstn": "여", "sm": "11,512", "avrg_cnwk_sdytrn": "15.7", "fyer_salary_totamt": "1,771,407,000,000", "jan_salary_am": "159,000,000"}]}
    h = pt.employee_stats(hy)
    check(h["count"] == 34549 and pt.won_text(h["avg"], man=True) == "1억8500만원", "SK하이닉스: 1억8500만원 (기사와 같음)")


MAT = """II. 사업의 내용
3. 원재료 및 생산설비
가. 주요 원재료 현황
(단위 : 억원, %) |
부 문 | 품 목 | 구체적 용도 | 매입액 | 비중 | 주요 매입처 |
DX 부문 | 모바일AP 솔루션 | CPU | 138,272 | 18.5% | Qualcomm, MediaTek |
디스플레이 패널 | TVㆍ모니터용 화면표시장치 | 79,606 | 10.7% | CSOT, SDP 등 |
기타 | - | 468,772 | 62.9% | |
소 계 | 745,693 | 100.0% | |
DS 부문 | Chemical | 원판 가공 | 29,900 | 17.1% | 솔브레인㈜, 동우화인켐㈜ 등 |
기타 | - | 122,907 | 70.5% | |
소 계 | 174,432 | 100.0% | |
※ 원재료 가격은 부문 등 간의 내부거래 등을 포함하고 있습니다. |
라. 생산설비 및 투자 현황 등
(2) 주요 투자 현황2022년 주요투자 현황 및 2023년 계획은 아래표를 참조하여 주시기 바랍니다.
(단위: 억원)
사업부문 | 구 분 | 2023년 계획 | 2022년 실적 | 2021년 실적 | 2020년 실적 |
차량부문 | R&D투자 | 41,502 | 35,268 | 30,939 | 28,784 |
합 계 | 105,267 | 84,897 | 75,370 | 84,190 |
4. 매출 및 수주상황
x | 1 |
III. 재무에 관한 사항
1. 요약재무정보
x | 1 |
"""


def test_material_and_fin():
    m = pt.material_table(rp.parse_report(MAT))
    check(m["total"] == 745693 + 174432 and m["unit"] == "억원" and m["line_total"] is None, "삼성전자 모양: 합계 줄이 없으면 부문 소계를 더함")
    check(m["items"][0][0] == "DX 부문 · 모바일AP 솔루션 · CPU" and m["items"][0][2] == 18.5 and all("기타" not in i[0] for i in m["items"]), "품목 큰 순, '기타' 뺌")
    eco = MAT.replace("부 문 | 품 목 | 구체적 용도 | 매입액 | 비중 | 주요 매입처 |", "품 목 | 구체적 용도 | 매입액 | 비율 |").replace("(단위 : 억원, %) |", "(기준일 : 2025년 12월 31일) | (단위 : 백만원) |")
    eco = eco.split("DX 부문")[0] + "전구체,리튬 등 | 양극활물질 제조 소재 | 1,906,841 | 98.8% |\n기타 | - | 23,412 | 1.2% |\n합계 | 1,930,253 | 100% |\n4. 매출 및 수주상황\nx | 1 |\nIII. 재무에 관한 사항\n1. 요약재무정보\nx | 1 |\n"
    e = pt.material_table(rp.parse_report(eco))
    check(e["total"] == 1930253 and e["unit"] == "백만원" and e["line_total"] and e["items"][0][1] == 1906841, "에코프로비엠 모양: 합계 줄")
    hy = MAT.split("부 문 |")[0] + """부문 | 구분 | 매입유형 | 주요품목 | 매입액 | 비율(%) | 비고 |
차량부문 | 국내공장(HMC) | 부품 | 모듈/시트外 | 203,216 | 44.5 | 현대모비스外 |
미국공장(HMMA) | 부품 | 모듈/시트外 | 71,287 | 15.6 | 현대모비스外 |
계 | 부품 | 404,013 | 88.4 | |
합 계 | 457,030 | 100.0 | |
4. 매출 및 수주상황
x | 1 |
III. 재무에 관한 사항
1. 요약재무정보
x | 1 |
"""
    h = pt.material_table(rp.parse_report(hy))
    check(h["total"] == 457030 and [i[0] for i in h["items"]] == ["국내공장(HMC) · 부품 · 모듈/시트外", "미국공장(HMMA) · 부품 · 모듈/시트外"], "현대차 모양: 중간 '계' 줄 빼고 공장 이름 붙임")
    plan = pt.invest_plan_lines(rp.parse_report(MAT))
    check(any("41,502" in t for _, t in plan) and any("105,267" in t for _, t in plan), "투자 계획·실적 표 줄 (계산 안 함)")
    fin_rows = [
        {"sj_div": "BS", "account_id": "ifrs-full_Liabilities", "account_nm": "부채총계", "thstrm_amount": "100,000", "frmtrm_amount": "90,000"},
        {"sj_div": "BS", "account_id": "ifrs-full_Equity", "account_nm": "자본총계", "thstrm_amount": "200,000", "frmtrm_amount": "200,000"},
        {"sj_div": "BS", "account_id": "x", "account_nm": "현금및현금성자산", "thstrm_amount": "30,000", "frmtrm_amount": "20,000"},
        {"sj_div": "BS", "account_id": "x", "account_nm": "단기차입금", "thstrm_amount": "10,000", "frmtrm_amount": "5,000"},
        {"sj_div": "BS", "account_id": "x", "account_nm": "사 채", "thstrm_amount": "15,000", "frmtrm_amount": "15,000"},
        {"sj_div": "BS", "account_id": "x", "account_nm": "단기차입금", "thstrm_amount": "10,000", "frmtrm_amount": "5,000"},
        {"sj_div": "CF", "account_id": "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", "account_nm": "유형자산의 취득", "thstrm_amount": "(40,000)", "frmtrm_amount": "(50,000)"}]
    f = pt.fin_stats(fin_rows)
    check(f["now"]["debt_ratio"] == 50.0 and f["prev"]["debt_ratio"] == 45.0 and f["now"]["borrow"] == 25000 and f["now"]["net_borrow"] == -5000, "부채비율·차입금(같은 계정 한 번만)·순차입금")
    check(f["now"]["capex"] == 40000 and f["prev"]["capex"] == 50000, "유형자산 취득 (괄호 음수를 크기로)")
    big = lambda x: x.replace("000", "000" + "0" * 8) if x else x  # 원 단위를 억원대로 키움 (괄호 음수 유지)
    fin = dict(pt.fin_stats([dict(r, thstrm_amount=big(r["thstrm_amount"]), frmtrm_amount=big(r["frmtrm_amount"])) for r in fin_rows]), fs="연결")
    cards = {c["key"]: c for c in pt.build_cards(rp.parse_report(MAT), None, None, fin_api=lambda: fin)}
    check(cards["debt"]["value"] == "부채비율 50.0%" and cards["debt"]["change"] == "5%p 상승", "부채비율 카드 (전기말 대비)")
    check(cards["capex"]["value"] == "4조원" and cards["capex"]["change"] == "20.0% 감소", "시설투자 카드 (유형자산 취득)")
    check(any("105,267" in r[1] for r in cards["plan"]["rows"]), "투자 계획·실적 원문 줄은 따로 카드")
    fast = {c["key"] for c in pt.build_cards(None, None, None, fin_api=lambda: fin, part="fast")}
    doc = {c["key"] for c in pt.build_cards(rp.parse_report(MAT), None, None, fin_api=lambda: fin, part="doc")}
    check(fast == {"capex", "debt"} and "plan" in doc and "material" in doc and not (doc & fast), "빠른 카드(원문 없이)·원문 카드 나누기")
    check(cards["material"]["value"] == "92조125억원", "원재료 매입액 카드 (억원 단위 표)")
    bank = rp.parse_report(MAT.replace("3. 원재료 및 생산설비", "1. 영업의 현황"))
    check("debt" not in {c["key"] for c in pt.build_cards(bank, None, None, fin_api=lambda: fin)}, "금융업은 부채비율 카드 뺌")


def test_income():
    q3 = [  # 3분기보고서 모양: thstrm=3개월, thstrm_add=누적
        {"sj_div": "CIS", "account_id": "ifrs-full_Revenue", "account_nm": "매출액", "thstrm_amount": "46,000", "thstrm_add_amount": "140,000",
         "frmtrm_amount": "43,000", "frmtrm_add_amount": "130,000"},
        {"sj_div": "CIS", "account_id": "dart_OperatingIncomeLoss", "account_nm": "영업이익", "thstrm_amount": "2,000", "thstrm_add_amount": "9,000",
         "frmtrm_amount": "-1,000", "frmtrm_add_amount": "10,000"},
        {"sj_div": "CIS", "account_id": "x", "account_nm": "분기순손실", "thstrm_amount": "500", "thstrm_add_amount": "1,200",
         "frmtrm_amount": "-300", "frmtrm_add_amount": "2,000"}]
    inc = pt.income_stats(q3)
    check(inc["cum"]["now"]["rev"] == 140000 and inc["cum"]["prev"]["op"] == 10000 and inc["qtr"]["now"]["op"] == 2000, "누적·분기(3개월) 나누기")
    check(inc["cum"]["now"]["net"] == -1200, "'분기순손실' 이름이면 양수도 손실")
    check(pt.profit_change(2000, -1000) == "흑자 전환" and pt.profit_change(-5, 3) == "적자 전환" and pt.profit_change(-3, -5) == "적자 축소", "흑자·적자 전환")
    fin = dict(pt.fin_stats(q3), fs="연결")
    c = {x["key"]: x for x in pt.build_cards(None, None, None, reprt="11014", fin_api=lambda: fin, part="fast")}["income"]
    check(c["title"] == "실적 (누적)" and c["change"] == "10.0% 감소" and any("이번 분기(3개월) 영업이익" in r[0] and "흑자 전환" in r[1] for r in c["rows"]), "실적 카드 (누적 + 이번 분기)")
    loss = dict(pt.fin_stats([dict(r, thstrm_add_amount="", frmtrm_add_amount="", thstrm_amount=r["thstrm_amount"].replace("2,000", "-34,000000000").replace("46,000", "2531000000000").replace("500", "-81000000000"),
                                   frmtrm_amount=r["frmtrm_amount"].replace("-1,000", "112000000000").replace("43,000", "2774000000000").replace("-300", "54000000000")) for r in q3]), fs="연결")
    lc = {x["key"]: x for x in pt.build_cards(None, None, None, fin_api=lambda: loss, part="fast")}["income"]
    check(lc["value"] == "영업손실 340억원" and lc["change"] == "적자 전환" and any(r[0] == "순이익" and r[1].startswith("순이익 810억원") is False and "순손실 810억원" in r[1] for r in lc["rows"])
          and any(r[0] == "영업이익률" and r[1].startswith("-1.3%") for r in lc["rows"]), "적자: '영업손실 ○억원', 마이너스 줄도 보임")
    yr = pt.income_stats([dict(r, thstrm_add_amount="", frmtrm_add_amount="") for r in q3])
    check(yr["qtr"] is None and yr["cum"]["now"]["rev"] == 46000, "사업보고서(누적 칸 없음)")
    mdna = "II. 사업의 내용\n1. 사업의 개요\nx\nIV. 이사의 경영진단 및 분석의견\n당사의 매출액은 반도체 수요 회복으로 전년 대비 12% 증가하였습니다.\n매출 | 1 | 2 |\nV. 회계감사인의 감사의견 등\nx\n"
    r = {x["key"]: x for x in pt.build_cards(rp.parse_report(mdna), None, None, part="doc")}
    check("reason" in r and "반도체 수요 회복" in r["reason"]["rows"][0][1], "실적 변동 이유 (경영진단 원문 줄)")


def test_api_cards():
    emp_now = {"list": [{"fo_bbm": "DX", "sexdstn": "남", "sm": "1,000", "fyer_salary_totamt": "158,000,000,000", "avrg_cnwk_sdytrn": "12.0"},
                        {"fo_bbm": "DX", "sexdstn": "여", "sm": "1,000", "fyer_salary_totamt": "158,000,000,000", "avrg_cnwk_sdytrn": "10.0"},
                        {"fo_bbm": "합계", "sexdstn": "", "sm": "2,000", "fyer_salary_totamt": "316,000,000,000"}]}
    emp_prev = {"list": [{"fo_bbm": "DX", "sexdstn": "남", "sm": "1,900", "fyer_salary_totamt": "247,000,000,000"}]}
    hy = {"list": [{"nm": "삼성생명보험㈜", "relate": "최대주주 본인", "stock_knd": "보통주", "bsis_posesn_stock_qota_rt": "8.51", "trmend_posesn_stock_qota_rt": "8.51"},
                   {"nm": "계", "relate": "-", "stock_knd": "보통주", "bsis_posesn_stock_qota_rt": "20.08", "trmend_posesn_stock_qota_rt": "19.92"}]}
    mr = {"list": [{"se": "소액주주", "shrholdr_co": "4,240,000", "hold_stock_rate": "70.1"}]}
    mr0 = {"list": [{"se": "소액주주", "shrholdr_co": "4,000,000", "hold_stock_rate": "70.0"}]}
    pay = {"list": [{"nm": "이원진", "ofcps": "사장", "mendng_totamt": "7,305,000,000"}, {"nm": "노 태문", "ofcps": "사장", "mendng_totamt": "6,125,000,000"},
                    {"nm": "회장\n이원진", "ofcps": "사장", "mendng_totamt": "7,305,000,000"}]}
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
    check(cards["pay"]["value"] == "이원진 " + pt.won_text(7_305_000_000) and len(cards["pay"]["rows"]) == 2, "최고 보수 (이름 앞 직위 줄 떼고 한 사람으로)")
    check(cards["holder"]["value"] == "19.92%" and cards["holder"]["change"] == "0.16%p 하락", "최대주주 지분 (기초 대비)")
    check(any("4,240,000명" in r[1] and "6.0% 증가" in r[1] for r in cards["holder"]["rows"]), "소액주주 수 변화")
    check(any(r[0] == "현금배당 총액" and "11조원" in r[1] for r in cards["return"]["rows"]) and cards["return"]["value"] == "소각 50주", "자사주·배당")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("모두 통과")
