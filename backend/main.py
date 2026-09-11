"""FastAPI 서버. OpenAI 파싱과 Pillow 렌더, SQLite 저장."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

_BACKEND_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _BACKEND_DIR.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

load_dotenv(_ROOT_DIR / ".env")

from database import init_db, save_chat, save_drawing  # noqa: E402
from drawing import DRAWING_VERSION, render_drawing_png  # noqa: E402
from openai_parse import parse_image_to_spec, parse_text_to_spec  # noqa: E402
from spec_schema import SpecDraft, missing_dimension_labels, normalize_spec  # noqa: E402

app = FastAPI(title="텍스트 도면 생성기")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SummarizeIn(BaseModel):
    text: str = ""


class RenderIn(BaseModel):
    spec: dict = Field(default_factory=dict)
    history_id: int | None = None


_ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
_MAX_IMAGE_BYTES = 15 * 1024 * 1024


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def _has_openai_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "has_openai_key": _has_openai_key(),
        "drawing_version": DRAWING_VERSION,
    }


@app.post("/summarize")
def summarize(body: SummarizeIn) -> dict:
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="설명을 입력하세요.")
    if not _has_openai_key():
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY가 없습니다. `.env`에 키를 넣으세요.",
        )
    try:
        spec = parse_text_to_spec(text)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"LLM 파싱 실패: {exc}") from exc

    payload = spec.model_dump()
    response_text = json.dumps(payload, ensure_ascii=False)
    history_id, created_at = save_chat(text, response_text)
    return {
        "id": history_id,
        "input": text,
        "response": response_text,
        "spec": payload,
        "created_at": created_at,
    }


@app.post("/extract")
def extract(file: UploadFile = File(...)) -> dict:
    if not _has_openai_key():
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY가 없습니다. `.env`에 키를 넣으세요.",
        )
    filename = (file.filename or "drawing.png").strip() or "drawing.png"
    suffix = Path(filename).suffix.lower()
    content_type = (file.content_type or "").lower()
    if suffix not in _ALLOWED_IMAGE_EXT and not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="PNG, JPG, WEBP 이미지만 업로드하세요.")

    image_bytes = file.file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    if len(image_bytes) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="이미지가 너무 큽니다. 15MB 이하로 올려 주세요.")

    try:
        spec = parse_image_to_spec(image_bytes, filename)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"도면 치수 추출 실패: {exc}") from exc

    payload = spec.model_dump()
    response_text = json.dumps(payload, ensure_ascii=False)
    history_id, created_at = save_chat(f"[도면] {filename}", response_text)
    return {
        "id": history_id,
        "input": filename,
        "response": response_text,
        "spec": payload,
        "created_at": created_at,
    }


@app.post("/render")
def render(body: RenderIn) -> Response:
    try:
        spec = normalize_spec(SpecDraft.model_validate(body.spec))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"도면 생성 실패: {exc}") from exc

    if spec.unsupported:
        raise HTTPException(status_code=422, detail="지원하지 않는 형상이라 도면을 만들지 않습니다.")
    gaps = missing_dimension_labels(spec)
    if gaps:
        raise HTTPException(status_code=422, detail="치수가 비어 있습니다: " + ", ".join(gaps))

    try:
        png = render_drawing_png(spec)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"도면 생성 실패: {exc}") from exc

    spec_json = json.dumps(spec.model_dump(), ensure_ascii=False)
    drawing_id = save_drawing(spec_json, png, history_id=body.history_id, title=spec.meta.title or None)
    return Response(
        content=png,
        media_type="image/png",
        headers={"X-Drawing-Id": str(drawing_id)},
    )
