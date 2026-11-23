"""가짜 DART 응답으로 앱을 띄운다 (화면 확인용). 실행: streamlit run tests/fake_app.py"""
import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
os.environ.setdefault("DART_API_KEY", "TEST")
os.environ.setdefault("GEMINI_API_KEY", "TEST")
import analyses as an
import dart_client as dc
import points as pt
FAKE_API = {  # 가짜 DART 구조화 자료 (이름: (올해, 1년 전))
    "empSttus": ({"list": [{"fo_bbm": "전지", "sexdstn": "남", "sm": "1,050", "fyer_salary_totamt": "68,250,000,000", "avrg_cnwk_sdytrn": "5.1"},
                           {"fo_bbm": "전지", "sexdstn": "여", "sm": "142", "fyer_salary_totamt": "6,000,000,000", "avrg_cnwk_sdytrn": "3.2"}]},
                 {"list": [{"fo_bbm": "전지", "sexdstn": "남", "sm": "1,219", "fyer_salary_totamt": "76,350,000,000"}]}),
    "hyslrSttus": ({"list": [{"nm": "가나홀딩스", "relate": "최대주주 본인", "stock_knd": "보통주", "bsis_posesn_stock_qota_rt": "45.12", "trmend_posesn_stock_qota_rt": "40.84"},
                             {"nm": "계", "stock_knd": "보통주", "bsis_posesn_stock_qota_rt": "50.33", "trmend_posesn_stock_qota_rt": "45.59"}]}, None),
    "mrhlSttus": ({"list": [{"shrholdr_co": "523,088"}]}, {"list": [{"shrholdr_co": "552,620"}]}),
    "hmvAuditIndvdlBySttus": ({"list": [{"nm": "홍길동", "ofcps": "사장", "mendng_totamt": "7,305,000,000"}, {"nm": "부사장\n김철수", "ofcps": "부사장", "mendng_totamt": "743,000,000"}]}, None),
    "alotMatter": ({"list": [{"se": "현금배당금총액(백만원)", "thstrm": "9,782", "frmtrm": "7,000"}, {"se": "주당 현금배당금(원)", "stock_knd": "보통주", "thstrm": "100", "frmtrm": "70"}]}, None),
}
OTHER = {"00000002": (3, 1.3), "00000003": (0.5, 0.8)}  # 다른 가짜 회사: (직원 배수, 급여 배수)


def _fake(call, cache, key, api, corp_code, year, reprt):
    jo = FAKE_API.get(api, (None, None))[0 if year >= 2025 else 1]
    if not jo or corp_code not in OTHER or api != "empSttus":
        return jo
    n, w = OTHER[corp_code]
    return {"list": [dict(r, sm=f"{int(pt.to_num(r['sm']) * n):,}", fyer_salary_totamt=f"{int(pt.to_num(r['fyer_salary_totamt']) * n * w):,}") for r in jo["list"]]}


pt.fetch_api = _fake
FIN = [{"sj_div": "BS", "account_id": "ifrs-full_Liabilities", "account_nm": "부채총계", "thstrm_amount": "5,200,000,000,000", "frmtrm_amount": "4,800,000,000,000"},
       {"sj_div": "BS", "account_id": "ifrs-full_Equity", "account_nm": "자본총계", "thstrm_amount": "6,100,000,000,000", "frmtrm_amount": "6,000,000,000,000"},
       {"sj_div": "BS", "account_id": "x", "account_nm": "현금및현금성자산", "thstrm_amount": "900,000,000,000", "frmtrm_amount": "1,200,000,000,000"},
       {"sj_div": "BS", "account_id": "x", "account_nm": "장기차입금", "thstrm_amount": "2,100,000,000,000", "frmtrm_amount": "1,700,000,000,000"},
       {"sj_div": "CF", "account_id": "x", "account_nm": "유형자산의 취득", "thstrm_amount": "(1,300,000,000,000)", "frmtrm_amount": "(1,900,000,000,000)"},
       {"sj_div": "CIS", "account_id": "ifrs-full_Revenue", "account_nm": "매출액", "thstrm_amount": "2,531,000,000,000", "frmtrm_amount": "2,774,000,000,000"},
       {"sj_div": "CIS", "account_id": "dart_OperatingIncomeLoss", "account_nm": "영업이익", "thstrm_amount": "-34,000,000,000", "frmtrm_amount": "112,000,000,000"},
       {"sj_div": "CIS", "account_id": "ifrs-full_ProfitLoss", "account_nm": "당기순이익(손실)", "thstrm_amount": "-81,000,000,000", "frmtrm_amount": "54,000,000,000"}]
pt.fetch_fin = lambda *a, **k: (FIN, "CFS")
from test_core import fake_report

ROWS = [{"rcept_no": "20260401000002", "rcept_dt": "20260401", "report_nm": "[기재정정]사업보고서 (2025.12)"},
        {"rcept_no": "20260310000001", "rcept_dt": "20260310", "report_nm": "사업보고서 (2025.12)"},
        {"rcept_no": "20250311000004", "rcept_dt": "20250311", "report_nm": "사업보고서 (2024.12)"}]
dc.load_corp_list = lambda s: [{"corp_code": "00126380", "corp_name": "가나전지", "stock_code": "123456"},
                               {"corp_code": "00000002", "corp_name": "다라모터스", "stock_code": "654321"},
                               {"corp_code": "00000003", "corp_name": "마바화학", "stock_code": "111111"}]
dc.periodic_reports = lambda *a, **k: ROWS
dc.report_text = lambda s, c, key, rno, **k: fake_report(
    rate="47.2" if rno.startswith("2026") else "60.1",
    new_line="당사는 로봇과 우주항공용 배터리로 사업 영역을 확대하고 있습니다." if rno.startswith("2026") else "당사는 ESS 사업을 축소하고 있습니다.")
an.call_gemini = lambda *a, **k: (
    "**한 줄 요약**: 가동률이 47.2%로 나타났다.\n\n**핵심 포인트**\n"
    "- 2025년 가동률은 47.2%다 [II-3. 원재료 및 생산설비 · 줄 16]\n"
    "- 회사는 주요 원재료인 양극재 가격이 하락했다고 설명 [II-3. 원재료 및 생산설비 · 줄 17]\n"
    "- 미주 매출은 133,274,900 백만원이다 [II-4. 매출 및 수주상황 · 줄 19]\n\n"
    "**기사로 쓴다면 확인할 것**\n- 가동률이 낮아진 공장은 어디인지")
from test_plant import NOW, PREV  # 현대차 3분기 모양 가동률 표
_orig = dc.report_text
PLANT = "3. 원재료 및 생산설비\n(3) 가동률\n| (단위 : 대, 시간) |\n사업부문 | 법인명 | 소재지 | 기간 |\n생산능력 | 생산실적 | 가동률(%) |\n{rows}\n"
dc.report_text = lambda s, c, key, rno, **k: _orig(s, c, key, rno).replace("3. 원재료 및 생산설비\n", PLANT.format(rows=NOW if rno.startswith("2026") else PREV), 1)
runpy.run_path(os.path.join(HERE, "..", "app.py"), run_name="__main__")
