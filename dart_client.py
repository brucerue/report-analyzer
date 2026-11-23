"""OpenDART 호출 · 원문 받기 · 기업 찾기 · 보고서 목록.

산업 취재 도우미(DART-Joongang app.py)의 call_dart · doc_text_from_zip · download_document · periodic_reports ·
find_prev_periodic · strip_correction을 옮겨 왔다. Streamlit에 기대지 않는다 (키·세션·저장소는 인자로 받음).
"""
import html
import io
import re
import time
import zipfile
from datetime import date

DART_VIEW_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={}"
DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
DART_DOC_URL = "https://opendart.fss.or.kr/api/document.xml"
CORP_LIST_URL = "https://raw.githubusercontent.com/brucerue/DART-Joongang/corp-codes/corp_codes.csv"  # 공개, 토큰 불필요
REQUEST_TIMEOUT = 20
DOC_TIMEOUT = 60
REPORT_KINDS = ("사업보고서", "반기보고서", "분기보고서")


class DartApiError(Exception):
    """DART 서버 오류·호출 한도 초과·원문 없음 등 — 화면에 그대로 보여 준다."""


# ------------------------------------------------------------
# 간단한 저장소 (같은 요청을 다시 보내지 않게). 앱에서는 st.cache_resource로 하나를 공유한다.
# ------------------------------------------------------------
class Cache:
    def __init__(self, max_items=500):
        self.store, self.max_items = {}, max_items

    def get(self, key, ttl):
        hit = self.store.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        return None

    def put(self, key, value):
        if len(self.store) >= self.max_items:
            self.store.clear()
        self.store[key] = (time.time(), value)
        return value


DAY = 24 * 3600


def call_dart(session, url, params):
    """정상이면 dict, 조회 결과 없음(013)이면 None, 그 밖은 DartApiError. 일시 오류는 두 번 더 시도."""
    jo, last = None, None
    for attempt in range(3):
        try:
            jo = session.get(url, params=params, timeout=REQUEST_TIMEOUT).json()
            break
        except Exception as e:
            last = e
            time.sleep(0.5 * (attempt + 1))
    if jo is None:
        raise DartApiError("DART 서버 응답이 없거나 늦어지고 있어요. 잠시 후 다시 시도해 주세요.") from last
    status = str(jo.get("status", ""))
    if "list" in jo or status == "000":
        return jo
    if status == "013":
        return None
    if status == "020":
        raise DartApiError("DART API 하루 호출 한도를 넘었어요. 내일 다시 시도해 주세요.")
    if status in ("010", "011", "012", "901"):
        raise DartApiError(f"DART API 키를 확인해 주세요 (Streamlit Secrets의 DART_API_KEY). [{status}]")
    raise DartApiError(f"DART 응답 오류 [{status}] {jo.get('message', '')}".strip())


# ------------------------------------------------------------
# 보고서 이름
# ------------------------------------------------------------
def strip_correction(name):
    """[기재정정]·[첨부정정] 같은 앞머리를 뗀 보고서명."""
    return re.sub(r"^\s*(\[[^\]]*\]\s*)+", "", str(name or "")).strip()


def is_correction(name):
    return bool(re.match(r"^\s*\[[^\]]*정정[^\]]*\]", str(name or "")))


def report_period_of(name):
    """'사업보고서 (2025.12)' -> (2025, 12) 또는 None."""
    m = re.search(r"\((\d{4})\.(\d{2})\)", str(name or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def report_kind_of(name):
    """'[기재정정]반기보고서 (2025.06)' -> '반기보고서'."""
    return re.sub(r"\s*\(\d{4}\.\d{2}\)\s*$", "", strip_correction(name)).strip()


def latest_versions(rows):
    """같은 보고서(종류+기간)의 정정본이 여럿이면 가장 늦게 낸 것만 남긴다. 각 행에 'versions'(낸 횟수)를 붙인다. 최신순."""
    groups = {}
    for r in rows:
        key = (report_kind_of(r.get("report_nm")), report_period_of(r.get("report_nm")))
        groups.setdefault(key, []).append(r)
    out = []
    for items in groups.values():
        last = max(items, key=lambda r: str(r.get("rcept_no", "")))
        out.append(dict(last, versions=len(items)))
    return sorted(out, key=lambda r: (str(r.get("rcept_dt", "")), str(r.get("rcept_no", ""))), reverse=True)


def find_prev_periodic(rows, cur):
    """1년 전 같은 기간·같은 종류 보고서 (정정본이 여럿이면 가장 늦은 것). 없으면 None."""
    per = report_period_of(cur.get("report_nm"))
    if not per:
        return None
    want, kind = (per[0] - 1, per[1]), report_kind_of(cur.get("report_nm"))
    cands = [r for r in rows if report_period_of(r.get("report_nm")) == want and report_kind_of(r.get("report_nm")) == kind]
    return max(cands, key=lambda r: str(r.get("rcept_no", ""))) if cands else None


def find_prev_quarter(rows, cur):
    """바로 앞 정기보고서 (예: 2025.09 분기 -> 2025.06 반기, 2025.12 사업 -> 2025.09 분기). 없으면 None."""
    per = report_period_of(cur.get("report_nm"))
    if not per:
        return None
    y, m = per
    want = (y, m - 3) if m > 3 else (y - 1, 12)
    cands = [r for r in rows if report_period_of(r.get("report_nm")) == want
             and any(k in report_kind_of(r.get("report_nm")) for k in REPORT_KINDS)]
    return max(cands, key=lambda r: str(r.get("rcept_no", ""))) if cands else None


# ------------------------------------------------------------
# 보고서 목록 · 원문
# ------------------------------------------------------------
def periodic_reports(session, cache, api_key, corp_code, years=4, today=None):
    """기업의 최근 약 4년 사업·반기·분기보고서 (정정본 포함, 최신순). 하루 저장."""
    key = ("periodic", corp_code, years)
    hit = cache.get(key, DAY / 4)
    if hit is not None:
        return hit
    today = today or date.today()
    start = today.replace(year=today.year - years)
    rows, page = [], 1
    while True:
        jo = call_dart(session, DART_LIST_URL, {
            "crtfc_key": api_key, "corp_code": corp_code, "bgn_de": start.strftime("%Y%m%d"), "end_de": today.strftime("%Y%m%d"),
            "pblntf_ty": "A", "last_reprt_at": "N", "page_no": page, "page_count": 100})
        if not jo:
            break
        rows += jo.get("list") or []
        if page >= int(jo.get("total_page") or 1) or page >= 10:
            break
        page += 1
    out = [r for r in rows if any(k in strip_correction(r.get("report_nm")) for k in REPORT_KINDS) and str(r.get("rcept_no", "")).strip()]
    out.sort(key=lambda r: (str(r.get("rcept_dt", "")), str(r.get("rcept_no", ""))), reverse=True)
    return cache.put(key, out)


def _one_line_row(m):
    row = re.sub(r"(?i)</?(P|BR|SPAN|TABLE-GROUP)\b[^>]*>", " ", m.group(0))
    return re.sub(r"\s+", " ", row)


def doc_text_from_zip(data):
    """DART 원본파일 zip -> 글. 표는 칸을 ' | ', 줄을 줄바꿈으로. 본문(가장 짧은 .xml 이름)이 맨 앞, 첨부는 빈 줄 뒤."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise DartApiError("DART 원문 파일을 열 수 없어요. 잠시 후 다시 시도해 주세요.") from e
    names = sorted(zf.namelist(), key=lambda n: (not n.endswith(".xml"), len(n), n))
    parts = []
    for name in names:
        raw, text = zf.read(name), None
        for enc in ("utf-8", "cp949"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                pass
        if text is None:
            continue
        text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
        text = re.sub(r"(?is)<TR\b.*?</TR>", _one_line_row, text)  # 표 한 행 = 한 줄 (칸 사이 줄바꿈·문단 태그를 없앤다)
        text = re.sub(r"(?i)</(TD|TH|TE|TU)>", " | ", text)
        text = re.sub(r"(?i)</(TR|P|TITLE|TABLE|LIBRARY|SECTION-\d+|BR)\s*>|<BR\s*/?>", "\n", text)
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
        text = re.sub(r"[ \t ]+", " ", text)
        text = re.sub(r"\s*\n\s*", "\n", text).strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def download_document(session, api_key, rcept_no):
    """접수번호 -> 원본파일 zip 바이트. 없거나 오류면 DartApiError."""
    try:
        res = session.get(DART_DOC_URL, params={"crtfc_key": api_key, "rcept_no": rcept_no}, timeout=DOC_TIMEOUT)
    except Exception as e:
        raise DartApiError("DART 서버 응답이 없거나 늦어지고 있어요. 잠시 후 다시 시도해 주세요.") from e
    data = res.content or b""
    if not data.startswith(b"PK"):
        msg = data.decode("utf-8", "ignore")
        m = re.search(r"<status>(\d+)</status>", msg) or re.search(r'"status"\s*:\s*"(\d+)"', msg)
        code = m.group(1) if m else "?"
        if code in ("013", "014"):
            raise DartApiError("DART에 이 보고서의 원문 파일이 아직 없어요. 잠시 후 다시 시도하거나 원문 링크로 보세요.")
        if code == "020":
            raise DartApiError("DART API 하루 호출 한도를 넘었어요. 내일 다시 시도해 주세요.")
        raise DartApiError(f"DART 원문을 받지 못했어요. [{code}]")
    return data


def report_text(session, cache, api_key, rcept_no):
    """접수번호 -> 원문 글 (일주일 저장: 같은 보고서는 다시 받지 않아 하루 호출 한도를 아낀다)."""
    key = ("doc", rcept_no)
    hit = cache.get(key, 7 * DAY)
    if hit is not None:
        return hit
    text = doc_text_from_zip(download_document(session, api_key, rcept_no))
    if not text:
        raise DartApiError("원문에서 글자를 찾지 못했어요. 원문 링크로 보세요.")
    return cache.put(key, text)


# ------------------------------------------------------------
# 기업 찾기 (DART-Joongang corp-codes 브랜치의 전체 기업 목록 CSV)
# ------------------------------------------------------------
def parse_corp_csv(text):
    """CSV 글 -> [{corp_code, corp_name, stock_code}] (상장사 먼저)."""
    import csv
    rows = [r for r in csv.DictReader(io.StringIO(text)) if r.get("corp_code") and r.get("corp_name")]
    rows.sort(key=lambda r: (not str(r.get("stock_code") or "").strip(), r["corp_name"]))
    return [{"corp_code": r["corp_code"].strip(), "corp_name": r["corp_name"].strip(),
             "stock_code": str(r.get("stock_code") or "").strip()} for r in rows]


def load_corp_list(session):
    res = session.get(CORP_LIST_URL, timeout=(10, 60))
    res.raise_for_status()
    return parse_corp_csv(res.content.decode("utf-8"))


def _norm(s):
    return re.sub(r"\s+", "", str(s or "")).casefold()


def find_corps(corps, query, limit=8):
    """기업명·종목코드 -> 후보 목록 (정확히 같은 이름 -> 이름으로 시작 -> 이름에 포함, 같은 단계에선 상장사 먼저)."""
    q = _norm(query)
    if not q:
        return []
    if q.isdigit():
        return [c for c in corps if c["stock_code"] == q.zfill(6) or c["corp_code"] == q.zfill(8)][:limit]
    exact = [c for c in corps if _norm(c["corp_name"]) == q]
    starts = [c for c in corps if _norm(c["corp_name"]).startswith(q) and c not in exact]
    inside = [c for c in corps if q in _norm(c["corp_name"]) and c not in exact and c not in starts]
    listed = lambda xs: [c for c in xs if c["stock_code"]] + [c for c in xs if not c["stock_code"]]
    return (listed(exact) + listed(starts) + listed(inside))[:limit]
