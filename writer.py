"""기사 문장 만들기 — 모든 카드가 같은 규칙으로 (AI 없음, 카드에 쓴 숫자 그대로).

규칙
- 숫자를 계산한 카드: 1~3문장. 기간은 '2025년 …, 전년보다'(사업보고서) / '2026년 1∼9월 …, 지난해 같은 기간보다'(분기·반기).
- 금액은 기사체(333조6059억원·7000만원, 보수는 만원까지), 증감은 'n% 늘었다/줄었다', 비율은 'n%p 높아졌다/낮아졌다',
  손익은 흑자 전환·적자 전환·영업손실. 조사(은/는·이/가·으로/로)는 plant.josa로 맞춘다.
- 회사 설명을 옮긴 카드(실적 변동 이유): '회사는 "…"라고 설명했다' 인용 한 문장.
- 표 줄만 보여 주는 카드(투자 계획·원문 줄 가동률·지역): 문장을 만들지 않는다 (단위·기간이 표마다 달라 숫자를 옮기면 틀리기 쉬움).
"""
import re

import plant
import points as pt

NO_SENTENCE_NOTE = "표 줄을 그대로 보여 주는 카드라 기사 문장은 만들지 않아요 (단위·기간을 원문 표에서 확인하세요)."


def j(word, pair):
    return plant.josa(word, pair)


def _chg(now, prev, unit_word=("증가했다", "감소했다")):
    """'10.9% 증가했다' / None. (가동률 문장 plant.sentences와 같은 말: 증가·감소, 상승·하락)"""
    if now is None or not prev:
        return None
    c = (now - prev) / abs(prev) * 100
    if round(c, 1) == 0:
        return "같은 수준이었다"
    return f"{abs(c):.1f}% {unit_word[0] if c > 0 else unit_word[1]}"


def _pp(now, prev):
    """'0.3%p 상승했다' / '같은 수준이었다'. 원래 값이 소수 둘째 자리면 둘째 자리까지 (0.04% -> 0.05%: '0.01%p 하락')."""
    if now is None or prev is None:
        return None
    nd = max(len(str(x).split(".")[1]) if "." in str(x) else 0 for x in (now, prev))
    nd = 2 if nd >= 2 else 1
    d = now - prev
    if round(d, nd) == 0:
        return "같은 수준이었다"
    return f"{abs(d):.{nd}f}%p {'상승했다' if d > 0 else '하락했다'}"


def _vs(base_text, now, prev):
    """'2025년 말(26.6%)보다 0.3%p 상승했다' / '2025년 말(26.6%)과 같은 수준이었다'."""
    pp = _pp(now, prev)
    if pp != "같은 수준이었다":
        return f"{base_text}보다 {pp}"
    head = re.sub(r"\([^()]*\)$", "", base_text)  # 조사는 괄호 앞 낱말에: '2025년 말(26.6%)과'
    return f"{base_text}{j(head, '과/와')[len(head):]} 같은 수준이었다"


def _profit(now, prev):
    """손익 변화 서술: '흑자 전환했다' / '적자 전환했다' / '적자 폭이 줄었다' / '33.2% 늘었다'."""
    if now is None or prev is None:
        return None
    if prev < 0 <= now:
        return "흑자 전환했다"
    if now < 0 <= prev:
        return "적자 전환했다"
    if now < 0 and prev < 0:
        return "적자 폭이 줄었다" if now > prev else "적자 폭이 커졌다"  # 적자 지속
    return _chg(now, prev)


def _pl(kind, v):
    return pt.pl_text(kind, v)


def sentences(c, period, annual):
    """카드 하나 -> 기사 문장 목록."""
    f = WRITERS.get(c["key"])
    if c.get("empty"):
        return []
    if f is None:
        if c["rows"]:
            c["note"] = ((c.get("note") or "") + " " + NO_SENTENCE_NOTE).strip()
        return []
    try:
        return [re.sub(r"(\d)\.0(?=%)", r"\1", s) for s in f(c["data"], period, "전년" if annual else "지난해 같은 기간", annual) if s]  # 59.0% -> 59% (사내 표기)
    except (KeyError, TypeError, ZeroDivisionError):
        return []  # 자료가 모자라면 문장 없이 (카드 숫자는 그대로)


def _and(clause):
    """'10.9% 증가했다' -> '10.9% 증가했고' (두 마디를 잇는다)."""
    return clause[:-1] + "고" if clause.endswith("다") else clause


def w_income(d, period, before, annual):
    n, p = d["now"], d["prev"]
    out = []
    rev = None
    if n["rev"] is not None:
        rev = (f"매출은 {pt.won_text(n['rev'])}으로 {before}보다 {_chg(n['rev'], p['rev'])}" if p["rev"]
               else f"매출은 {pt.won_text(n['rev'])}이었다")
    op = None
    if n["op"] is not None:
        how = _profit(n["op"], p["op"]) if p["op"] is not None else None
        if how is None:
            op = f"{_pl('영업', n['op'])}을 냈다"
        elif n["op"] < 0 or "전환" in how:
            op = f"{_pl('영업', n['op'])}을 내 {how}"
        else:
            op = f"영업이익은 {pt.won_text(n['op'])}으로 {'' if n['rev'] is not None and p['rev'] else before + '보다 '}{how}"
    if rev and op:
        out.append(f"{period} {_and(rev)}, {op}.")
    elif rev or op:
        out.append(f"{period} {rev or op}.")
    if d.get("margin") is not None and d.get("pmargin") is not None and n["op"] is not None and n["op"] > 0:
        pm = d["pmargin"]
        out.append(f"영업이익률은 {d['margin']:.1f}%로 " + _vs("%s(%.1f%%)" % (before, pm), round(d["margin"], 1), round(pm, 1)) + ".")
    if n["net"] is not None and p["net"] is not None:
        how = _profit(n["net"], p["net"])
        out.append(f"순이익은 {pt.won_text(n['net'])}으로 {how}." if n["net"] >= 0 and "전환" not in how else f"{_pl('순', n['net'])}을 내 {how}.")
    q = d.get("qtr")
    if q and q["now"]["op"] is not None and q["prev"]["op"] is not None:
        qn, qp = q["now"], q["prev"]
        how = _profit(qn["op"], qp["op"])
        ql = d.get("q_label") or "분기(3개월)"
        out.append(f"{ql}만 보면 영업이익은 {pt.won_text(qn['op'])}으로 지난해 같은 분기보다 {how}." if qn["op"] >= 0 and "전환" not in how
                   else f"{ql}만 보면 {_pl('영업', qn['op'])}을 내 {how}.")
    pq, qn = d.get("prevq"), d.get("q_now")
    if pq and qn and pq.get("op") is not None and qn.get("op") is not None:
        how = _profit(qn["op"], pq["op"])
        base = f"직전 분기인 {d.get('prevq_label') or '지난 분기'}"
        if qn["op"] >= 0 and "전환" not in how:
            out.append(f"{base}와 비교하면 영업이익이 {how}.")
        else:
            out.append(f"{base}와 비교하면 {how}.")
    return out


def w_reason(d, period, before, annual):
    q = d["quotes"][0]
    q = q if len(q) <= 120 else q[:118].rsplit(" ", 1)[0] + "…"
    return [f'회사는 {"사업" if annual else "정기"}보고서에서 "{q}"라고 설명했다.']


def w_invest(d, period, before, annual):
    out = []
    for r in d["rows"][:3]:
        amt = pt.money_text(abs(r["amount"] or 0), d["unit"])
        rate = f"(지분율 {r['rate1']}%)" if pt.to_num(r["rate1"]) is not None else ""
        verb = {"신규 취득": f"지분을 {amt}에 새로 사들였다", "추가 취득": f"지분을 {amt}어치 더 사들였다",
                "전량 처분": f"지분 {amt}어치를 모두 팔았다", "일부 처분": f"지분 {amt}어치를 팔았다"}[r["kind"]]
        out.append(f"{period} {r['name']} {verb}{rate}." if r["kind"] != "전량 처분" else f"{period} {r['name']} {verb}.")
    return out


def w_consol(d, period, before, annual):
    s = f"연결 종속회사는 {d['count']:,}곳이다."
    if d.get("rows_prev"):
        diff = d["rows_now"] - d["rows_prev"]
        s = f"연결 종속회사는 {d['count']:,}곳으로, {d.get('same_point') or '1년 전'}보다 {abs(diff)}곳 {'증가했다' if diff > 0 else '감소했다'}." if diff else s
    out = [s]
    if d.get("new"):
        names = ", ".join(d["new"][:3])
        out.append(f"새로 연결 대상에 들어온 곳은 {names}" + (f" 등 {len(d['new'])}곳이다." if len(d["new"]) > 3 else j(names, "이다/다")[len(names):] + "."))
    return out


def w_staff(d, period, before, annual):
    n, p = d["now"], d["prev"]
    out = []
    s = f"직원 수는 {n['count']:,}명으로 {d.get('same_point') or '1년 전'}보다 {_chg(n['count'], p['count'])}." if p["count"] else f"직원 수는 {n['count']:,}명이다."
    out.append(s)
    if n["avg"]:
        label = "1인 평균 급여는" if annual else f"{period} 1인 평균 급여(누적)는"
        out.append(f"{label} {pt.won_text(n['avg'], man=True)}으로 {'전년' if annual else before}({pt.won_text(p['avg'], man=True)})보다 {_chg(n['avg'], p['avg'])}."
                   if p["avg"] else f"{label} {pt.won_text(n['avg'], man=True)}이었다.")
    return out


def w_pay(d, period, before, annual):
    t = d["top"]
    name, title, amt = t[0]
    who = f"{name} {title}".strip()
    out = [f"보수를 가장 많이 받은 사람은 {j(who, '으로/로')} {pt.won_text(amt, man=True)}을 받았다."]
    if len(t) > 1:
        rest = ", ".join(f"{f'{n} {ti}'.strip()}({pt.won_text(a, man=True)})" for n, ti, a in t[1:3])
        out.append(f"이어 {rest} 순이었다.")
    return out


def w_holder(d, period, before, annual):
    h = d["h"]
    out = []
    if h["total"] is not None:
        base = d.get("base")
        bk = d["base_kind"]
        s = f"최대주주 {j(h['name'], '과/와')} 특수관계인의 보통주 지분율은 {h['total']}%"
        if base is None:
            s += "다."
        elif _pp(h["total"], base) == "같은 수준이었다":
            s += f"로 {j(bk, '과/와')} 같았다."
        else:
            s += f"로 {bk}({base}%)보다 {_pp(h['total'], base)}."
        out.append(s)
    m1, m0 = d.get("m1"), d.get("m0")
    if m1 and m1.get("count"):
        out.append(f"소액주주는 {m1['count']:,}명으로 {d.get('same_point') or '1년 전'}보다 {_chg(m1['count'], m0['count'])}." if m0 and m0.get("count") else f"소액주주는 {m1['count']:,}명이다.")
    return out


def w_return(d, period, before, annual):
    out = []
    t, dv = d.get("t"), d["d"]
    if t and t.get("burn"):
        out.append(f"{period} 자사주 {t['burn']:,}주를 소각했다.")
    elif t and t.get("acq"):
        out.append(f"{period} 자사주 {t['acq']:,}주를 사들였다.")
    if dv["now"]["total"]:
        if annual and dv["prev"]["total"]:
            out.append(f"현금배당 총액은 {pt.won_text(dv['now']['total'])}으로 전년보다 {_chg(dv['now']['total'], dv['prev']['total'])}.")
        else:
            out.append(f"현금배당 총액은 {pt.won_text(dv['now']['total'])}이다.")
    if dv["now"]["dps"]:
        out.append(f"보통주 1주당 배당금은 {dv['now']['dps']:,}원" + (f", 배당성향(연결)은 {dv['now']['payout']}%다." if dv["now"]["payout"] is not None else "이다."))
    return out


def w_plant(d, period, before, annual):
    return plant.sentences(d["set"], period, annual=annual)


def w_material(d, period, before, annual):
    m, pm = d["mat"], d.get("prev")
    if not m["unit"]:
        return []  # 단위를 모르면 문장을 만들지 않는다
    tot = pt.money_text(m["total"], m["unit"])
    chg = d.get("chg")
    s = f"{period} 원재료 매입액은 {tot}" + (f"으로 {before}보다 {_chg(*chg)}." if pm and chg else "이다.")
    out = [s.replace(f"{tot}으로", j(tot, "으로/로"))]
    if m["items"]:
        _, v, sh, _, name = m["items"][0]
        out.append(f"가장 많이 사들인 품목은 {name}({pt.money_text(v, m['unit'])}" + (f", 비중 {sh:g}%)다." if sh is not None else ")이다."))
    return out


def w_capex(d, period, before, annual):
    n, p = d["now"], d["prev"]
    v = pt.won_text(n["capex"])
    s = f"{period} 시설투자(유형자산 취득)는 {v}" + (f"으로 {before}보다 {_chg(n['capex'], p['capex'])}." if p.get("capex") else "다.")
    return [s.replace(f"{v}으로", j(v, "으로/로"))]


def w_debt(d, period, before, annual):
    n, p = d["now"], d["prev"]
    pe = d.get("prev_end") or "지난해 말"
    out = [f"부채비율은 {n['debt_ratio']:.1f}%로 " + _vs("%s(%.1f%%)" % (pe, p["debt_ratio"]), round(n["debt_ratio"], 1), round(p["debt_ratio"], 1)) + "."
           if p.get("debt_ratio") is not None else f"부채비율은 {n['debt_ratio']:.1f}%다."]
    if n.get("borrow") is not None:
        s = f"차입금(사채 포함)은 {pt.won_text(n['borrow'])}"
        if n.get("cash") is not None:
            nb = n["net_borrow"]
            s += f", 현금및현금성자산은 {pt.won_text(n['cash'])}으로 " + (f"순차입금은 {pt.won_text(nb)}이다." if nb >= 0 else f"차입금보다 현금이 {pt.won_text(-nb)} 많다.")
        else:
            s += "이다."
        out.append(s)
    return out


def w_rnd(d, period, before, annual):
    r = d["r"]
    out = []
    if "cost" in r:
        c = r["cost"][0]
        c0 = d.get("cost0")
        v = pt.money_text(c, r["unit"])
        s = f"{period} 연구개발비는 {v}"
        s += (f"으로 {before}보다 {_chg(c, c0)}." if c0 else "이다.")
        out.append(s.replace(f"{v}으로", j(v, "으로/로")))
    ratio = r.get("ratio")
    if ratio:
        b = d.get("ratio0")
        if b is not None:
            out.append(f"매출 대비 연구개발비 비율은 {ratio[0]}%로 {_vs(f'{before}({b}%)', ratio[0], b)}.")
        else:
            out.append(f"매출 대비 연구개발비 비율은 {ratio[0]}%다.")
    return out


def w_region(d, period, before, annual):
    reg, tot = d["reg"], d["tot"]
    items = sorted([(k, v) for k, v in reg["now"] if k != "합계"], key=lambda x: -x[1])
    prev = dict(reg.get("prev") or [])
    top = items[0]
    s = f"{period} 지역별 매출은 {j(top[0], '이/가')} {pt.money_text(top[1], reg['unit'])}(비중 {top[1] / tot * 100:.1f}%)로 가장 많았고"
    rest = ", ".join(f"{k}({pt.money_text(v, reg['unit'])}·{v / tot * 100:.1f}%)" for k, v in items[1:3])
    out = [s + (f", {rest} 순이었다." if rest else "다.")]
    if prev.get(top[0]):
        out.append(f"{top[0]} 매출은 {before}보다 {_chg(top[1], prev[top[0]])}.")
    return out


WRITERS = {"income": w_income, "reason": w_reason, "invest": w_invest, "consol": w_consol, "staff": w_staff, "pay": w_pay,
           "holder": w_holder, "return": w_return, "plant": w_plant, "material": w_material, "capex": w_capex,
           "debt": w_debt, "rnd": w_rnd, "region": w_region}


def collect(cards):
    """모든 카드의 문장을 카드 순서대로 하나의 글로 (기사 문장 모음)."""
    return [s for c in cards for s in c.get("sentences") or []]
