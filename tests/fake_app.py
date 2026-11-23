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
pt.fetch_api = lambda *a, **k: None  # 가짜: DART 구조화 자료 없음
from test_core import fake_report

ROWS = [{"rcept_no": "20260401000002", "rcept_dt": "20260401", "report_nm": "[기재정정]사업보고서 (2025.12)"},
        {"rcept_no": "20260310000001", "rcept_dt": "20260310", "report_nm": "사업보고서 (2025.12)"},
        {"rcept_no": "20250311000004", "rcept_dt": "20250311", "report_nm": "사업보고서 (2024.12)"}]
dc.load_corp_list = lambda s: [{"corp_code": "00126380", "corp_name": "가나전지", "stock_code": "123456"}]
dc.periodic_reports = lambda *a, **k: ROWS
dc.report_text = lambda s, c, key, rno: fake_report(
    rate="47.2" if rno.startswith("2026") else "60.1",
    new_line="당사는 로봇과 우주항공용 배터리로 사업 영역을 확대하고 있습니다." if rno.startswith("2026") else "당사는 ESS 사업을 축소하고 있습니다.")
an.call_gemini = lambda *a, **k: (
    "**한 줄 요약**: 가동률이 47.2%로 나타났다.\n\n**핵심 포인트**\n"
    "- 2025년 가동률은 47.2%다 [II-3. 원재료 및 생산설비 · 줄 16]\n"
    "- 회사는 주요 원재료인 양극재 가격이 하락했다고 설명 [II-3. 원재료 및 생산설비 · 줄 17]\n"
    "- 미주 매출은 133,274,900 백만원이다 [II-4. 매출 및 수주상황 · 줄 19]\n\n"
    "**기사로 쓴다면 확인할 것**\n- 가동률이 낮아진 공장은 어디인지")
runpy.run_path(os.path.join(HERE, "..", "app.py"), run_name="__main__")
