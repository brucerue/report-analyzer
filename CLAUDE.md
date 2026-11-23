# 사업보고서 분석기 — 작업 규칙 (Claude Code용)

중앙일보 나상현 기자의 Streamlit 앱(https://report-analyzer.streamlit.app, Streamlit Community Cloud · main 브랜치 app.py). 사업·반기·분기보고서(DART 정기보고서)를 목차 부분별로 깊게 읽는다.
산업 취재 도우미(공개 저장소 `brucerue/DART-Joongang`)에서 갈라져 나왔다. 사용자는 한국어, 짧고 친절한 설명과 단계별 안내를 좋아함.

## 반드시 지킬 것
- 이 저장소는 **공개**. API 키·토큰을 파일에 쓰지 않는다. 비밀값은 Streamlit Secrets(`DART_API_KEY`, `GEMINI_API_KEY`, `PAPER_PRIVATE_READ_TOKEN`, 선택 `ANTHROPIC_API_KEY`)에만. 채팅에 붙여 넣으라고 하지 않는다.
- **기사 원문(제목·리드·링크)과 특정 회사 분석 결과·보관함은 이 저장소에 넣지 않는다.** 비공개 저장소 `brucerue/paper-private`(`report-analyzer-handoff/`)에 둔다. 여기엔 낱말·건수로 된 우선순위 표만.
- 추가 비용이 드는 서비스는 쓰지 않는다. AI는 Gemini 무료 등급이 기본. 예외: '기사 쓰기 > 문체 틀'만 Claude API(유료)를 고를 수 있다(2026.11.24 사용자 요청, Secrets `ANTHROPIC_API_KEY`가 있을 때만 선택지가 보임, `claude_ai.py`). 다른 곳에 Claude를 넓히지 않는다.
- 요청하지 않은 변경은 하지 않는다.
- 기능을 바꾸면 `app.py`의 `LAST_UPDATED`(한국시간)를 올리고, 같은 커밋에서 `업데이트_기록.md` 맨 위에 `시각 [추가/수정/삭제] 내용 · 바뀐 파일 · ▶할 일`을 적는다.
- 바꾼 뒤엔 `python tests/test_core.py`, `python tests/test_app.py`(가짜 DART 응답). 화면을 바꿨으면 `tests/fake_app.py`를 띄워 캡처로 확인. 실서버 접속이 안 되는 환경이면 솔직히 말한다.

## 원칙 (산업 취재 도우미에서 이어 옴)
- 숫자는 AI가 만들지 않는다. AI 발췌에는 원문 줄 번호(`123: `)를 붙이고, 답에 나온 숫자가 발췌에 그대로 있는지 대조해 없으면 경고(`analyses.unverified_numbers`).
- 근거 위치를 같이 적는다: `[II-4. 매출 및 수주상황 · 줄 1234]`.
- 회사 설명은 '회사는 ~라고 설명'. 위험 평가는 하지 않고 '확인 필요'로만.
- 정정보고서가 여럿이면 가장 늦은 것(`dart_client.latest_versions`).

## 파일
- `report_parse.py`: 목차 나누기(I~XII는 제목 글자로, 목차 점선 줄 건너뜀, 같은 제목이면 뒤 글이 긴 쪽이 본문) · 소제목 · 재무 주석 · 줄 번호.
- `dart_client.py`: OpenDART 호출, 원문 zip → 글, 보고서 목록(최근 4년), 1년 전·바로 앞 보고서 찾기, 기업 찾기(DART-Joongang `corp-codes` 브랜치 CSV).
- `analyses.py`: AI 분석 항목(지면 기사 학습 빈도순), 발췌, 문장 비교, 숫자 대조, Gemini 호출.
- `points.py`: 기사 포인트 카드(AI 없음). DART 주요정보 API(직원 empSttus·보수·최대주주 hyslrSttus·소액주주 mrhlSttus·자사주·배당 alotMatter, 산업 취재 도우미 계산을 옮김) + 원문 표(XII-3 출자 16칸 표준 서식, XII-1 종속회사, II-6 R&D 비율 — 당기가 앞 칸). 지역별 매출은 재무 주석 '지역에 대한 공시' 표(겹친 머리글: 국내|외국 → 세부 지역, 마지막 값 합계)에서, 없으면 원문 표 줄만. 출자 신규·전량 처분은 수량과 장부가를 함께 본다. 표 단위는 표 머리 '(단위 : 백만원, 천주, %)'에서 읽는다.
- `tools/golden.py` + Actions 'golden'(수동): 실제 DART 보고서 5건(`tests/golden/expected.json`의 접수번호)으로 목차·블록·카드를 찍고 기대값과 비교. 이 작업 환경은 DART 접속이 막혀 있어 실제 확인은 이걸로 한다(로그는 MCP get_job_logs로 읽음).
- `tools/sweep.py` + Actions 'sweep'(수동, 묶음 1~5 동시): 업종 대표 25곳 최근 보고서로 카드·기사 문장·초안을 찍고 이상값을 '!! 점검'으로 표시(기대값 비교 없음). 카드 규칙을 바꾸면 돌려서 로그를 읽는다.
- `plant.py`: 공장별 가동률. II-3에서 '능력 | 실적 | 가동률%'로 끝나는 표 줄을 읽음(첫 줄의 글 칸 수로 사업부문을 이어 붙임), 단위가 '대, 시간'이면 사업부문 이름으로 고름. 공장별은 보고서 값, 합산은 능력·실적 합. 1년 전 같은 기간 보고서와 같은 공장끼리 비교, `sentences`가 숫자로만 기사 문장을 만든다.
- `compare.py`: 여러 회사 비교. 기본 지표는 DART 주요정보 API(회사별 동시 조회, 한 회사 오류는 비고로), 원문 지표(R&D·가동률·해외 비중)는 선택. 업종 묶음 `INDUSTRY_GROUPS`(DART-Joongang에서 옮김)·줄임말 `ALIASES`. `rank_sentence`가 순위 문장(증감률은 나열). 화면은 app.py `render_multi`(맨 위 '여러 회사 비교').
- `writer.py`: 카드 숫자 → 기사 문장 (모든 카드 같은 규칙: 증가·감소/상승·하락/흑자·적자 전환, 기간 '2025년…전년' / '2026년 1∼9월…지난해 같은 기간', 조사 plant.josa). 회사 설명은 인용 한 문장, 표 줄 카드는 문장 없음. 카드에는 문장을 보여 주지 않고 '기사 쓰기' 재료로만 쓴다.
- `article.py`: '기사 쓰기' 탭 — ① 재료 초안(AI 없음): 고른 요소를 리드부터 엮은 숫자 문장. ② 문체 틀: `facts`(카드→JSON, 기사 문장 없음) → Gemini 작성(`write_prompt`: 문체 규칙 전문 + 유형 B·C 예문 + `APP_RULES`) → 규칙 점검(`check_prompt`, `split_check`로 고친 곳 분리) + 숫자 대조. 틀이라 날짜 'OO일', 멘트 없음, 원인·전망은 【확인 필요】.
- `style.py`: 문체 규칙·예문을 paper-private `report-analyzer-handoff/style/`에서 GitHub API로 읽음(Secrets `PAPER_PRIVATE_READ_TOKEN`, main → 작업 브랜치 순, 10분 저장, 시험은 `STYLE_DIR`=tests/fake_style). **지면 기사 본문이라 이 공개 저장소에 문체 파일을 넣지 않는다.** 데스크 수정 쌍은 쓰지 않는다(Gemini 무료로 보내므로).
- 카드 기간 이름은 `points.period_labels`(이번·작년 같은 기간·누적 제목·이번 분기 3개월·prev_end '2025년 말'·same_point '2025년 9월 말'·prevq). 비교 기준: 기간 값=전년 동기(R&D도 1년 전 같은 기간 보고서), 잔액=지난해 말, 직원·소액주주·종속회사=1년 전 같은 시점, 분기 실적은 직전 분기(`points.prev_quarter`)도.
- `ui.py`: 화면 꾸미기 '교정지' — 종이 #F2F4F3 · 먹 #1F2B30 · 형광펜 #EEF36A(근거·새 문장) · 교정 빨강 #B8322A(없어진 문장) · 인주 청 #24479A. 원문은 괘선+줄 번호. HTML 조각은 `st.html`(스타일 포함), AI 답만 마크다운.
- `tests/fake_app.py`: 가짜 DART·AI 응답으로 앱 띄우기 (`streamlit run tests/fake_app.py`) — 화면 확인용.
- 화면 흐름: 보고서를 고르면 `points.build_cards(part='fast')`(원문 없이 DART 자료만)를 먼저 그리고, `load_parsed`가 원문을 받아(진행 표시, `dart_client.DOC_DEADLINE` 90초 넘으면 끊음, 메모리+디스크 `/tmp/report-analyzer-cache` 일주일) `part='doc'` 카드·공장별 가동률·다른 탭을 채운다.
- `app.py`: 화면 — 맨 위 '회사 하나 깊게 보기'(기사 포인트 / 기사 쓰기 / 목차별 보기 / AI 분석 / 달라진 문장) 또는 '여러 회사 비교'.

## 단계
1. 뼈대(완료): 목차별 원문+줄 번호, AI 분석 11개, 달라진 문장(1년 전·바로 앞).
2. 기사 포인트 카드(완료): 실적(손익, 흑자·적자 전환, 경영진단 이유 줄) → 출자·종속회사 → 임원·직원 → 주주환원·지분 → 가동률(plant.py, 공장별 표+기사 문장) → 원재료 매입액(II-3 표) → 시설투자(현금흐름표 유형자산 취득 + 원문 계획 줄) → 부채비율·차입금·현금(DART 재무제표 fnlttSinglAcntAll, `points.fetch_fin`) → R&D → 지역별 매출(주석 지역 공시).
3. 골든 시험(완료): 삼성전자·KB금융·에코프로비엠·현대차 반기·현대차 정정본.
4. 여러 회사 비교(완료): 회사 이름·업종 묶음, 같은 기간 지표 표, 순위 문장.
5. 네이버 검색 API 기사 수집(완료): `tools/news_collect.py` + Actions 'news_collect'(수동, 이 공개 저장소에서 실행 — 무료). 결과는 paper-private `report-news` 브랜치(naver_reports.jsonl·summary.md)에만, 로그엔 건수만. Secrets: NAVER_CLIENT_ID·NAVER_CLIENT_SECRET·PAPER_PRIVATE_TOKEN.

## 알아 둘 함정
- 목차는 회사·연도마다 조금씩 다르다. 금융업은 II가 '영업의 현황' 등으로 다르다(`biz_fin_*`).
- 표는 한 행이 한 줄, 칸은 ' | ' (`dart_client._one_line_row`, 2026.11.23부터. 그 전엔 칸마다 줄이 바뀌었음). 단위(백만원·천원)는 표 머리에서 같이 읽는다.
- OpenDART 정기보고서 API는 미등기임원 등이 빠지는 회사가 있다(paper-private `hmg_exec.py` 참고).
- DART 하루 호출 한도: 같은 보고서 원문은 일주일 저장.
