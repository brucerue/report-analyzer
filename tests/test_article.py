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



def test_frame():
    """문체 틀: 숫자 자료(JSON)·작성/점검 프롬프트·점검 답 나누기·표기."""
    import os, tempfile
    import style as sty
    cards = [dict(key="income", title="실적 · 2026년 1∼9월 누적", value="영업이익 8조428억원", prev="2025년 1∼9월 영업이익 9조7700억원",
                  change="17.7% 감소", rows=[("매출", "140조2645억원 (2025년 1∼9월 139조원, 0.9% 증가)", None)], source="DART 재무제표", note=None,
                  sentences=["매출은 …"]),
             dict(key="plant", title="가동률", value="88.9%", prev=None, change=None, rows=[("HMMA(미국)", "101.0%", 123)], source="II-3", note="공장별"),
             dict(key="debt", empty="없음", title="부채", rows=[])]
    d = art.facts(cards, ["plant", "income"], "income", "현대자동차", "분기보고서 (2026.09)", "20261116")
    assert d["보고서"] == "2026년 3분기 보고서" and d["공시일"] == "2026.11.16" and [x["항목"] for x in d["항목"]] == ["실적 · 2026년 1∼9월 누적", "가동률"]
    assert d["항목"][0]["리드"] and d["항목"][1]["세부"][0]["원문 줄"] == 123 and "sentences" not in str(d), "리드 먼저, 원문 줄, 기사 문장은 안 넣음"
    cards[0]["rows"] += [("2026년 3분기(7∼9월) 매출", "46조원 (2025년 3분기 대비 3.4% 감소)", None), ("무형자산 취득", "1억원", None)]
    d2 = art.facts(cards, ["income"], "income", "현대자동차", "분기보고서 (2026.09)", "20261116")
    names = [x["항목"] for x in d2["항목"]]
    assert names == ["이번 분기 실적 · 2026년 3분기(7∼9월)", "실적 · 2026년 1∼9월 누적"] and d2["항목"][0]["리드"] and not d2["항목"][1]["리드"], names
    assert "무형자산" not in str(d2) and str(d2).count("46조원") == 1, "분기 줄은 따로 한 번, 보조 줄은 뺌"
    system, prompt = art.write_prompt("규칙 전문", ["예문1"], "B", d)
    assert system == "규칙 전문" and "OO일" in prompt and "멘트" in prompt and "약 1200자" in prompt and "내용(회사·숫자·사실)은 쓰지 마라" in prompt and "8조428억원" in prompt
    body, fixes = art.split_check("제목: 가\n\n본문 1\n\n[고친 곳]\n- 전 → 후\n- 없음")
    assert body == "제목: 가\n\n본문 1" and fixes == ["전 → 후"], (body, fixes)
    assert art.split_check("제목: 가\n\n본문")[1] == []
    assert art.pct0("59.0%와 1.0%p, 100.0%, 10.05%") == "59%와 1%p, 100%, 10.05%"
    assert art.body_chars("제목: 가나\n\n12345") == 5
    sd = tempfile.mkdtemp()
    os.makedirs(os.path.join(sd, "examples"))
    open(os.path.join(sd, "style_rules.md"), "w", encoding="utf-8").write("R")
    for n in ("B_1.md", "B_2.md", "C_1.md", "A_1.md"):
        open(os.path.join(sd, "examples", n), "w", encoding="utf-8").write(n)
    os.environ["STYLE_DIR"] = sd
    sty._cache.clear()
    s = sty.load()
    assert s["rules"] == "R" and sty.examples_for(s, "B") == ["B_1.md", "B_2.md"] and sty.examples_for(s, "C") == ["C_1.md"]
    del os.environ["STYLE_DIR"]
    sty._cache.clear()
    try:
        sty.load(token=None)
        assert False
    except sty.StyleError as e:
        assert "PAPER_PRIVATE_READ_TOKEN" in str(e)
    print("ok - 문체 틀 재료·프롬프트·점검 답·표기")

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("모두 통과")
