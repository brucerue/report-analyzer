"""Claude API 호출(가짜 클라이언트): 텍스트만 꺼내기, 거절·오류 안내. 실행: python tests/test_claude.py"""
import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import anthropic
import httpx2 as httpx  # anthropic 2.x가 쓰는 http 라이브러리 (가짜 응답용)

import analyses as an
import claude_ai


class Fake:
    def __init__(self, result=None, error=None):
        self.kw, self.result, self.error = None, result, error
        self.beta = NS(messages=NS(create=self.create))

    def create(self, **kw):
        self.kw = kw
        if self.error:
            raise self.error
        return self.result


def test_text_only():
    res = NS(stop_reason="end_turn", content=[NS(type="thinking", thinking=""), NS(type="text", text="제목: 가\n\n본문")])
    f = Fake(res)
    out = claude_ai.call_claude("k", "PROMPT", "SYSTEM", client=f)
    assert out == "제목: 가\n\n본문"
    assert f.kw["model"] == "claude-opus-5-5" and f.kw["system"] == "SYSTEM" and f.kw["fallbacks"] == "default"
    assert f.kw["messages"][0]["content"] == "PROMPT"
    print("ok - 텍스트 블록만, 기본 모델·fallbacks")


def test_errors():
    try:
        claude_ai.call_claude("k", "p", "s", client=Fake(NS(stop_reason="refusal", content=[])))
        assert False
    except an.AiError as e:
        assert "Gemini로" in str(e)
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    for cls, code, word in ((anthropic.AuthenticationError, 401, "ANTHROPIC_API_KEY"), (anthropic.RateLimitError, 429, "한도")):
        err = cls("x", response=httpx.Response(code, request=req), body=None)
        try:
            claude_ai.call_claude("k", "p", "s", client=Fake(error=err))
            assert False
        except an.AiError as e:
            assert word in str(e), str(e)
    print("ok - 거절·키·한도 안내")



def test_meter_cost():
    res = NS(stop_reason="end_turn", model="claude-sonnet-5-5", usage=NS(input_tokens=10000, output_tokens=3000, cache_creation_input_tokens=0, cache_read_input_tokens=0),
             content=[NS(type="text", text="본문")])
    m = []
    f = Fake(res)
    claude_ai.call_claude("k", "p", "s", model="claude-sonnet-5-5", client=f, meter=m)
    tin, tout, won = claude_ai.cost_won(m)
    assert (tin, tout) == (10000, 3000) and abs(won - (10000 * 2 + 3000 * 10) / 1e6 * 1400) < 0.01, won
    fh = Fake(NS(stop_reason="end_turn", content=[NS(type="text", text="x")]))
    claude_ai.call_claude("k", "p", "s", model="claude-haiku-5-5", client=fh)
    assert "fallbacks" not in fh.kw, "Haiku엔 서버 대체(fallbacks) 안 붙임"
    print("ok - 실제 사용량 -> 원, Haiku는 fallbacks 없음")

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("모두 통과")
