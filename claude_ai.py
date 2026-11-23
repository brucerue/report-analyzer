"""Claude API (유료, 선택) — '기사 쓰기 > 문체 틀'에서만 쓴다. 2026.11.24 사용자 요청으로 추가.

- 키는 Streamlit Secrets `ANTHROPIC_API_KEY`에만. 키가 없으면 화면에 Claude 선택지가 나오지 않는다(Gemini 무료만).
- 모델은 Secrets `CLAUDE_MODEL`(없으면 claude-opus-5-5). 거절(refusal)되면 서버가 다른 모델로 이어 쓰게 fallbacks="default".
- 비용이 드니 Anthropic 콘솔에서 월 사용 한도를 걸어 둔다.
"""
import anthropic

from analyses import AiError

DEFAULT_MODEL = "claude-opus-5-5"
TIMEOUT = 180
MODELS = {  # 화면 선택지: 이름 -> (모델, 입력·출력 100만 토큰당 달러). 요금은 2026.11 기준(바뀌면 여기만 고침)
    "Haiku 5.5 (가장 쌈)": ("claude-haiku-5-5", 0.10, 0.50),
    "Sonnet 5.5 (중간)": ("claude-sonnet-5-5", 2.0, 10.0),
    "Opus 5.5 (가장 좋음)": ("claude-opus-5-5", 4.0, 20.0),
}
WON_PER_DOLLAR = 1400  # 어림 환율


def price_of(model):
    for m, pin, pout in MODELS.values():
        if model and str(model).startswith(m):
            return pin, pout
    return None


def cost_won(usage_list):
    """[(모델, 입력 토큰, 출력 토큰)] -> (입력 합, 출력 합, 원). 모르는 모델이면 원은 None."""
    tin = sum(u[1] for u in usage_list)
    tout = sum(u[2] for u in usage_list)
    won = 0.0
    for m, i, o in usage_list:
        pr = price_of(m)
        if pr is None:
            return tin, tout, None
        won += (i * pr[0] + o * pr[1]) / 1e6 * WON_PER_DOLLAR
    return tin, tout, won


def call_claude(api_key, prompt, system, model=None, client=None, meter=None):
    """-> 답 글(텍스트 블록만). 오류는 AiError로 (Gemini와 같은 안내 방식).
    meter(목록)를 주면 (모델, 입력 토큰, 출력 토큰)을 더한다 — 화면에 실제 든 돈을 보여 주려고."""
    client = client or anthropic.Anthropic(api_key=api_key, timeout=TIMEOUT, max_retries=2)
    model = model or DEFAULT_MODEL
    extra = {} if model.startswith("claude-haiku") else dict(betas=["server-side-fallback-2026-07-01"], fallbacks="default")  # Haiku엔 서버 대체 없음
    try:
        res = client.beta.messages.create(
            model=model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": "medium"},
            **extra,
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
    u = getattr(res, "usage", None)
    if meter is not None and u is not None:
        meter.append((getattr(res, "model", None) or model, (u.input_tokens or 0) + (getattr(u, "cache_creation_input_tokens", 0) or 0)
                      + (getattr(u, "cache_read_input_tokens", 0) or 0), u.output_tokens or 0))
    if res.stop_reason == "refusal":
        raise AiError("Claude가 이 요청에 답하지 않았어요. Gemini로 다시 시도해 보세요.")
    text = "".join(b.text for b in res.content if getattr(b, "type", "") == "text").strip()
    if not text:
        raise AiError("Claude가 답을 돌려주지 않았어요. 다시 시도해 주세요.")
    return text
