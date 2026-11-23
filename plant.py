"""공장(생산거점)별 가동률: II-3 원재료 및 생산설비의 '생산능력' 표와 '생산실적' 표를 법인·소재지끼리 짝지어
가동률 = 생산실적 ÷ 생산능력 을 계산하고, 1년 전 같은 기간 보고서와 비교한다 (AI 없음, 원문 줄 번호 표시).

읽는 표: '생산능력 | 생산실적 | 가동률%'로 끝나는 줄 (현대차 '(3) 가동률', 삼성전자 '(가동률)' 표 확인)
  차량부문(대수) | HMC | 한국 | 907,000 | 897,929 | 99.0% |
  HMGMA | 미국 | 51,400 | 19,100 | 37.2% |          <- 앞 칸(사업부문)이 빠진 이어지는 줄
공장별 가동률은 보고서에 적힌 값(rate=reported, 기사도 이 값을 씀), 합산 가동률은 능력·실적을 더해 계산한다. 다시 계산한 값은 calc.
반기·분기 숫자는 그 기간 누적이라 '같은 기간' 비교에는 1년 전 같은 기간 보고서를 쓴다.
"""
import re

from points import block_lines, cells, to_num

TOTAL_WORDS = {"합계", "소계", "총계", "계", "전체"}
DOMESTIC = re.compile(r"한국|국내|대한민국|울산|아산|전주|광명|화성|광주|오창|청주|포항|구미|평택|기흥|천안|여수|창원|수원")


def _unit(t):
    m = re.search(r"단위\s*[:：]\s*([^)|]*)", t)
    return m.group(1).strip() if m else None


def unit_for(group, unit):
    """'대, 시간'처럼 단위가 여럿이면 사업부문 이름('차량부문(대수)', '기타부문(시간)')으로 고른다."""
    parts = [u.strip() for u in re.split(r"[,/]", unit or "") if u.strip()]
    if len(parts) <= 1:
        return parts[0] if parts else ""
    for u in parts:
        if u.rstrip("수") and u.rstrip("수") in group:
            return u
    return parts[0]


def rate_rows(parsed):
    """II-3에서 '생산능력 | 생산실적 | 가동률%'로 끝나는 표 줄 -> [dict(key, group, name, place, cap, prod, rate, reported, unit, line)].
    현대차: 'HMGMA | 미국 | 51,400 | 19,100 | 37.2% |', 삼성전자: '스마트폰 등 | 270,050 | 214,259 | 79.3% |'.
    표의 첫 줄은 사업부문 칸이 있고 이어지는 줄은 없어서, 첫 줄의 글 칸 수로 사업부문을 이어 붙인다."""
    out, unit, full, group = [], None, None, ""
    for no, t in block_lines(parsed, "biz_plant"):
        if "단위" in t:
            unit = _unit(t) or unit
        if "|" not in t:
            full, group = None, ""  # 표 밖 글: 다음 표를 새로 센다
            continue
        c = cells(t)
        if len(c) < 4 or not c[-1].strip().endswith("%"):
            continue
        cap, prod, rep = to_num(c[-3]), to_num(c[-2]), to_num(c[-1])
        if cap is None or prod is None or rep is None:
            continue
        texts = [x for x in c[:-3] if x]
        if not texts:
            continue
        if full is None:
            full = len(texts)
        if len(texts) >= full and full >= 2:
            group, texts = texts[0], texts[1:]
        if any(re.sub(r"\s+", "", x) in TOTAL_WORDS for x in texts):
            continue
        name = texts[0]
        place = texts[1] if len(texts) > 1 else ""
        key = (re.sub(r"\s+", "", group), re.sub(r"\s+", "", name), re.sub(r"\s+", "", place))
        out.append(dict(key=key, group=group, name=name, place=place, cap=cap, prod=prod,
                        rate=rep, calc=prod / cap * 100 if cap else None, reported=rep, unit=unit_for(group, unit), line=no))
    return out


def total(rows, prev=False):
    """합산: 능력·실적을 더해 계산. 한 곳뿐이면 보고서에 적힌 그 공장 가동률."""
    k = "prev_" if prev else ""
    cap, prod = sum(r[k + "cap"] for r in rows), sum(r[k + "prod"] for r in rows)
    rate = rows[0][k + "rate"] if len(rows) == 1 else (prod / cap * 100 if cap else None)
    return dict(cap=cap, prod=prod, rate=rate, n=len(rows))


def compare(parsed, prev_parsed):
    """이번·1년 전 같은 기간 보고서 -> dict(rows, sets). 합산은 단위·사업부문이 같은 줄끼리 (예: 현대차 '차량부문(대수)', 단위 '대').
    sets = [dict(label, unit, rows, now, prev, now_dom, prev_dom, now_abr, prev_abr)] — 합산 묶음마다."""
    cur = rate_rows(parsed)
    prev = rate_rows(prev_parsed) if prev_parsed else []
    pmap = {(r["key"], r["unit"]): r for r in prev}
    for r in cur:
        p = pmap.get((r["key"], r["unit"]))
        r["prev_rate"] = p["rate"] if p else None
        r["prev_prod"] = p["prod"] if p else None
        r["prev_cap"] = p["cap"] if p else None
        r["prev_line"] = p["line"] if p else None
        r["diff"] = r["rate"] - p["rate"] if p and r["rate"] is not None and p["rate"] is not None else None
    sets = []
    for g, u in dict.fromkeys((r["group"], r["unit"]) for r in cur):
        rows = [r for r in cur if r["group"] == g and r["unit"] == u]
        both = [r for r in rows if r["prev_rate"] is not None]
        is_dom = lambda r: bool(DOMESTIC.search(r["place"] or r["name"]))
        pt = lambda rs: total(rs, prev=True)
        dom, abr = [r for r in both if is_dom(r)], [r for r in both if not is_dom(r)]
        sets.append(dict(label=g, unit=u, rows=rows, now=total(rows), same=total(both) if both else None, prev=pt(both) if both else None,
                         now_dom=total(dom) if dom else None, prev_dom=pt(dom) if dom else None,
                         now_abr=total(abr) if abr else None, prev_abr=pt(abr) if abr else None))
    return dict(rows=cur, sets=sets)


def pct(v):
    return "-" if v is None else f"{v:.1f}%"


def pp(d):
    if d is None:
        return "-"
    if round(d, 1) == 0:
        return "변동 없음"
    return f"{abs(d):.1f}%p {'상승' if d > 0 else '하락'}"


def man_dae(v):
    """대 -> 기사체 '290만1천대' / '5만2천대' / '8,000대'."""
    if v is None:
        return "-"
    v = int(round(v))
    man, cheon = v // 10000, (v % 10000) // 1000
    if man:
        return f"{man}만" + (f"{cheon}천대" if cheon else "대")
    return f"{v:,}대"


def label(r):
    return f"{r['name']}({r['place']})" if r["place"] else r["name"]


def amount(v, unit):
    u = (unit or "").replace(" ", "")
    if u == "대":
        return man_dae(v)
    return f"{v:,}{u}"


def sentences(st, period_text="이번 기간"):
    """합산 묶음 하나(compare의 sets 원소) -> 숫자로만 만든 기사용 문장 (AI 없음). 1년 전과는 같은 공장끼리 비교."""
    out, u = [], st["unit"]
    noun = "생산거점" if any(r["place"] for r in st["rows"]) else "품목"
    now, prev = st["same"], st["prev"]
    if now and prev and prev["rate"] is not None:
        out.append(f"{period_text} {now['n']}개 {noun}의 전체 가동률은 {now['rate']:.1f}%로 지난해 같은 기간({prev['rate']:.1f}%)보다 "
                   f"{pp(now['rate'] - prev['rate'])}했다.".replace("변동 없음했다", "같았다"))
        if prev["cap"] and prev["prod"]:
            cc, pc = (now["cap"] - prev["cap"]) / prev["cap"] * 100, (now["prod"] - prev["prod"]) / prev["prod"] * 100
            out.append(f"전체 생산능력은 {amount(prev['cap'], u)}에서 {amount(now['cap'], u)}로 {abs(cc):.1f}% {'증가' if cc >= 0 else '감소'}했고, "
                       f"생산량은 {amount(prev['prod'], u)}에서 {amount(now['prod'], u)}로 {abs(pc):.1f}%({amount(abs(now['prod'] - prev['prod']), u)}) "
                       f"{'증가' if pc >= 0 else '감소'}했다.")
        for name, a, b in (("국내", st["now_dom"], st["prev_dom"]), ("해외", st["now_abr"], st["prev_abr"])):
            if a and b and b["rate"] is not None:
                n = f" {a['n']}개 공장의" if a["n"] > 1 else " 공장"
                out.append(f"{name}{n} 가동률은 지난해 {b['rate']:.1f}%에서 올해 {a['rate']:.1f}%로 {pp(a['rate'] - b['rate'])}했다."
                           .replace("변동 없음했다", "같았다"))
    elif st["now"]["rate"] is not None:
        out.append(f"{period_text} {st['now']['n']}개 {noun}의 전체 가동률은 {st['now']['rate']:.1f}%다. (1년 전 같은 기간 보고서가 없어 비교하지 못했어요)")
    ranked = [r for r in st["rows"] if r.get("diff") is not None]
    if ranked:
        worst, best = min(ranked, key=lambda r: r["diff"]), max(ranked, key=lambda r: r["diff"])
        out.append(f"하락 폭이 가장 큰 곳은 {label(worst)}로 {worst['prev_rate']:.1f}%에서 {worst['rate']:.1f}%로 {pp(worst['diff'])}했다.")
        if best["diff"] > 0:
            out.append(f"반면 {label(best)}은 {best['prev_rate']:.1f}%에서 {best['rate']:.1f}%로 {pp(best['diff'])}했다.")
    if len(st["rows"]) > 1:
        low, high = min(st["rows"], key=lambda r: r["rate"]), max(st["rows"], key=lambda r: r["rate"])
        out.append(f"가동률이 가장 낮은 곳은 {label(low)}({low['rate']:.1f}%), 가장 높은 곳은 {label(high)}({high['rate']:.1f}%)다.")
    return out
