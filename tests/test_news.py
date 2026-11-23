"""기사 모으기 시험 (가짜 네이버 응답, 실제 기사 아님). 실행: python tests/test_news.py"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import news_collect as nc


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("ok -", msg)


class Res:
    def __init__(self, items, code=200):
        self.items, self.status_code = items, code

    def json(self):
        return {"items": self.items}


def item(i, title, desc, url):
    return {"title": title, "description": desc, "link": f"https://n.news.naver.com/{i}", "originallink": url,
            "pubDate": "Mon, 17 Nov 2026 09:00:00 +0900"}


class Session:
    def __init__(self, pages):
        self.pages, self.calls = pages, 0

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls += 1
        return Res(self.pages.get(params["start"], []))


def test_classify_and_search():
    k, t, s = nc.classify("가나전자 직원 평균 연봉 1억… 사업보고서에 따르면 자사주 소각")
    check(k == ["사업보고서"] and "직원 급여" in t and "자사주" in t and "VIII. 임원 및 직원" in s, "분류 (종류·주제·보고서 부분)")
    check("실적(매출·이익)" in nc.classify("분기보고서에 따르면 영업이익 1조 적자 전환")[1], "실적 주제")
    check(nc.press_of("https://www.joongang.co.kr/article/1") == "중앙일보" and nc.press_of("https://biz.chosun.com/x") == "조선비즈", "언론사")
    page1 = [item(i, f"<b>가상</b>회사 {i} 가동률", "분기보고서에 따르면 가동률 &quot;80%&quot;", f"https://www.yna.co.kr/{i}") for i in range(100)]
    page1[5]["description"] = "보고서 낱말 없는 기사"
    page1[6]["title"] = page1[6]["description"] = "보고서 낱말 없는 기사"
    s = Session({1: page1, 101: page1[:3]})
    got = nc.search(s, "id", "sec", "q", pages=10, sleep=0)
    check(s.calls == 2 and len(got) == 101, "100건 미만 쪽에서 멈춤, 정기보고서 낱말 없는 기사 뺌")
    check(got[0]["title"] == "가상회사 0 가동률" and '"80%"' in got[0]["desc"] and got[0]["date"] == "2026-11-17", "HTML 태그·특수문자 정리, 날짜")


def test_merge_and_summary():
    a = nc.to_record(item(1, "가 배당 늘려", "사업보고서에 따르면 배당", "https://www.mk.co.kr/1"), "q1")
    b = nc.to_record(item(1, "가 배당 늘려", "사업보고서에 따르면 배당", "https://www.mk.co.kr/1"), "q2")
    c = nc.to_record(item(2, "나 소송", "반기보고서에 따르면 소송", "https://www.mk.co.kr/2"), "q1")
    rows, added = nc.merge([a], [b, c])
    check(len(rows) == 2 and added == 1 and rows[[r["originallink"] for r in rows].index("https://www.mk.co.kr/1")]["queries"] == ["q1", "q2"], "같은 링크는 한 번만, 검색어 합침")
    md = nc.summary(rows)
    check("| 배당 | 1 |" in md and "| 반기보고서 | 1 |" in md and "가 배당 늘려" not in md, "집계는 건수만 (기사 제목 없음)")


def test_main_writes(monkey_dir=None):
    d = tempfile.mkdtemp()
    out, summ = os.path.join(d, "n.jsonl"), os.path.join(d, "s.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps(nc.to_record(item(9, "옛 기사", "사업보고서에 따르면", "https://x.com/9"), "old"), ensure_ascii=False) + "\n")
    os.environ["NAVER_CLIENT_ID"], os.environ["NAVER_CLIENT_SECRET"] = "id", "sec"
    import requests
    orig = requests.Session
    requests.Session = lambda: Session({1: [item(1, "새 기사", "사업보고서에 따르면 연봉", "https://x.com/1")]})
    sys.argv = ["x", "--out", out, "--summary", summ, "--pages", "1"]
    try:
        nc.main()
    finally:
        requests.Session = orig
    rows = [json.loads(x) for x in open(out, encoding="utf-8")]
    check(len(rows) == 2 and os.path.exists(summ), "지난 파일에 합쳐 저장 + 집계 파일")
    sys.argv = ["x", "--out", out, "--summary", summ, "--reclassify"]
    nc.main()
    check("치우침 없는 표본" in open(summ, encoding="utf-8").read(), "다시 분류 모드 + 치우침 없는 표본 표")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("모두 통과")
