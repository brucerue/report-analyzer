"""가짜 DART 응답으로 화면을 끝까지 그려 본다 (Streamlit AppTest). 실행: python tests/test_app.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
os.environ["DART_API_KEY"] = "TEST"
from streamlit.testing.v1 import AppTest

import dart_client as dc
import points as pt
pt.fetch_api = lambda *a, **k: None  # 가짜: DART 구조화 자료 없음
pt.fetch_fin = lambda *a, **k: ([], None)  # 가짜: 재무제표 없음
from test_core import fake_report

ROWS = [{"rcept_no": "20260310000001", "rcept_dt": "20260310", "report_nm": "사업보고서 (2025.12)"},
        {"rcept_no": "20250311000004", "rcept_dt": "20250311", "report_nm": "사업보고서 (2024.12)"}]
dc.load_corp_list = lambda s: [{"corp_code": "00126380", "corp_name": "가나전지", "stock_code": "123456"}]
dc.periodic_reports = lambda *a, **k: ROWS
dc.report_text = lambda s, c, key, rno, **k: fake_report(rate="47.2" if rno.startswith("2026") else "60.1",
                                                    new_line="당사는 로봇용 배터리로 사업 영역을 확대하고 있습니다." if rno.startswith("2026") else "")

at = AppTest.from_file(os.path.join(os.path.dirname(__file__), "..", "app.py"), default_timeout=30).run()
at.text_input[0].input("가나전지")
at.button[0].click().run()
assert not at.exception, at.exception
assert any("사업보고서 (2025.12)" in str(o) for o in at.selectbox[0].options), "보고서 목록"
codes = " ".join([m.value for m in at.markdown] + [str(h.proto) for h in at.get("html")])
assert "자기주식" in codes, "목차별 보기 원문 (첫 목차 I. 회사의 개요)"
assert "로봇용 배터리" in codes, "달라진 문장"
assert any("GEMINI_API_KEY" in i.value for i in at.info), "Gemini 키 없을 때 안내"
os.environ["GEMINI_API_KEY"] = "TEST"
import analyses as an
an.call_gemini = lambda *a, **k: "**한 줄 요약**: 가동률 47.2% [II-3. 원재료 및 생산설비 · 줄 16]"
at = AppTest.from_file(os.path.join(os.path.dirname(__file__), "..", "app.py"), default_timeout=30).run()
at.text_input[0].input("가나전지")
at.button[0].click().run()
next(b for b in at.button if b.label == "분석하기").click().run()
assert not at.exception, at.exception
assert any("ra-answer" in m.value for m in at.markdown), "AI 답 보이기"
print("ok - AI 분석 버튼까지 오류 없음 (가짜 AI 답)")
print("ok - 화면이 오류 없이 끝까지 그려짐 (목록·목차별 원문·달라진 문장)")

# ---- 여러 회사 비교 ----
import streamlit as st
st.cache_resource.clear()  # 앞 시험의 기업 목록 저장값을 지운다
dc.load_corp_list = lambda s: [{"corp_code": "A", "corp_name": "가나전지", "stock_code": "1"},
                               {"corp_code": "B", "corp_name": "다라전자", "stock_code": "2"}]
EMP = {"A": (1000, 158_000_000_000), "B": (500, 92_500_000_000)}
pt.fetch_api = lambda call, cache, key, api, code, year, reprt: (
    {"list": [{"fo_bbm": "전사", "sexdstn": "남", "sm": str(EMP[code][0]), "fyer_salary_totamt": str(EMP[code][1])}]} if api == "empSttus" else None)
at = AppTest.from_file(os.path.join(os.path.dirname(__file__), "..", "app.py"), default_timeout=30).run()
at.radio(key="mode").set_value("여러 회사 비교").run()
at.text_area(key="multi_names").input("가나전지, 다라전자, 없는회사")
next(b for b in at.button if b.label == "비교하기").click().run()
assert not at.exception, at.exception
assert any("없는회사" in w.value for w in at.warning), "못 찾은 회사 안내"
assert len(at.dataframe) == 1, "비교 표"
codes = " ".join(c.value for c in at.code)
assert "1인 평균 급여는 다라전자가 1억8500만원으로 가장 많았고, 가나전지(1억5800만원) 순이었다." in codes, codes
print("ok - 여러 회사 비교: 표와 순위 문장")

# ---- 원문을 못 받아도 빠른 카드는 보이고, 다른 탭은 안내 ----
st.cache_resource.clear()
dc.load_corp_list = lambda s: [{"corp_code": "00126380", "corp_name": "가나전지", "stock_code": "123456"}]


def _slow(*a, **k):
    raise dc.DartApiError("DART 원문 내려받기가 90초를 넘어 멈췄어요 (3.0MB 받음).")


dc.report_text = _slow
pt.fetch_api = lambda *a, **k: None
pt.fetch_fin = lambda *a, **k: ([{"sj_div": "CIS", "account_id": "dart_OperatingIncomeLoss", "account_nm": "영업이익", "thstrm_amount": "500000000000", "frmtrm_amount": "400000000000"},
                                 {"sj_div": "CIS", "account_id": "ifrs-full_Revenue", "account_nm": "매출액", "thstrm_amount": "9000000000000", "frmtrm_amount": "8000000000000"}], "CFS")
at = AppTest.from_file(os.path.join(os.path.dirname(__file__), "..", "app.py"), default_timeout=30).run()
at.text_input[0].input("가나전지")
at.button[0].click().run()
assert not at.exception, at.exception
html_all = " ".join(str(h.proto) for h in at.get("html"))
assert "영업이익 5000억원" in html_all, "실적 카드는 원문 없이 먼저"
assert any("90초를 넘어" in e.value for e in at.error), "원문 오류 안내"
assert any("원문을 받지 못해" in i.value for i in at.info), "다른 탭 안내"
print("ok - 원문을 못 받아도 빠른 카드(실적)는 보이고 다른 탭은 안내")


# ---- 기사 쓰기: 요소 고르고 리드 정하면 초안 ----
st.cache_resource.clear()
dc.report_text = lambda s, c, key, rno, **k: fake_report(rate="47.2" if rno.startswith("2026") else "60.1")
pt.fetch_api = lambda *a, **k: None
at = AppTest.from_file(os.path.join(os.path.dirname(__file__), "..", "app.py"), default_timeout=30).run()
at.text_input[0].input("가나전지")
at.button[0].click().run()
assert not at.exception, at.exception
ms = at.multiselect(key="w_pick")
assert "실적 · 2025년" in ms.options, ms.options
ms.set_value(["income"]).run()
at.radio(key="w_lead").set_value("income").run()
at.button(key="w_go").click().run()
assert not at.exception, at.exception
codes = " ".join(c.value for c in at.code)
assert "가나전지가" in codes and "공시한 2025년 사업보고서에 따르면 2025년 매출은 9조원으로 전년보다 12.5% 증가했고" in codes, codes[:300]
print("ok - 기사 쓰기: 요소·리드 고르고 기사 만들기")


# ---- 문체 틀: 가짜 문체 폴더 + 가짜 Gemini(작성 -> 점검) ----
import tempfile
sd = tempfile.mkdtemp()
os.makedirs(os.path.join(sd, "examples"))
open(os.path.join(sd, "style_rules.md"), "w", encoding="utf-8").write("# 가짜 문체 규칙\n리드는 숫자 없이.")
open(os.path.join(sd, "examples", "B_가짜.md"), "w", encoding="utf-8").write("가짜 예문 B")
os.environ["STYLE_DIR"] = sd
calls = []


def fake_gemini(session, key, model, prompt, system, fallback=None):
    calls.append((system, prompt))
    if len(calls) == 1:
        return "제목: 가나전지, 배터리 호조…매출 12.5% 증가\n\n가나전지 실적이 좋아졌다.\n\n가나전지가 OO일 공시한 2025년 사업보고서에 따르면 매출은 9조원이다. 【확인 필요: 원인】"
    return ("제목: 가나전지, 배터리 호조…매출 12.5% 증가\n\n가나전지 실적이 개선됐다.\n\n가나전지가 OO일 공시한 2025년 사업보고서에 따르면 매출은 9조원이다. 【확인 필요: 원인】"
            "\n\n[고친 곳]\n- 실적이 좋아졌다 → 실적이 개선됐다")


an.call_gemini = fake_gemini
at.run()
assert not at.exception, at.exception
at.radio(key="f_kind").set_value("B").run()
at.button(key="f_go").click().run()
assert not at.exception, at.exception
assert len(calls) == 2 and "가짜 문체 규칙" in calls[0][0] and "가짜 예문 B" in calls[0][1] and "9조원" in calls[0][1], "작성 호출: 규칙·예문·숫자 자료"
assert "규칙에 어긋난 문장만 고쳐라" in calls[1][1] and "실적이 좋아졌다" in calls[1][1], "점검 호출: 첫 초안"
codes = " ".join(c.value for c in at.code)
assert "실적이 개선됐다" in codes and "[고친 곳]" not in codes, "점검 뒤 기사, 고친 곳은 따로"
html = " ".join(str(h.proto) for h in at.get("html"))
assert "<mark" in html and "OO일" in html, "【확인 필요】·OO일 형광펜"
assert not at.warning or all("숫자 자료에 없는" not in w.value for w in at.warning), "숫자 대조 통과"
print("ok - 문체 틀: 작성 -> 규칙 점검, 고친 곳 따로, 자리 표시 형광펜")


# ---- 점검에서 한도에 걸리면 첫 초안을 살린다 ----
calls.clear()


def quota_on_check(session, key, model, prompt, system, fallback=None):
    calls.append(1)
    if len(calls) == 1:
        return "제목: 가나전지 실적\n\n첫 초안 본문 9조원."
    raise an.AiError("AI 무료 사용량의 분당 한도를 넘었어요(기본 모델·예비 모델 모두). 1분쯤 뒤에 다시 눌러 주세요.", quota=True)


an.call_gemini = quota_on_check
at.button(key="f_go").click().run()
assert not at.exception, at.exception
assert any("규칙 점검은 못 했어요" in w.value for w in at.warning) and "첫 초안 본문" in " ".join(c.value for c in at.code), "점검 실패해도 첫 초안"
print("ok - 점검에서 한도에 걸려도 첫 초안은 보임")

