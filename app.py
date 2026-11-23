"""사업보고서 분석기 — 사업·반기·분기보고서를 목차 부분별로 깊게 읽는 Streamlit 앱.

비밀값은 Streamlit Secrets에만: DART_API_KEY, GEMINI_API_KEY (선택: GEMINI_MODEL, GEMINI_FALLBACK_MODEL).
"""
import os

import requests
import streamlit as st

import analyses as an
import dart_client as dc
import points as pt
import report_parse as rp
import ui

LAST_UPDATED = "2026.11.23 15:38"
st.set_page_config(page_title="사업보고서 분석기", layout="wide")
ui.inject()


def load_secret(name):
    try:
        value = st.secrets[name]
        if value:
            return str(value)
    except Exception:
        pass
    return os.environ.get(name)


DART_KEY = load_secret("DART_API_KEY")
GEMINI_KEY = load_secret("GEMINI_API_KEY")
GEMINI_MODEL = load_secret("GEMINI_MODEL") or "gemini-3.6-flash"
GEMINI_FALLBACK = load_secret("GEMINI_FALLBACK_MODEL") or "gemini-3.5-flash-lite"


@st.cache_resource
def get_session():
    return requests.Session()


@st.cache_resource
def get_cache():
    return dc.Cache()


@st.cache_resource(ttl=24 * 3600, show_spinner=False)
def get_corps():
    return dc.load_corp_list(get_session())


@st.cache_resource(max_entries=12, show_spinner=False)
def get_parsed(rcept_no):
    """접수번호 -> 나눈 보고서 (원문은 dart_client 저장소에 일주일)."""
    text = dc.report_text(get_session(), get_cache(), DART_KEY, rcept_no)
    return rp.parse_report(text)


def filed_on(r):
    d = str(r.get("rcept_dt", ""))
    return f"{d[:4]}.{d[4:6]}.{d[6:8]}" if len(d) == 8 else d


def date_label(r):
    extra = f", 정정 {r['versions'] - 1}회" if r.get("versions", 1) > 1 else ""
    return f"{dc.strip_correction(r.get('report_nm'))}  (제출 {filed_on(r)}{extra})"


# ------------------------------------------------------------
ui.masthead(LAST_UPDATED)

if not DART_KEY:
    st.error("Streamlit Secrets에 DART_API_KEY를 넣어 주세요.")
    st.stop()

with st.form("pick_corp"):
    query = st.text_input("기업명 또는 종목코드", placeholder="예: 삼성전자, 005380")
    go = st.form_submit_button("보고서 찾기", type="primary")
if go:
    st.session_state.pop("corp", None)
    try:
        with st.spinner("기업 목록을 확인하는 중..."):
            cands = dc.find_corps(get_corps(), query)
    except Exception:
        st.error("기업 목록을 받지 못했어요. 잠시 후 다시 시도해 주세요.")
        cands = []
    if not cands and query.strip():
        st.warning(f"'{query}' 기업을 찾지 못했어요. 공시된 이름이나 종목코드 6자리로 입력해 보세요.")
    st.session_state["cands"] = cands

cands = st.session_state.get("cands") or []
if not cands:
    st.stop()
ci = 0
if len(cands) > 1:
    ci = st.radio("기업", range(len(cands)), horizontal=True,
                  format_func=lambda i: cands[i]["corp_name"] + (f" ({cands[i]['stock_code']})" if cands[i]["stock_code"] else " (비상장)"))
corp = cands[ci]

try:
    with st.spinner("정기보고서 목록을 불러오는 중..."):
        all_rows = dc.periodic_reports(get_session(), get_cache(), DART_KEY, corp["corp_code"])
except dc.DartApiError as e:
    st.error(str(e))
    st.stop()
rows = dc.latest_versions(all_rows)
if not rows:
    st.warning("최근 4년 안의 사업·반기·분기보고서가 없어요.")
    st.stop()
ri = st.selectbox("보고서", range(len(rows)), format_func=lambda i: date_label(rows[i]))
row = rows[ri]
rno = str(row["rcept_no"]).strip()
ui.cover(corp, dc.strip_correction(row.get("report_nm")), filed_on(row), row.get("versions", 1), None, dc.DART_VIEW_URL.format(rno))

try:
    with st.spinner("보고서 원문을 받아 목차별로 나누는 중... (처음 받는 보고서는 20~40초)"):
        parsed = get_parsed(rno)
except (dc.DartApiError, rp.ParseError) as e:
    st.error(str(e))
    st.stop()

tab_point, tab_toc, tab_ai, tab_diff, tab_multi = st.tabs(["기사 포인트", "목차별 보기", "AI 분석", "달라진 문장", "여러 회사 비교"])

# ---------------- 기사 포인트 (2단계에서 숫자 카드로) ----------------
with tab_point:
    year, reprt = pt.reprt_of(row)
    prev_row = dc.find_prev_periodic(rows, row)
    prev_parsed = None
    if prev_row:
        try:
            with st.spinner("1년 전 같은 기간 보고서도 받아 비교하는 중..."):
                prev_parsed = get_parsed(str(prev_row["rcept_no"]).strip())
        except (dc.DartApiError, rp.ParseError):
            prev_parsed = None
    memo = {}

    def api(name):
        if name not in memo:
            call = lambda url, params: dc.call_dart(get_session(), url, params)
            try:
                memo[name] = (pt.fetch_api(call, get_cache(), DART_KEY, name, corp["corp_code"], year, reprt),
                              pt.fetch_api(call, get_cache(), DART_KEY, name, corp["corp_code"], year - 1, reprt))
            except dc.DartApiError:
                memo[name] = (None, None)
        return memo[name]

    with st.spinner("기사 포인트 숫자를 모으는 중..."):
        items = pt.build_cards(parsed, prev_parsed, api if year else None, reprt or "11011")
    ui.note(f"직전 비교: {date_label(prev_row) if prev_row else '1년 전 같은 기간 보고서 없음'}. 숫자는 DART 구조화 자료와 원문 표에서만 가져와요 (AI 없음).")
    if items:
        ui.cards(items)
        cite = sorted({ln for c in items for ln in ([r[2] for r in c["rows"]] + c["lines"]) if ln})
        if cite:
            with st.expander(f"카드 근거 줄 원문 보기 ({len(cite)}곳)"):
                ui.legend(marker_text="카드가 가리킨 줄")
                ui.sheet(ui.around_rows(parsed["lines"], set(cite[:40]), width=2))
    else:
        st.info("이 보고서에서 카드로 만들 숫자를 찾지 못했어요. '목차별 보기'에서 원문을 확인해 주세요.")
    found = [(rp.REPORT_BLOCK_LABELS[k], rp.block_first_line(parsed, k)) for k in rp.REPORT_BLOCK_LABELS if k in parsed["blocks"]]
    missing = [rp.REPORT_BLOCK_LABELS[k] for k in rp.REPORT_BLOCK_LABELS if k not in parsed["blocks"]]
    with st.expander(f"이 보고서에서 찾은 부분 {len(found)}개 (원문 전체 {len(parsed['lines']):,}줄)"):
        ui.parts_list(found, missing)

# ---------------- 목차별 보기 ----------------
with tab_toc:
    keys = [k for k, _ in rp.REPORT_MAIN_SECTIONS if k in parsed["mains"]]
    mk = st.selectbox("목차", keys, format_func=lambda k: rp.MAIN_LABELS[k])
    i, j = parsed["mains"][mk]
    ui.note(f"원문 {i + 1:,}~{j:,}번째 줄")
    subs = [k for k in rp.REPORT_BLOCK_LABELS if (k.startswith(mk + "_") or k == mk) and k in parsed["blocks"]]
    notes = [k for k in rp.REPORT_NOTES if k in parsed["blocks"]] if mk == "fin" else []
    for k in subs + notes:
        with st.expander(f"{rp.REPORT_BLOCK_LABELS[k]} (줄 {rp.block_first_line(parsed, k)}~)"):
            ui.sheet(ui.numbered_rows(rp.block_text(parsed, k, numbered=True, cap=60000)))
    with st.expander("이 목차 전체 원문"):
        ui.sheet(ui.numbered_rows(rp.main_text(parsed, mk, numbered=True, cap=200000)))

# ---------------- AI 분석 ----------------
with tab_ai:
    if not GEMINI_KEY:
        st.info("AI 분석을 쓰려면 Streamlit Secrets에 GEMINI_API_KEY를 넣어 주세요.")
    else:
        ai = st.selectbox("분석 항목", range(len(an.PERIODIC_ANALYSES)), format_func=lambda k: an.PERIODIC_ANALYSES[k]["label"])
        spec = an.PERIODIC_ANALYSES[ai]
        st.caption(spec["help"])
        state_key = (rno, spec["key"])
        if st.button("분석하기", type="primary", key="ai_go"):
            body, read, missing, truncated = an.analysis_input(parsed, spec)
            res = dict(read=read, missing=missing, truncated=truncated, body=body, text="")
            if an.has_content(body):
                with st.spinner("해당 부분만 읽고 정리하는 중..."):
                    try:
                        prompt = an.build_prompt(corp["corp_name"], row, spec, body)
                        res["text"] = an.call_gemini(get_session(), GEMINI_KEY, GEMINI_MODEL, prompt, an.AI_PERIODIC_SYSTEM, GEMINI_FALLBACK)
                    except an.AiError as e:
                        st.error(str(e))
            st.session_state["ai_res"] = {"key": state_key, "res": res}
        saved = st.session_state.get("ai_res")
        if saved and saved["key"] == state_key:
            res = saved["res"]
            if res["text"]:
                ui.answer(res["text"])
                bad = an.unverified_numbers(res["text"], res["body"])
                if bad:
                    st.warning("AI가 읽은 발췌에 그대로 없는 숫자가 있어요: " + ", ".join(bad) + ". 단위를 바꿔 썼거나 잘못 옮긴 것일 수 있으니 원문으로 확인하세요.")
                cites = an.cited_lines(res["text"])
                if cites:
                    with st.expander(f"근거 줄 원문 보기 ({len(cites)}곳)"):
                        ui.legend(marker_text="AI가 근거로 든 줄")
                        ui.sheet(ui.around_rows(parsed["lines"], set(cites[:30])))
            elif not res["body"].strip() or not an.has_content(res["body"]):
                st.warning("이 보고서에는 해당 내용이 거의 없어요. (분기·반기보고서는 생략되는 항목이 많아요.)")
            notes = []
            if res["read"]:
                notes.append("읽은 부분: " + ", ".join(res["read"]))
            if res["missing"]:
                notes.append("못 찾은 부분: " + ", ".join(res["missing"]))
            if res["truncated"]:
                notes.append(f"길어서 앞 {an.MAX_REPORT_CHARS:,}자까지만 읽었어요")
            for n in notes:
                ui.note(n)

# ---------------- 달라진 문장 ----------------
with tab_diff:
    mode = st.radio("비교 대상", ["1년 전 같은 기간", "바로 앞 보고서"], horizontal=True)
    prev = dc.find_prev_periodic(rows, row) if mode.startswith("1년") else dc.find_prev_quarter(rows, row)
    if not prev:
        st.info("비교할 보고서가 목록(최근 4년)에 없어요.")
    else:
        ui.note(f"비교 대상: {date_label(prev)}")
        try:
            with st.spinner("직전 보고서를 받아 비교하는 중..."):
                prev_parsed = get_parsed(str(prev["rcept_no"]).strip())
        except (dc.DartApiError, rp.ParseError) as e:
            st.error(str(e))
            prev_parsed = None
        if prev_parsed:
            diffs, missing = an.report_diff(prev_parsed, parsed)
            if not diffs:
                st.success("비교한 부분에서 문장이 바뀐 곳이 없어요. (숫자만 바뀐 줄은 뺐어요.)")
            if diffs:
                ui.legend(marker_text="이번에 새로 생긴 문장 (이번 보고서 줄 번호)", red_text="이번에 없어진 문장 (직전 보고서 줄 번호)")
            for d in diffs:
                with st.expander(f"{d['label']}: 새 문장 {len(d['added'])}개, 없어진 문장 {len(d['removed'])}개"):
                    ui.sheet([(n, s, "mark") for n, s in d["added"][:200]] + [(f"직전 {n}", s, "gone") for n, s in d["removed"][:200]])
            if missing:
                ui.note("한쪽 보고서에 없어 비교하지 못한 부분: " + ", ".join(missing))
            if diffs and GEMINI_KEY and st.button("AI로 의미 있는 변화만 고르기", key="diff_ai"):
                body, truncated = an.diff_input(diffs)
                with st.spinner("변화를 고르는 중..."):
                    try:
                        prompt = an.build_prompt(corp["corp_name"], row, an.DIFF_SPEC, body, prev)
                        ui.answer(an.call_gemini(get_session(), GEMINI_KEY, GEMINI_MODEL, prompt, an.AI_PERIODIC_SYSTEM,
                                                 GEMINI_FALLBACK))
                    except an.AiError as e:
                        st.error(str(e))
                if truncated:
                    ui.note(f"바뀐 문장이 많아 앞 {an.MAX_REPORT_CHARS:,}자까지만 AI에 보냈어요.")

# ---------------- 여러 회사 비교 (4단계) ----------------
with tab_multi:
    st.info("여러 회사를 한 지표로 나란히 놓는 표(연봉 순위, 가동률 비교 등)는 4단계에서 이 자리에 들어와요.")
