# 사업보고서 분석기

DART 사업·반기·분기보고서를 목차 부분별로 나눠 읽는 Streamlit 앱입니다.

- 목차별 원문 (원문 줄 번호 표시)
- AI 분석 11개 항목 — 근거 줄 번호, 원문에 없는 숫자는 경고
- 직전 보고서 대비 달라진 문장 (1년 전 같은 기간 / 바로 앞 보고서)

## 실행
Streamlit Community Cloud에서 이 저장소의 `app.py`를 배포하고, Secrets에 다음을 넣습니다.

```toml
DART_API_KEY = "..."
GEMINI_API_KEY = "..."
```

## 시험
```bash
pip install -r requirements.txt
python tests/test_core.py
python tests/test_app.py
```
