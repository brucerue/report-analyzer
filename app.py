"""사업보고서 분석기 — 사업·반기·분기보고서를 목차 부분별로 깊게 읽는 Streamlit 앱.

비밀값은 Streamlit Secrets에만: DART_API_KEY, GEMINI_API_KEY (선택: GEMINI_MODEL, GEMINI_FALLBACK_MODEL, PAPER_PRIVATE_READ_TOKEN — 문체 파일 읽기 전용).
"""
import json
import os
import re

import requests
import streamlit as st

import analyses as an
import article as art
import compare as cp
import dart_client as dc
import plant
import points as pt
import report_parse as rp
import ui

LAST_UPDATED = "2026.11.24 04:30"
st.set_page_config(page_title="사업보고서 분석기", page_icon=os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.png"), layout="wide")
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
STYLE_TOKEN = load_secret("PAPER_PRIVATE_READ_TOKEN")  # 문체 파일(paper-private) 읽기 전용


@st.cache_resource
def get_session():
    return requests.Session()


@st.cache_resource
def get_cache():
    return dc.Cache()


@st.cache_resource(ttl=24 * 3600, show_spinner=False)
def get_corps():
    return dc.load_corp_list(get_session())


@st.cache_resource
def _parsed_store():
    return dc.Cache(max_items=12)  # 나눈 보고서 (원문은 dart_client가 메모리·디스크에 일주일)


class _Parsed:
    def get(self, rno):
        return _parsed_store().get(("parsed", rno), 7 * 24 * 3600)

    def put(self, rno, v):
        return _parsed_store().put(("parsed", rno), v)


PARSED = _Parsed()


def get_parsed(rcept_no):
    """접수번호 -> 나눈 보고서 (여러 회사 비교에서 씀. 진행 표시 없이)."""
    hit = PARSED.get(rcept_no)
    if hit is None:
        hit = PARSED.put(rcept_no, rp.parse_report(dc.report_text(get_session(), get_cache(), DART_KEY, rcept_no)))
    return hit


def filed_on(r):
    d = str(r.get("rcept_dt", ""))
    return f"{d[:4]}.{d[4:6]}.{d[6:8]}" if len(d) == 8 else d


def period_phrase(r):
    """보고서 -> 기사 기간 표현: 사업 '2025년', 반기 '2026년 상반기', 1분기 '2026년 1분기', 3분기 '2026년 1∼9월'."""
    per, kind = dc.report_period_of(r.get("report_nm")), dc.report_kind_of(r.get("report_nm"))
    if not per:
        return "이번 기간"
    y, m = per
    if "사업" in kind:
        return f"{y}년"
    return {6: f"{y}년 상반기", 3: f"{y}년 1분기", 9: f"{y}년 1∼9월"}.get(m, f"{y}년 {m}월까지")


def date_label(r):
    extra = f", 정정 {r['versions'] - 1}회" if r.get("versions", 1) > 1 else ""
    return f"{dc.strip_correction(r.get('report_nm'))}  (제출 {filed_on(r)}{extra})"


# ------------------------------------------------------------
ui.masthead(LAST_UPDATED)

if not DART_KEY:
    st.error("Streamlit Secrets에 DART_API_KEY를 넣어 주세요.")
    st.stop()

MODE_ONE, MODE_MULTI = "회사 하나 깊게 보기", "여러 회사 비교"
mode = st.radio("보기", [MODE_ONE, MODE_MULTI], horizontal=True, label_visibility="collapsed", key="mode")


def fill_group():
    g = st.session_state.get("multi_group")
    if g and g in cp.INDUSTRY_GROUPS:
        st.session_state["multi_names"] = ", ".join(cp.INDUSTRY_GROUPS[g])


def pick_report(rows_all, kind_name, year):
    """회사 보고서 목록에서 고른 종류·연도 보고서 (정정본이면 가장 늦은 것). 없으면 None."""
    _, month = cp.KINDS[kind_name]
    want_kind = "사업보고서" if kind_name == "사업보고서" else "반기보고서" if kind_name == "반기보고서" else "분기보고서"
    for r in dc.latest_versions(rows_all):
        if dc.report_kind_of(r.get("report_nm")) == want_kind and dc.report_period_of(r.get("report_nm")) == (year, month):
            return r
    return None


def render_multi():
    """여러 회사를 같은 기간·같은 지표로 한 표에. 숫자는 DART 자료·원문 표에서만 (AI 없음)."""
    from datetime import date
    this_year = date.today().year
    st.selectbox("업종 묶음으로 채우기 (산업 취재 도우미와 같은 묶음)", ["직접 입력"] + list(cp.INDUSTRY_GROUPS),
                 key="multi_group", on_change=fill_group)
    with st.form("multi_form"):
        names = st.text_area("회사 이름 (쉼표나 줄바꿈으로, 최대 12곳)", key="multi_names", height=90,
                             placeholder="예: 삼성전자, SK하이닉스, LG전자")
        c1, c2 = st.columns(2)
        kind_name = c1.selectbox("보고서", list(cp.KINDS), key="multi_kind")
        year = c2.selectbox("사업연도", list(range(this_year, this_year - 5, -1)), index=1, key="multi_year")
        with_doc = st.checkbox("원문 표 지표도 (R&D 비율·가동률·해외 매출 비중) — 회사마다 원문을 받아 1곳에 20~40초 걸려요", key="multi_doc")
        go_multi = st.form_submit_button("비교하기", type="primary")
    if go_multi:
        try:
            corps_all = get_corps()
        except Exception:
            st.error("기업 목록을 받지 못했어요. 잠시 후 다시 시도해 주세요.")
            return
        found, missing = cp.resolve(corps_all, cp.split_names(names))
        if missing:
            st.warning("못 찾은 회사: " + ", ".join(missing) + " (공시된 이름으로 적어 주세요)")
        if not found:
            st.error("비교할 회사를 찾지 못했어요.")
            return
        reprt = cp.KINDS[kind_name][0]
        call = lambda url, params: dc.call_dart(get_session(), url, params)
        fetch = lambda api, code, y, r: pt.fetch_api(call, get_cache(), DART_KEY, api, code, y, r)
        fin_fetch = lambda code, y, r: pt.fetch_fin(call, get_cache(), DART_KEY, code, y, r)
        with st.spinner(f"{len(found)}곳의 DART 자료를 모으는 중..."):
            rows = cp.collect(fetch, found, year, reprt, fin_fetch=fin_fetch)
        if with_doc:
            bar = st.progress(0.0, text="원문을 받는 중...")
            for i, (r, (_, c)) in enumerate(zip(rows, found)):
                bar.progress(i / len(found), text=f"원문을 받는 중... {c['corp_name']} ({i + 1}/{len(found)})")
                try:
                    rep_row = pick_report(dc.periodic_reports(get_session(), get_cache(), DART_KEY, c["corp_code"]), kind_name, year)
                    if rep_row:
                        r.update(cp.doc_metrics(get_parsed(str(rep_row["rcept_no"]).strip())))
                        r["rcept_no"] = rep_row["rcept_no"]
                except (dc.DartApiError, rp.ParseError) as e:
                    r["error"] = (r.get("error") or "") + f" 원문: {e}"
            bar.empty()
        st.session_state["multi_res"] = dict(rows=rows, year=year, kind=kind_name, doc=with_doc)
    res = st.session_state.get("multi_res")
    if not res:
        ui.note("회사 이름을 넣고 '비교하기'를 누르세요. 업종 묶음을 고르면 이름이 채워져요.")
        return
    rows = res["rows"]
    keys_all = [m[0] for m in cp.METRICS if res["doc"] or not m[4]]
    have = [k for k in keys_all if any(r.get(k) is not None for r in rows)]
    default = [k for k in ("rev", "rev_chg", "op", "op_margin", "emp", "emp_chg", "pay", "pay_chg", "top_pay", "holder", "minor", "div", "debt_ratio", "capex", "rnd", "util", "abroad") if k in have]
    shown = st.multiselect("보여 줄 지표", have, default=default, format_func=lambda k: cp.METRIC_BY_KEY[k][1], key="multi_keys")
    if not shown:
        return
    sort_key = st.selectbox("순위 기준", shown, format_func=lambda k: cp.METRIC_BY_KEY[k][1], key="multi_sort")
    ordered = sorted(rows, key=lambda r: (r.get(sort_key) is None, -(r.get(sort_key) or 0)))
    period = f"{res['year']}년 {res['kind']}"
    ui.note(f"{period} 기준 · 표 머리를 누르면 다시 정렬돼요 · 금액은 만원·억원")
    if any(k in shown for k in ("pay", "pay_chg")):
        ui.note("1인 평균 급여는 보고서의 성별·부문별 '1인 평균 급여액'을 직원 수로 가중 평균한 값이에요 (기사들이 쓰는 방식. 회사가 원문에 적은 전체 평균과 수십만 원 다를 수 있어요).")
    if res["kind"] != "사업보고서" and any(k in shown for k in ("pay", "pay_chg")):
        ui.note("반기·분기 급여는 그 기간 누적이에요. 증감률은 1년 전 같은 기간 보고서와 비교한 값이에요.")
    table = cp.table_rows(ordered, shown)
    num_cols = {k for row in table for k, v in row.items() if isinstance(v, (int, float))}
    config = {k: st.column_config.NumberColumn(k, format="%.1f" if ("률" in k or "지분" in k or "비율" in k or "비중" in k or "가동률" in k or "근속" in k) else "localized")
              for k in num_cols}
    st.dataframe(table, hide_index=True, width="stretch", column_config=config)
    import csv, io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list({k: None for row in table for k in row}))
    w.writeheader()
    w.writerows(table)
    st.download_button("표 내려받기 (CSV)", buf.getvalue().encode("utf-8-sig"), file_name=f"비교_{period}.csv", mime="text/csv")
    lines = [s for s in (cp.rank_sentence(rows, k) for k in [sort_key] + [k for k in shown if k != sort_key]) if s]
    if lines:
        ui.note("순위 문장 (숫자로만 만든 초안 · 오른쪽 위 단추로 복사)")
        st.code("\n".join([f"({period} 기준) " + lines[0]] + lines[1:]), language=None, wrap_lines=True)


if mode == MODE_MULTI:
    render_multi()
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

def load_parsed(rcept_no, label):
    """원문을 받아 나눈다. 받는 동안 진행 표시 (90초를 넘기면 dart_client가 끊고 DartApiError). -> (parsed, 오류 글)"""
    hit = PARSED.get(rcept_no)
    if hit is not None:
        return hit, None
    bar = st.progress(0.0, text=f"{label} 원문을 받는 중...")

    def progress(nbytes, spent):
        bar.progress(min(spent / dc.DOC_DEADLINE, 0.99), text=f"{label} 원문을 받는 중... {nbytes / 1e6:.1f}MB · {spent:.0f}초 (90초를 넘기면 멈춰요)")

    try:
        text = dc.report_text(get_session(), get_cache(), DART_KEY, rcept_no, progress=progress)
        parsed = rp.parse_report(text)
    except (dc.DartApiError, rp.ParseError) as e:
        bar.empty()
        return None, str(e)
    bar.empty()
    PARSED.put(rcept_no, parsed)
    return parsed, None


tab_point, tab_write, tab_toc, tab_ai, tab_diff = st.tabs(["기사 포인트", "기사 쓰기", "목차별 보기", "AI 분석", "달라진 문장"])
PERIOD = period_phrase(row)
year, reprt = pt.reprt_of(row)
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


def fin_api():
    if "fin" not in memo:
        try:
            frows, fs = pt.fetch_fin(lambda url, params: dc.call_dart(get_session(), url, params), get_cache(), DART_KEY,
                                     corp["corp_code"], year, reprt)
        except dc.DartApiError:
            frows, fs = [], None
        memo["fin"] = dict(pt.fin_stats(frows), fs="연결" if fs == "CFS" else "별도") if frows else None
        if memo["fin"] and reprt in ("11012", "11013", "11014"):  # 직전 분기 3개월 (QoQ)
            def rows_of(y, r):
                try:
                    return pt.fetch_fin(lambda url, params: dc.call_dart(get_session(), url, params), get_cache(), DART_KEY,
                                        corp["corp_code"], y, r)[0]
                except dc.DartApiError:
                    return []
            memo["fin"]["prevq"] = pt.prev_quarter(rows_of, year, reprt)
    return memo["fin"]


# ---------------- 기사 포인트: 1) DART 자료로 바로 나오는 카드 ----------------
with tab_point:
    prev_row = dc.find_prev_periodic(rows, row)
    ui.note(f"직전 비교: {date_label(prev_row) if prev_row else '1년 전 같은 기간 보고서 없음'}. 숫자는 DART 재무제표·구조화 자료와 원문 표에서만 가져와요 (AI 없음). "
            "비교 기준: 실적·시설투자·가동률·R&D 같은 기간 값은 전년 동기, 부채·현금·최대주주 지분은 지난해 말, 직원·소액주주는 1년 전 같은 시점, 분기 실적은 직전 분기도 함께.")
    with st.spinner("DART 자료로 숫자를 모으는 중..."):
        fast = pt.build_cards(None, None, api if year else None, reprt or "11011", fin_api if year else None, part="fast", period=PERIOD)
    if fast:
        ui.cards(fast)
    doc_area = st.container()

# ---------------- 2) 원문을 받아 나머지 ----------------
with doc_area:
    parsed, doc_err = load_parsed(rno, "이번 보고서")
    prev_parsed, items = None, []
    if parsed is not None and prev_row:
        prev_parsed, _ = load_parsed(str(prev_row["rcept_no"]).strip(), "1년 전 같은 기간 보고서")
    if parsed is None:
        st.error(doc_err)
    else:
        items = pt.build_cards(parsed, prev_parsed, None, reprt or "11011", None, part="doc", period=PERIOD)
        if items:
            ui.cards(items)
        cite = sorted({ln for c in fast + items for ln in ([r[2] for r in c["rows"]] + c["lines"]) if ln})
        if cite:
            with st.expander(f"카드 근거 줄 원문 보기 ({len(cite)}곳)"):
                ui.legend(marker_text="카드가 가리킨 줄")
                ui.sheet(ui.around_rows(parsed["lines"], set(cite[:40]), width=2))
        if not fast and not items:
            st.info("이 보고서에서 카드로 만들 숫자를 찾지 못했어요. '목차별 보기'에서 원문을 확인해 주세요.")
        pres = plant.compare(parsed, prev_parsed)
        if pres["sets"]:
            st.markdown("#### 공장별 가동률")
            ui.note("보고서의 '생산능력 | 생산실적 | 가동률' 표를 읽었어요. 1년 전은 같은 기간 보고서의 같은 공장끼리 비교해요.")
            for one in pres["sets"]:
                ui.plant_table(one)
            ui.note("가동률 기사 문장은 '기사 쓰기' 탭에서 다른 요소와 함께 엮을 수 있어요.")
        found = [(rp.REPORT_BLOCK_LABELS[k], rp.block_first_line(parsed, k)) for k in rp.REPORT_BLOCK_LABELS if k in parsed["blocks"]]
        missing = [rp.REPORT_BLOCK_LABELS[k] for k in rp.REPORT_BLOCK_LABELS if k not in parsed["blocks"]]
        with st.expander(f"이 보고서에서 찾은 부분 {len(found)}개 (원문 전체 {len(parsed['lines']):,}줄)"):
            ui.parts_list(found, missing)


# ---------------- 목차별 보기 ----------------
def render_toc(parsed):
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
def render_ai(parsed):
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
def render_diff(parsed):
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


# ---------------- 기사 쓰기: 고른 요소를 리드부터 엮어 초안 ----------------
def marked(text):
    """【확인 필요】·'OO일' 자리를 형광펜으로 (HTML)."""
    import html as _h
    t = _h.escape(text)
    t = re.sub(r"(【[^】]*】|OO일)", r'<mark style="background:#EEF36A">\1</mark>', t)
    return "<div style='white-space:pre-wrap;line-height:1.75;font-size:15px'>" + t + "</div>"


def copy_button(text, label):
    """클립보드 복사 단추 (st.html + 자바스크립트). 브라우저가 막으면 아래 글 오른쪽 위 단추로 복사하라고 안내."""
    import html as _h
    import hashlib
    uid = "cp" + hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
    st.html(
        f"""<textarea id="{uid}t" style="position:absolute;left:-9999px" readonly>{_h.escape(text)}</textarea>
<button id="{uid}b" style="font:600 14px sans-serif;padding:8px 16px;border:0;border-radius:6px;background:#24479A;color:#fff;cursor:pointer">{_h.escape(label)}</button>
<span id="{uid}m" style="font:13px sans-serif;color:#555;margin-left:10px"></span>
<script>
(function() {{
  const b = document.getElementById('{uid}b');
  if (!b) return;
  b.onclick = async () => {{
    const t = document.getElementById('{uid}t'), m = document.getElementById('{uid}m');
    let ok = false;
    try {{ await navigator.clipboard.writeText(t.value); ok = true; }} catch (e) {{
      try {{ t.select(); ok = document.execCommand('copy'); }} catch (e2) {{}}
    }}
    m.textContent = ok ? '복사했어요. claude.ai 대화창에 붙여 넣으세요.' : '브라우저가 막았어요. 아래 글 오른쪽 위 단추로 복사하세요.';
  }};
}})();
</script>""", unsafe_allow_javascript=True)


def render_frame(all_cards, picked, lead, rno):
    """문체 틀: 문체 규칙(paper-private) + 예문 + 고른 요소의 숫자 -> Gemini 작성 -> 규칙 점검.
    Gemini 대신 claude.ai 등에 직접 붙여 넣을 수 있게 같은 재료를 한 덩어리로도 보여 준다(API 비용 없음)."""
    import style as sty
    st.markdown("#### 문체 틀 만들기 (중앙일보 산업부 문체)")
    ui.note("바로 출고할 기사가 아니라 기자가 채워 넣을 틀이에요. 날짜는 'OO일', 원인·전망은 【확인 필요】로 비워 둬요.")
    try:
        style = sty.load(get_session(), STYLE_TOKEN)
    except sty.StyleError as e:
        st.warning(f"문체 파일을 읽지 못했어요: {e}")
        return
    kind = st.radio("① 기사 유형", list(art.KINDS), format_func=lambda k: f"{art.KINDS[k][0]} (약 {art.KINDS[k][1]:,}자)",
                    horizontal=True, key="f_kind")
    how = st.radio("② 만드는 방법", ["Claude에 붙여 넣을 재료 받기 (추천)", "앱에서 바로 만들기 (Gemini 무료)"], horizontal=True, key="f_how")
    data = art.facts(all_cards, picked, lead, corp["corp_name"], dc.strip_correction(row.get("report_nm")), str(row.get("rcept_dt", "")))
    if how.startswith("Claude"):
        ui.note("'재료 전체 복사'를 누르고 claude.ai 대화창에 그대로 붙여 넣으세요. 문체 규칙·예문·숫자 자료·지시가 다 들어 있어서 "
                "Claude가 틀을 쓰고 스스로 규칙 점검까지 해요. (이 앱은 AI를 부르지 않아요)")
        bundle = art.paste_bundle(style["rules"], sty.examples_for(style, kind), kind, data)
        copy_button(bundle, "재료 전체 복사")
        st.code(bundle, language=None, wrap_lines=True)
        return
    ui.note("'틀 만들기'를 누르면 Gemini를 두 번(작성 → 규칙 점검) 불러요. 1분 안팎 걸리고, 결과 숫자를 고른 요소의 값과 대조해요.")
    with st.expander("참고: AI에 넘기는 숫자 자료"):
        st.json(data, expanded=False)
    if not GEMINI_KEY:
        ui.note("Streamlit Secrets에 GEMINI_API_KEY를 넣어야 쓸 수 있어요. 지금은 '② 만드는 방법'에서 Claude 쪽을 고르세요.")
        return

    def ask(prompt, system):
        return an.call_gemini(get_session(), GEMINI_KEY, GEMINI_MODEL, prompt, system, GEMINI_FALLBACK)
    if st.button("틀 만들기", type="primary", key="f_go"):
        with st.spinner("쓰는 중... (작성 → 규칙 점검, 1분 안팎)"):
            src = art.pct0(json.dumps(data, ensure_ascii=False)) + "\n" + json.dumps(data, ensure_ascii=False)
            try:
                system, prompt = art.write_prompt(style["rules"], sty.examples_for(style, kind), kind, data)
                first = ask(prompt, system)
            except an.AiError as e:
                first = None
                st.error(str(e))
            if first:
                try:
                    system2, prompt2 = art.check_prompt(style["rules"], first)
                    body, fixes = art.split_check(ask(prompt2, system2))
                    st.session_state["f_out"] = dict(rno=rno, kind=kind, first=first, body=art.pct0(body) or first, fixes=fixes, src=src, data=data)
                except an.AiError as e:  # 점검에서 한도에 걸려도 첫 초안은 살린다
                    st.warning(f"규칙 점검은 못 했어요 — {e} 아래는 점검 전 첫 초안이에요.")
                    st.session_state["f_out"] = dict(rno=rno, kind=kind, first=first, body=art.pct0(first), fixes=[], src=src, unchecked=True, data=data)
    out = st.session_state.get("f_out")
    if out and out["rno"] == rno:
        n, goal = art.body_chars(out["body"]), art.KINDS[out["kind"]][1]
        ui.note(f"본문 {n:,}자 / 목표 약 {goal:,}자" + (" — 목표보다 100자 넘게 길어요." if n - goal > 100 else
                                                        (" — 사실이 모자라 짧아요(억지로 채우지 않음)." if goal - n > 100 else "")))
        fake_q = art.unverified_quotes(out["body"], out.get("data") or {})
        if fake_q:
            st.warning("숫자 자료에 없는 인용(큰따옴표)이 있어요 — 지어낸 말일 수 있어요: " + " / ".join(f"“{q}”" for q in fake_q) + ". 빼거나 실제 발언으로 바꿔 주세요.")
        bad = an.unverified_numbers(out["body"], out["src"])
        if bad:
            st.warning("숫자 자료에 없는 숫자가 있어요: " + ", ".join(bad) + ". 고치거나 빼 주세요.")
        else:
            ui.note("틀의 숫자는 모두 숫자 자료에 있어요.")
        st.html(marked(out["body"]))
        st.code(out["body"], language=None, wrap_lines=True)
        if out.get("unchecked"):
            ui.note("규칙 점검 전 초안이에요. 한도가 풀리면 '틀 만들기'를 다시 누르면 점검까지 해요.")
        with st.expander(f"규칙 점검에서 고친 곳 ({len(out['fixes'])})"):
            st.markdown("\n".join(f"- {x}" for x in out["fixes"]) or "고친 곳 없음")
        with st.expander("점검 전 첫 초안"):
            st.code(out["first"], language=None, wrap_lines=True)

with tab_write:
    all_cards = fast + items
    opts = art.choices(all_cards)
    if not opts:
        st.info("기사로 엮을 숫자가 아직 없어요. '기사 포인트' 탭에서 카드가 나오는지 확인해 주세요.")
    else:
        names = dict(opts)
        ui.note("넣고 싶은 요소를 고르고, 그중 맨 앞(리드)에 올 것을 고르세요. '재료 초안'은 카드 숫자를 그대로 이은 문장(AI 없음), 아래 '문체 틀'은 중앙일보 산업부 문체로 쓴 뼈대예요.")
        picked = st.multiselect("기사에 넣을 요소", [k for k, _ in opts], format_func=names.get, key="w_pick",
                                placeholder="예: 실적, 가동률, 직원")
        lead = st.radio("맨 앞에 올 요소 (리드)", picked, format_func=names.get, horizontal=True, key="w_lead") if picked else None
        if st.button("재료 초안 만들기 (숫자 문장만 · AI 없음)", disabled=not picked, key="w_go"):
            draft = art.compose(all_cards, picked, lead, corp["corp_name"], dc.strip_correction(row.get("report_nm")), str(row.get("rcept_dt", "")))
            st.session_state["w_draft"] = dict(rno=rno, draft=draft, ai=None)
        saved = st.session_state.get("w_draft")
        if saved and saved["rno"] == rno:
            d = saved["draft"]
            ui.note("제목 후보")
            st.code(d["title"], language=None, wrap_lines=True)
            ui.note("본문 초안 (숫자로만 엮음 · 오른쪽 위 단추로 복사)")
            st.code(d["text"], language=None, wrap_lines=True)
        if picked:
            st.divider()
            render_frame(all_cards, picked, lead, rno)


for tab, fn in ((tab_toc, render_toc), (tab_ai, render_ai), (tab_diff, render_diff)):
    with tab:
        if parsed is None:
            st.info("원문을 받지 못해 이 탭은 비어 있어요. 위 '기사 포인트'의 안내를 보고 잠시 뒤 다시 열어 주세요.")
        else:
            fn(parsed)
