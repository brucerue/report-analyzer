"""기사 쓰기 시험. 실행: python tests/test_article.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import article as art
import points as pt
import report_parse as rp
from test_plant import NOW, PREV, report


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("ok -", msg)


def cards_q3():
    inc = [{"sj_div": "CIS", "account_id": "ifrs-full_Revenue", "account_nm": "매출액", "thstrm_amount": "45,110,200,000,000", "thstrm_add_amount": "140,264,500,000,000",
            "frmtrm_q_amount": "46,000,000,000,000", "frmtrm_add_amount": "139,415,900,000,000"},
           {"sj_div": "CIS", "account_id": "dart_OperatingIncomeLoss", "account_nm": "영업이익", "thstrm_amount": "2,677,200,000,000", "thstrm_add_amount": "8,042,800,000,000",
            "frmtrm_q_amount": "3,000,000,000,000", "frmtrm_add_amount": "9,772,500,000,000"}]
    fin = dict(pt.fin_stats(inc), fs="연결")
    fast = pt.build_cards(None, None, None, "11014", lambda: fin, part="fast", period="2026년 1∼9월")
    doc = pt.build_cards(rp.parse_report(report(NOW)), rp.parse_report(report(PREV, "2025년 3분기")), None, "11014", part="doc", period="2026년 1∼9월")
    return fast + doc


def test_compose():
    cards = cards_q3()
    keys = [k for k, _ in art.choices(cards)]
    check("income" in keys and "plant" in keys, "고를 수 있는 요소 = 문장이 있는 카드")
    d = art.compose(cards, ["income", "plant"], "plant", "현대자동차", "분기보고서 (2026.09)", "20261116")
    print("   제목:", d["title"])
    for p in d["paragraphs"]:
        print("   ", p[:150])
    check(d["paragraphs"][0].startswith("현대자동차가 16일 공시한 2026년 3분기 보고서에 따르면 2026년 1∼9월 4개 생산거점의 전체 가동률은"), "첫 문장: 회사·공시일·보고서 + 리드 요소")
    check(d["paragraphs"][1].startswith("2026년 1∼9월 매출은 140조2645억원으로 지난해 같은 기간보다 0.6% 증가했고, 영업이익은 8조428억원으로 17.7% 감소했다."), "둘째 문단: 다음 요소 (같은 말투: 증가·감소)")
    check(d["title"] == "현대자동차 가동률 88.9%…8.2%p 하락 / 영업이익 8조428억원", "제목 후보 (리드 + 다른 요소, 숫자엔 이름)")
    d2 = art.compose(cards, ["income", "plant"], "income", "현대자동차", "분기보고서 (2026.09)", "20261116")
    check(d2["paragraphs"][0].startswith("현대자동차가 16일 공시한 2026년 3분기 보고서에 따르면 2026년 1∼9월 매출은"), "리드를 바꾸면 순서가 바뀜")
    check("3분기(7∼9월)만 보면 영업이익은 2조6772억원으로 지난해 같은 분기보다 10.8% 감소했다." in d2["text"], "이번 분기 3개월도 문장에")
    check(art.intro("LG에너지솔루션", "사업보고서 (2025.12)", "20260310") == "LG에너지솔루션이 10일 공시한 2025년 사업보고서에 따르면", "조사·보고서 이름")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("모두 통과")
