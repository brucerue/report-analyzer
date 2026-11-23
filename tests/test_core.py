"""가짜 정기보고서로 목차 나누기·줄 번호·비교·숫자 대조·보고서 목록을 시험한다. 실행: python tests/test_core.py"""
import io
import os
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import analyses as an
import dart_client as dc
import report_parse as rp

TOC = """사 업 보 고 서
목 차
I. 회사의 개요 ………………… 1
II. 사업의 내용 ………………… 5
III. 재무에 관한 사항 ……………… 30"""


def fake_report(rate="47.2", new_line=""):
    """doc_text_from_zip처럼 빈 줄 없는 글 (빈 줄 두 개는 '첨부 파일 경계'라서)"""
    return "\n".join(x for x in _fake(rate, new_line).split("\n") if x.strip())


def _fake(rate, new_line):
    return f"""{TOC}
Ⅰ. 회사의 개요
1. 회사의 개요
당사는 전기차 배터리를 만드는 회사로 1999년 설립되었습니다.
4. 주식의 총수 등
자기주식 | 기초 | 취득 | 소각 | 기말
보통주 | 1,000 | 200 | 100 | 1,100
II. 사업의 내용
1. 사업의 개요
당사는 중대형 전지 사업을 영위하고 있으며 북미 시장에 집중하고 있습니다.
{new_line}
3. 원재료 및 생산설비
(단위: 백만원, %)
가동률 | 2025년 | {rate}
당사의 주요 원재료는 양극재이며 가격이 하락하였습니다.
4. 매출 및 수주상황
미주 지역 매출은 133,274,800 백만원으로 전년 대비 증가하였습니다.
III. 재무에 관한 사항
I. 매출액
매출액 | 100
5. 재무제표 주석
15. 재고자산 (연결)
재고자산은 제품과 원재료로 구성되어 있으며 기말 잔액은 5,000,000 백만원입니다.
16. 우발부채와 약정사항 (연결)
당사는 미국에서 특허 소송의 피고로 계류 중이며 소송가액은 1,234 백만원입니다.
17. 특수관계자
지배기업과의 매출 거래는 4,321 백만원입니다.
VIII. 임원 및 직원 등에 관한 사항
1. 임원 및 직원 등의 현황
직원 수 | 12,345 | 1인평균급여액 | 158
2. 임원의 보수 등
보수 5억원 이상 개인별 보수 현황이 있습니다. 홍길동 사장 7,305 백만원입니다.
XII. 상세표
1. 연결대상 종속회사 현황(상세)
종속회사 LG Energy Solution Michigan 등 95개사가 연결 대상에 포함됩니다.
당기 중 미국 합작법인 두 곳을 새로 설립하여 연결 대상에 편입하였고, 중국 판매법인 한 곳은 청산하여 연결에서 제외하였습니다.
"""


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("ok -", msg)


def test_parse():
    p = rp.parse_report(fake_report())
    check(set(["co", "biz", "fin", "staff", "detail"]) <= set(p["mains"]), "대분류 찾기 (목차 점선 줄은 건너뜀, Ⅰ도 읽음)")
    check("fin" in p["mains"] and "I. 매출액" in rp.main_text(p, "fin", numbered=False), "재무제표 'I. 매출액'을 대분류로 착각하지 않음")
    for k in ("biz_plant", "biz_sales", "co_shares", "staff_people", "staff_pay", "detail_consol", "note_contingent",
              "note_related", "note_inventory"):
        check(k in p["blocks"], f"블록 {k}")
    t = rp.block_text(p, "biz_plant")
    line_no = int(t.split("\n")[1].split(":")[0])
    check("가동률" in p["lines"][line_no - 1], "줄 번호가 원문 줄을 정확히 가리킴")
    check("특수관계자" not in rp.block_text(p, "note_contingent", numbered=False), "주석은 다음 번호 앞에서 끊김")


def test_no_toc():
    try:
        rp.parse_report("그냥 공시\n내용")
    except rp.ParseError:
        print("ok - 목차 없는 글은 ParseError")
        return
    raise AssertionError("ParseError가 나야 함")


def test_diff_and_numbers():
    prev = rp.parse_report(fake_report(rate="60.1"))
    cur = rp.parse_report(fake_report(rate="47.2", new_line="당사는 로봇과 우주항공용 배터리로 사업 영역을 확대하고 있습니다."))
    diffs, _ = an.report_diff(prev, cur)
    added = [s for d in diffs for _, s in d["added"]]
    check(any("로봇" in s for s in added), "새로 생긴 문장을 찾음")
    check(not any("가동률" in s for d in diffs for _, s in d["added"] + d["removed"]), "숫자만 바뀐 줄은 비교에서 뺌")
    body, read, missing, _ = an.analysis_input(cur, an.ANALYSIS_BY_KEY["plant"])
    check(read and body.split("\n")[1][0].isdigit(), "AI 발췌에 줄 번호가 붙음")
    ans = "가동률은 47.2%다 [II-3. 원재료 및 생산설비 · 줄 18]. 매출은 999,999 백만원."
    check(an.unverified_numbers(ans, body) == ["999,999"], "발췌에 없는 숫자만 골라냄 (줄 번호·있는 숫자는 통과)")
    check(an.cited_lines(ans) == [18], "근거 줄 번호 읽기")
    check(an.has_content(body + "\n99: 당사는 북미 공장의 생산능력을 확대하기 위해 신규 라인 투자를 진행하고 있습니다.") and not an.has_content("[II-3. 원재료]\n12: 해당사항 없음"), "내용 거의 없으면 AI를 안 부름")
    prompt = an.build_prompt("가나전지", {"report_nm": "사업보고서 (2025.12)", "rcept_no": "1"}, an.ANALYSIS_BY_KEY["plant"], body)
    check("[발췌]" in prompt and "가동률" in prompt, "AI 질문 만들기")


def test_report_names():
    rows = [
        {"rcept_no": "20260310000001", "rcept_dt": "20260310", "report_nm": "사업보고서 (2025.12)"},
        {"rcept_no": "20260401000002", "rcept_dt": "20260401", "report_nm": "[기재정정]사업보고서 (2025.12)"},
        {"rcept_no": "20251114000003", "rcept_dt": "20251114", "report_nm": "분기보고서 (2025.09)"},
        {"rcept_no": "20250311000004", "rcept_dt": "20250311", "report_nm": "사업보고서 (2024.12)"},
    ]
    latest = dc.latest_versions(rows)
    check(len(latest) == 3 and latest[0]["rcept_no"] == "20260401000002" and latest[0]["versions"] == 2, "정정본은 가장 늦은 것만, 정정 횟수 표시")
    check(dc.find_prev_periodic(latest, latest[0])["rcept_no"] == "20250311000004", "1년 전 같은 기간 보고서")
    check(dc.find_prev_quarter(latest, latest[0])["rcept_no"] == "20251114000003", "바로 앞 보고서 (12월 -> 9월)")


def test_zip_and_list():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("20260310000001.xml", "<TITLE>II. 사업의 내용</TITLE><P>본문</P><TABLE><TR><TD>가동률</TD><TD>47.2</TD></TR></TABLE>")
        z.writestr("20260310000001_00760.xml", "<P>첨부 감사보고서</P>")
    text = dc.doc_text_from_zip(buf.getvalue())
    check(text.index("본문") < text.index("첨부"), "본문 파일이 맨 앞")
    check("가동률 | 47.2 |" in text, "표 칸은 ' | '로")

    class Res:
        def __init__(self, jo):
            self.jo = jo
        def json(self):
            return self.jo

    class Session:
        calls = 0
        def get(self, url, params=None, timeout=None):
            Session.calls += 1
            return Res({"status": "000", "total_page": 1, "list": [
                {"rcept_no": "1", "rcept_dt": "20260310", "report_nm": "사업보고서 (2025.12)"},
                {"rcept_no": "2", "rcept_dt": "20260311", "report_nm": "주요사항보고서(자기주식취득결정)"}]})

    cache = dc.Cache()
    out = dc.periodic_reports(Session(), cache, "KEY", "00126380")
    dc.periodic_reports(Session(), cache, "KEY", "00126380")
    check([r["rcept_no"] for r in out] == ["1"] and Session.calls == 1, "정기보고서만 고르고 같은 목록은 저장해 다시 안 부름")

    corps = dc.parse_corp_csv("corp_code,corp_name,stock_code\n00000001,삼성전자서비스,\n00126380,삼성전자,005930\n00000002,삼성전자우,\n")
    check(dc.find_corps(corps, "삼성 전자")[0]["corp_code"] == "00126380", "기업명 찾기 (띄어쓰기 무시, 정확히 같은 이름 먼저)")
    check(dc.find_corps(corps, "005930")[0]["corp_name"] == "삼성전자", "종목코드로 찾기")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("모두 통과")
