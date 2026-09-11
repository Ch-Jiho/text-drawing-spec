# 텍스트 도면 생성기

한국어로 부품(용도·모양·치수)을 설명하면 FastAPI가 OpenAI로 Spec JSON을 만들고, Streamlit에서 치수를 확인한 뒤에만 Pillow로 도면 PNG를 그립니다.

- Frontend: Streamlit (`frontend/app.py`)
- Backend: FastAPI (`backend/main.py`)
- Database: SQLite (`chat_history`, `drawings`)
- LLM: OpenAI API (텍스트 → JSON만)
- 환경변수: 프로젝트 루트 `.env`

AI 이미지 생성(DALL·E 등)은 쓰지 않습니다. 도면은 Spec JSON을 진실의 원천으로 코드가 그립니다. 로컬에서만 실행하며 배포하지 않습니다.

상세 설계는 `docs/구현계획.md`를 참고하세요.

## 폴더

```text
실습1/
  frontend/
    app.py                 # Streamlit UI. HTTP만 호출
  backend/
    main.py                # POST /summarize, POST /render, GET /health
    database.py            # SQLite
    openai_parse.py
    spec_schema.py
    drawing.py
    data/app.db            # 실행 시 생성. gitignore
  .env
  .env.example
  requirements.txt
  README.md
  docs/구현계획.md
```

루트에서 `streamlit run app.py`는 더 이상 없습니다. UI는 `frontend/app.py`입니다.

## 실행

1. Python 3.11+ 와 가상환경

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2. 루트 `.env`에 키를 넣습니다. `.env.example`을 복사해도 됩니다.

```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
BACKEND_URL=http://127.0.0.1:8000
```

선택: `OPENAI_BASE_URL`, `SQLITE_PATH`(기본 `backend/data/app.db`).

키는 FastAPI만 읽습니다. Streamlit에는 넣지 않습니다.

3. 터미널 두 개에서, **프로젝트 루트**로 실행합니다.

```bash
uvicorn backend.main:app --reload --port 8000
```

```bash
streamlit run frontend/app.py
```

백엔드가 꺼져 있으면 화면에 연결 오류가 납니다.

## 사용 흐름

1. 텍스트 입력 → ↑ **스펙 추출** → `POST /summarize`
2. 표에서 치수 확인/수정 (이 단계까지는 도면 없음)
3. **확인 후 도면 생성** → `POST /render`
4. PNG 미리보기 및 다운로드

확인 없이 추출과 렌더를 한 번에 하지 않습니다. 키가 없거나 호출/스키마가 실패하면 도면을 만들지 않습니다. 규칙 파서 폴백은 없습니다.

`/summarize`는 일반 문서 요약이 아니라 부품 설명 → Spec JSON입니다. `/chat`은 없습니다.

## API

| 메서드 | 경로 | 역할 |
|--------|------|------|
| GET | `/health` | 서버·OpenAI 키 여부 |
| POST | `/summarize` | 텍스트 → Spec. `chat_history`에 입력·응답·시각 저장 |
| POST | `/render` | 확정 Spec → PNG. `drawings`에 저장 |

히스토리 화면은 없습니다. DB는 백엔드가 조용히 기록만 합니다.

## 지원 범위

- `box`: 가로(폭) / 세로(깊이) / 높이, 제3각법 3면도
- `cylinder`: 단별 외경 / 내경 / 길이·공차, 정면도만 중앙. 단 추가·이동·삭제. 총 기장은 단 길이의 합
- `plate`: 길이 / 폭 / 두께, 제3각법 3면도
- 원형 hole(면, 지름, 중심)은 가능하면 표시
- 그 외는 `unsupported`로 거절하고 그리지 않음

도면은 교육용 근사입니다. KS 완전 규격이 아닙니다.

## 한계

- OpenAI API 키가 필수입니다.
- FastAPI(`8000`)와 Streamlit을 같이 켜야 합니다.
- 지원 솔리드는 box / cylinder / plate 뿐입니다.
- 치수선·표제란·축척(1:1, 1:2, 1:5, 1:10)은 교육용 근사입니다.
- “세로”는 깊이로 두고 UI에서 수정합니다. 자동으로 높이로 바꾸지 않습니다.
