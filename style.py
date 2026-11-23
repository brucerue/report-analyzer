"""문체 파일 읽기: 기사 '틀' 만들기(작성·규칙 점검)에 쓰는 중앙일보 산업부 문체 규칙과 예문.

- 파일에는 지면 기사 본문이 들어 있어 이 공개 저장소에 두지 않는다. 비공개 저장소 paper-private의
  `report-analyzer-handoff/style/`(style_rules.md, examples/*.md)에 두고, 앱이 실행할 때마다 GitHub에서 읽는다(10분 저장).
- 읽기 전용 토큰은 Streamlit Secrets `PAPER_PRIVATE_READ_TOKEN`(paper-private 한 곳, Contents: Read)에만.
- 시험·로컬: 환경변수 `STYLE_DIR`에 같은 모양의 폴더를 두면 그곳에서 읽는다.
- 코드에는 문체 내용을 쓰지 않는다 (사용자가 파일만 고치면 반영).
"""
import base64
import os
import time

REPO = "brucerue/paper-private"
BASE = "report-analyzer-handoff/style"
REFS = ("main", "claude/confident-cray-m85m6s")  # main에 합쳐지기 전엔 작업 브랜치에서
TTL = 600
_cache = {}


class StyleError(Exception):
    pass


def _from_dir(path):
    rules_p = os.path.join(path, "style_rules.md")
    if not os.path.exists(rules_p):
        raise StyleError(f"{rules_p} 가 없어요.")
    ex = {}
    ex_dir = os.path.join(path, "examples")
    for name in sorted(os.listdir(ex_dir)) if os.path.isdir(ex_dir) else []:
        if name.endswith(".md"):
            ex[name] = open(os.path.join(ex_dir, name), encoding="utf-8").read()
    return dict(rules=open(rules_p, encoding="utf-8").read(), examples=ex, source=f"폴더 {path}")


def _gh(session, token, path, ref):
    res = session.get(f"https://api.github.com/repos/{REPO}/contents/{path}", params={"ref": ref}, timeout=20,
                      headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    if res.status_code == 404:
        return None
    if res.status_code in (401, 403):
        raise StyleError("문체 파일 토큰(Streamlit Secrets의 PAPER_PRIVATE_READ_TOKEN)이 맞지 않거나 권한이 없어요.")
    if res.status_code != 200:
        raise StyleError(f"문체 파일을 읽지 못했어요 [{res.status_code}].")
    return res.json()


def _text(item):
    return base64.b64decode(item.get("content", "")).decode("utf-8")


def _from_github(session, token, refs=REFS):
    for ref in refs:
        rules = _gh(session, token, f"{BASE}/style_rules.md", ref)
        if rules is None:
            continue
        ex = {}
        for item in _gh(session, token, f"{BASE}/examples", ref) or []:
            if item.get("name", "").endswith(".md"):
                one = _gh(session, token, item["path"], ref)
                if one:
                    ex[item["name"]] = _text(one)
        return dict(rules=_text(rules), examples=ex, source=f"paper-private ({ref})")
    raise StyleError("paper-private에서 문체 파일(report-analyzer-handoff/style/style_rules.md)을 찾지 못했어요.")


def load(session=None, token=None, refs=REFS, now=None):
    """-> dict(rules, examples{파일명: 글}, source). 10분 동안 저장."""
    now = now or time.time()
    hit = _cache.get("style")
    if hit and now - hit[0] < TTL:
        return hit[1]
    if os.environ.get("STYLE_DIR"):
        out = _from_dir(os.environ["STYLE_DIR"])
    elif token:
        import requests
        out = _from_github(session or requests.Session(), token, refs)
    else:
        raise StyleError("문체 파일을 읽으려면 Streamlit Secrets에 PAPER_PRIVATE_READ_TOKEN을 넣어 주세요.")
    _cache["style"] = (now, out)
    return out


def examples_for(style, kind):
    """유형(A·B·C) 예문: 파일 이름이 'B_'로 시작하는 것."""
    return [t for n, t in sorted(style["examples"].items()) if n.upper().startswith(kind.upper() + "_")]
