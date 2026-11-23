"""Claude API (유료, 선택) — '기사 쓰기 > 문체 틀'에서만 쓴다. 2026.11.24 사용자 요청으로 추가.

- 키는 Streamlit Secrets `ANTHROPIC_API_KEY`에만. 키가 없으면 화면에 Claude 선택지가 나오지 않는다(Gemini 무료만).
- 모델은 Secrets `CLAUDE_MODEL`(없으면 claude-opus-5-5). 거절(refusal)되면 서버가 다른 모델로 이어 쓰게 fallbacks="default".
- 비용이 드니 Anthropic 콘솔에서 월 사용 한도를 걸어 둔다.
"""
import anthropic

from analyses import AiError

DEFAULT_MODEL = "claude-opus-5-5"
TIMEOUT = 180


def call_claude(api_key, prompt, system, model=None, client=None):
    """-> 답 글(텍스트 블록만). 오류는 AiError로 (Gemini와 같은 안내 방식)."""
    client = client or anthropic.Anthropic(api_key=api_key, timeout=TIMEOUT, max_retries=2)
    try:
        res = client.beta.messages.create(
            model=model or DEFAULT_MODEL,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.AuthenticationError:
        raise AiError("Claude 키(Streamlit Secrets의 ANTHROPIC_API_KEY)를 확인해 주세요.")
    except anthropic.PermissionDeniedError:
        raise AiError("Claude 키에 이 모델 권한이 없어요. Secrets의 CLAUDE_MODEL을 확인해 주세요.")
    except anthropic.NotFoundError:
        raise AiError("Claude 모델 이름(Secrets의 CLAUDE_MODEL)을 확인해 주세요.")
    except anthropic.RateLimitError:
        raise AiError("Claude 사용량 한도(분당 또는 콘솔에서 건 월 한도)에 걸렸어요. 잠시 뒤 다시 눌러 주세요.", quota=True)
    except anthropic.APIStatusError as e:
        if e.status_code >= 500:
            raise AiError("Claude 서버가 지금 붐비거나 응답이 없어요. 1~2분 뒤 다시 눌러 주세요.")
        if "credit" in str(e).lower() or "billing" in str(e).lower():
            raise AiError("Claude 크레딧이 부족해요. Anthropic 콘솔에서 충전해 주세요.")
        raise AiError(f"Claude 응답 오류 [{e.status_code}]")
    except anthropic.APIConnectionError:
        raise AiError("Claude 서버에 연결하지 못했어요. 잠시 뒤 다시 눌러 주세요.")
    if res.stop_reason == "refusal":
        raise AiError("Claude가 이 요청에 답하지 않았어요. Gemini로 다시 시도해 보세요.")
    text = "".join(b.text for b in res.content if getattr(b, "type", "") == "text").strip()
    if not text:
        raise AiError("Claude가 답을 돌려주지 않았어요. 다시 시도해 주세요.")
    return text
