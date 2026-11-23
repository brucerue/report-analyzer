"""가짜 DART 응답으로 화면을 끝까지 그려 본다 (Streamlit AppTest). 실행: python tests/test_app.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
os.environ["DART_API_KEY"] = "TEST"
from streamlit.testing.v1 import AppTest

import dart_client as dc
from test_core import fake_report

ROWS = [{"rcept_no": "20260310000001", "rcept_dt": "20260310", "report_nm": "사업보고서 (2025.12)"},
        {"rcept_no": "20250311000004", "rcept_dt": "20250311", "report_nm": "사업보고서 (2024.12)"}]
dc.load_corp_list = lambda s: [{"corp_code": "00126380", "corp_name": "가나전지", "stock_code": "123456"}]
dc.periodic_reports = lambda *a, **k: ROWS
dc.report_text = lambda s, c, key, rno: fake_report(rate="47.2" if rno.startswith("2026") else "60.1",
                                                    new_line="당사는 로봇용 배터리로 사업 영역을 확대하고 있습니다." if rno.startswith("2026") else "")

at = AppTest.from_file(os.path.join(os.path.dirname(__file__), "..", "app.py"), default_timeout=30).run()
at.text_input[0].input("가나전지")
at.button[0].click().run()
assert not at.exception, at.exception
assert any("사업보고서 (2025.12)" in str(o) for o in at.selectbox[0].options), "보고서 목록"
codes = " ".join(c.value for c in at.code)
assert "자기주식" in codes, "목차별 보기 원문 (첫 목차 I. 회사의 개요)"
assert "로봇용 배터리" in codes, "달라진 문장"
assert any("GEMINI_API_KEY" in i.value for i in at.info), "Gemini 키 없을 때 안내"
print("ok - 화면이 오류 없이 끝까지 그려짐 (목록·목차별 원문·달라진 문장)")
