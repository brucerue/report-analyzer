"""정기보고서(사업·반기·분기보고서)를 다룬 기사 모으기 — 네이버 뉴스 검색 API (무료, 하루 25,000회).

GitHub Actions 'news_collect'(수동)가 돌리고, 결과는 비공개 저장소 paper-private의 `report-news` 브랜치에만 올린다.
  - naver_reports.jsonl : 기사 한 줄씩 {title, desc, link, originallink, press, date, kinds, topics, sections, queries}
                          (네이버가 주는 제목·요약 2줄·링크뿐, 전문은 받지 않는다. 같은 링크는 한 번만, 지난 파일에 합친다)
  - summary.md          : 주제(보고서 부분)별·보고서 종류별·월별 건수 — 앱 분석 항목 우선순위의 근거
로그에는 건수만 찍는다(기사 제목·요약을 찍지 않음). 키는 GitHub Secrets NAVER_CLIENT_ID / NAVER_CLIENT_SECRET.

검색어: 문구(예: "사업보고서에 따르면") x 주제 낱말(연봉·가동률 …). 네이버는 검색어 하나당 최신 1,100건(100건 x 11쪽)까지만
주므로 주제 낱말로 쪼개 더 오래된 기사까지 모은다.
"""
import argparse
import html
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"
PHRASES = ['"사업보고서에 따르면"', '"반기보고서에 따르면"', '"분기보고서에 따르면"', '"사업보고서를 분석한"', '"사업보고서에서"']
# 주제 낱말 -> (주제 이름, 보고서 부분). 분류에도 쓴다 (제목+요약에 낱말이 있으면 그 주제).
TOPICS = [
    ("연봉|평균 급여|평균 보수|1인당 평균", "직원 급여", "VIII. 임원 및 직원"),
    ("직원 수|임직원 수|직원이|인력", "직원 수", "VIII. 임원 및 직원"),
    ("보수|연봉킹|성과급|퇴직금|스톡옵션|RSU", "임원 보수", "VIII. 임원의 보수"),
    ("임원|사외이사|이사회", "임원·이사회", "VI·VIII. 이사회·임원 현황"),
    ("지분|최대주주|특수관계인|국민연금|소액주주|주주", "지분·주주", "VII. 주주에 관한 사항"),
    ("자사주|자기주식|소각", "자사주", "I-4. 주식의 총수·자기주식"),
    ("배당", "배당", "III. 배당에 관한 사항"),
    ("출자|지분 매입|지분을 매입|투자했|인수|매각", "출자·인수·매각", "XII-3. 타법인출자"),
    ("종속회사|종속기업|자회사|계열사|해외법인|현지법인", "종속·계열회사", "XII-1·IX. 종속·계열회사"),
    ("가동률|생산능력|생산량|생산실적|공장", "가동률·생산", "II-3. 원재료 및 생산설비"),
    ("원재료|매입액|원자재|원가", "원재료", "II-3. 원재료 및 생산설비"),
    ("설비투자|시설투자|투자 계획|증설|CAPEX", "시설투자", "II-3. 원재료 및 생산설비"),
    ("연구개발|R&D|특허", "연구개발", "II-6. 연구개발"),
    ("매출처|고객사|매출 비중|지역별|미국 매출|중국 매출|수출", "매출 구성·고객", "II-4. 매출 및 수주"),
    ("수주|수주잔고", "수주", "II-4. 매출 및 수주"),
    ("소송|제재|과징금|우발|채무보증|분쟁", "소송·제재·우발", "XI. 그 밖에 투자자 보호"),
    ("특수관계|내부거래|일감", "특수관계자 거래", "X. 대주주 등과의 거래"),
    ("매출액|영업이익|순이익|영업손실|순손실|적자|흑자|실적", "실적(매출·이익)", "III·IV. 재무·경영진단"),
    ("차입|부채|현금|유동성|회사채", "부채·현금", "III·IV. 재무·경영진단"),
    ("재고", "재고", "III. 재무 주석"),
    ("전망|위험 요인|리스크", "전망·위험", "IV. 이사의 경영진단"),
]
TOPIC_WORDS = ["영업이익", "연봉", "직원", "보수", "임원", "지분", "자사주", "배당", "출자", "종속회사", "가동률", "원재료",
               "시설투자", "연구개발", "매출", "수주", "소송", "특수관계", "부채", "재고", ""]
PRESS = {  # 기사 원문 주소 -> 언론사 (주요 매체만, 나머지는 도메인)
    "chosun.com": "조선일보", "joongang.co.kr": "중앙일보", "donga.com": "동아일보", "hankyung.com": "한국경제",
    "mk.co.kr": "매일경제", "sedaily.com": "서울경제", "yna.co.kr": "연합뉴스", "edaily.co.kr": "이데일리",
    "mt.co.kr": "머니투데이", "fnnews.com": "파이낸셜뉴스", "hankookilbo.com": "한국일보", "hani.co.kr": "한겨레",
    "khan.co.kr": "경향신문", "asiae.co.kr": "아시아경제", "heraldcorp.com": "헤럴드경제", "newsis.com": "뉴시스",
    "news1.kr": "뉴스1", "biz.chosun.com": "조선비즈", "etnews.com": "전자신문", "thebell.co.kr": "더벨",
    "seoul.co.kr": "서울신문", "kmib.co.kr": "국민일보", "munhwa.com": "문화일보", "segye.com": "세계일보",
}


class NaverError(Exception):
    pass


def clean(text):
    return html.unescape(re.sub(r"<[^>]+>", "", str(text or ""))).strip()


def press_of(url):
    host = urlparse(str(url or "")).netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    for dom in sorted(PRESS, key=len, reverse=True):
        if host == dom or host.endswith("." + dom):
            return PRESS[dom]
    return host or "-"


def classify(text):
    """제목+요약 -> (보고서 종류들, 주제들, 보고서 부분들)."""
    kinds = [k for k in ("사업보고서", "반기보고서", "분기보고서") if k in text]
    topics, sections = [], []
    for pat, name, sec in TOPICS:
        if re.search(pat, text):
            topics.append(name)
            if sec not in sections:
                sections.append(sec)
    return kinds, topics, sections


def to_record(item, query):
    title, desc = clean(item.get("title")), clean(item.get("description"))
    try:
        date = parsedate_to_datetime(item.get("pubDate")).strftime("%Y-%m-%d")
    except Exception:
        date = ""
    kinds, topics, sections = classify(title + " " + desc)
    orig = item.get("originallink") or item.get("link") or ""
    return dict(title=title, desc=desc, link=item.get("link") or orig, originallink=orig, press=press_of(orig),
                date=date, kinds=kinds, topics=topics, sections=sections, queries=[query])


def search(session, cid, secret, query, pages, sleep=0.12):
    """검색어 하나 -> 기사 목록 (최신순, 최대 pages x 100건). 정기보고서 낱말이 제목·요약에 없는 기사는 뺀다."""
    out = []
    for p in range(pages):
        start = 1 + p * 100
        if start > 1000:
            break
        for attempt in range(4):
            res = session.get(NAVER_NEWS_URL, params={"query": query, "display": 100, "start": start, "sort": "date"},
                              headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": secret}, timeout=20)
            if res.status_code == 429:
                time.sleep(1.0 * (attempt + 1))
                continue
            break
        if res.status_code in (401, 403):
            raise NaverError(f"네이버 API 키 오류 [{res.status_code}] — GitHub Secrets의 NAVER_CLIENT_ID·SECRET 확인")
        if res.status_code != 200:
            raise NaverError(f"네이버 응답 오류 [{res.status_code}]")
        items = res.json().get("items") or []
        for it in items:
            rec = to_record(it, query)
            if rec["kinds"]:
                out.append(rec)
        if len(items) < 100:
            break
        time.sleep(sleep)
    return out


def merge(old, new):
    """링크(원문 주소 우선)로 합친다. 같은 기사면 검색어만 더한다."""
    by = {r.get("originallink") or r["link"]: r for r in old}
    added = 0
    for r in new:
        k = r.get("originallink") or r["link"]
        if k in by:
            q = by[k].setdefault("queries", [])
            for x in r["queries"]:
                if x not in q:
                    q.append(x)
        else:
            by[k] = r
            added += 1
    rows = sorted(by.values(), key=lambda r: (r.get("date") or "", r.get("title") or ""), reverse=True)
    return rows, added


def summary(rows):
    """주제·부분·종류·월별 건수 (기사 내용 없이 건수만)."""
    by_topic, by_sec, by_kind, by_month, by_press = Counter(), Counter(), Counter(), Counter(), Counter()
    for r in rows:
        by_topic.update(r.get("topics") or ["(주제 없음)"])
        by_sec.update(r.get("sections") or ["(부분 없음)"])
        by_kind.update(r.get("kinds") or [])
        by_month[(r.get("date") or "")[:7] or "-"] += 1
        by_press[r.get("press") or "-"] += 1
    plain = [r for r in rows if any(q in PHRASES for q in r.get("queries") or [])]
    by_plain = Counter(t for r in plain for t in (r.get("topics") or ["(주제 없음)"]))
    lines = [f"# 정기보고서 기사 집계 (네이버 뉴스 검색)", "",
             f"- 만든 때: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC · 기사 {len(rows):,}건 (제목·요약 2줄 기준 분류, 한 기사가 여러 주제에 걸림)", ""]
    lines += ["## 주제별 — 치우침 없는 표본 (주제 낱말 없이 문구만으로 검색한 기사)", "",
              f"주제 낱말을 붙인 검색은 그 주제 기사를 더 많이 모으므로, 순위는 이 표로 본다. 표본 {len(plain):,}건.", "",
              "| 주제 | 건수 | 비중 |", "|---|---|---|"] + [f"| {k} | {v:,} | {v / max(len(plain), 1) * 100:.1f}% |" for k, v in by_plain.most_common(30)] + [""]
    for title, c, n in (("주제별 (전체, 검색 방식 영향 있음)", by_topic, 30), ("보고서 부분별", by_sec, 30), ("보고서 종류별", by_kind, 5), ("언론사별(상위 20)", by_press, 20)):
        lines += [f"## {title}", "", "| 항목 | 건수 |", "|---|---|"] + [f"| {k} | {v:,} |" for k, v in c.most_common(n)] + [""]
    lines += ["## 월별", "", "| 월 | 건수 |", "|---|---|"] + [f"| {k} | {v:,} |" for k, v in sorted(by_month.items(), reverse=True)] + [""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--pages", type=int, default=10, help="검색어 하나당 몇 쪽(100건씩, 최대 10)")
    ap.add_argument("--reclassify", action="store_true", help="검색하지 않고 지난 파일의 기사만 다시 분류 (주제 표를 바꿨을 때)")
    a = ap.parse_args()
    if a.reclassify:
        with open(a.out, encoding="utf-8") as f:
            rows = [json.loads(x) for x in f if x.strip()]
        for r in rows:
            r["kinds"], r["topics"], r["sections"] = classify(r.get("title", "") + " " + r.get("desc", ""))
        with open(a.out, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        with open(a.summary, "w", encoding="utf-8") as f:
            f.write(summary(rows))
        print(f"다시 분류 {len(rows):,}건")
        return
    cid, secret = os.environ.get("NAVER_CLIENT_ID"), os.environ.get("NAVER_CLIENT_SECRET")
    if not cid or not secret:
        sys.exit("NAVER_CLIENT_ID·NAVER_CLIENT_SECRET이 없어요 (GitHub Secrets).")
    import requests
    session = requests.Session()
    old = []
    if os.path.exists(a.out):
        with open(a.out, encoding="utf-8") as f:
            old = [json.loads(x) for x in f if x.strip()]
    new, calls = [], 0
    for phrase in PHRASES:
        for word in TOPIC_WORDS:
            q = f"{phrase} {word}".strip()
            got = search(session, cid, secret, q, min(a.pages, 10))
            calls += 1
            new += got
            print(f"검색어 {calls:>3}: {len(got):>5}건")  # 건수만 (검색어도 찍지 않음)
    rows, added = merge(old, new)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(a.summary, "w", encoding="utf-8") as f:
        f.write(summary(rows))
    print(f"모은 기사 {len(new):,}건 → 새 기사 {added:,}건, 전체 {len(rows):,}건")


if __name__ == "__main__":
    main()
