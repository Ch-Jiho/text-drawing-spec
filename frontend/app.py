"""텍스트 기반 도면 생성기 — Streamlit UI.

흐름 1: 텍스트 → OpenAI Spec JSON → 치수 확인 → 확인 후에만 Pillow 렌더
흐름 2: 도면 업로드 → OpenAI Vision Spec JSON → 치수표
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import requests
import streamlit as st
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from spec_schema import (  # noqa: E402
    SHAPE_LABELS,
    CylinderStep,
    SpecDraft,
    cylinder_steps_of,
    dim_fields,
    missing_dimension_labels,
    normalize_spec,
    sync_cylinder_params,
)

load_dotenv(_ROOT / ".env")

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")

MODE_TEXT_TO_DRAWING = "text_to_drawing"
MODE_DRAWING_TO_TEXT = "drawing_to_text"
LABEL_TEXT_TO_DRAWING = "텍스트 to 도면"
LABEL_DRAWING_TO_TEXT = "도면 to 텍스트"


def _api_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
        detail = payload.get("detail", response.text)
        if isinstance(detail, list):
            return str(detail)
        return str(detail)
    except Exception:
        return response.text or f"HTTP {response.status_code}"


def api_health() -> dict[str, Any]:
    try:
        response = requests.get(f"{BACKEND_URL}/health", timeout=5)
        response.raise_for_status()
        data = response.json()
        data["reachable"] = True
        return data
    except Exception:
        return {"ok": False, "has_openai_key": False, "drawing_version": "", "reachable": False}


def api_summarize(text: str) -> dict[str, Any]:
    response = requests.post(f"{BACKEND_URL}/summarize", json={"text": text}, timeout=60)
    if response.status_code >= 400:
        raise RuntimeError(_api_detail(response))
    return response.json()


def api_render(spec: dict[str, Any], history_id: int | None) -> bytes:
    response = requests.post(
        f"{BACKEND_URL}/render",
        json={"spec": spec, "history_id": history_id},
        timeout=60,
    )
    if response.status_code >= 400:
        raise RuntimeError(_api_detail(response))
    return response.content


def api_extract(file_bytes: bytes, filename: str, mime: str) -> dict[str, Any]:
    response = requests.post(
        f"{BACKEND_URL}/extract",
        files={"file": (filename, file_bytes, mime or "application/octet-stream")},
        timeout=90,
    )
    if response.status_code >= 400:
        raise RuntimeError(_api_detail(response))
    return response.json()

PAGE_CSS = """
<style>
html, body, [class*="css"], .stApp, .stMarkdown, button, input, textarea {
  font-family: "Noto Sans KR", "OpenAI Sans", "Söhne", "Helvetica Neue", Helvetica, Arial, system-ui, sans-serif;
}

[data-testid="stHeader"] { background: transparent; }
[data-testid="stToolbar"] { display: none; }
.stAppDeployButton { display: none; }
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }

.stApp { background: #ffffff; color: #0d0d0d; }

.block-container {
  max-width: 768px;
  padding-top: 36px;
  padding-bottom: 96px;
}

.st-key-mode_text_to_drawing button,
.st-key-mode_drawing_to_text button {
  height: 44px !important;
  font-weight: 600 !important;
  letter-spacing: -0.01em;
}

[data-testid="stFileUploader"] {
  border: 1px dashed #d1d1d1;
  border-radius: 16px;
  padding: 8px 12px;
  background: #f7f7f8;
}
[data-testid="stFileUploader"] section {
  border: none !important;
}

.hero { text-align: center; margin-bottom: 48px; }
.badge {
  display: inline-flex;
  background: #d9f2ea;
  color: #1a7f64;
  font-size: 12px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 6px;
  margin-bottom: 16px;
}
.hero h1 {
  font-size: 32px;
  line-height: 40px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: #0d0d0d;
  margin: 0 0 12px 0;
}
.hero p {
  color: #6e6e80;
  font-size: 16px;
  font-weight: 400;
  line-height: 26px;
  margin: 0 auto;
  max-width: 640px;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
  background: #ffffff;
  border: 1px solid #e5e5e5 !important;
  border-radius: 12px !important;
  box-shadow: none !important;
}

[data-testid="stTextArea"] textarea {
  border: 1px solid #e5e5e5 !important;
  border-radius: 26px !important;
  background: #ffffff !important;
  min-height: 120px !important;
  color: #0d0d0d !important;
  font-size: 16px !important;
  line-height: 1.6 !important;
  padding: 14px 18px !important;
}
[data-testid="stTextArea"] textarea:focus {
  border-color: #b4b4b4 !important;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08) !important;
}

[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input {
  border: 1px solid #d1d1d1 !important;
  border-radius: 8px !important;
  background: #ffffff !important;
  color: #0d0d0d !important;
  font-size: 15px !important;
  height: 44px !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus {
  border-color: #10a37f !important;
  box-shadow: 0 0 0 3px rgba(16,163,127,0.2) !important;
}

div[data-testid="stButton"] > button {
  border-radius: 12px;
  font-weight: 500;
  font-size: 15px;
  height: 48px;
}
div[data-testid="stButton"] > button[kind="primary"] {
  background: #0d0d0d !important;
  border: none !important;
  color: #ffffff !important;
}
div[data-testid="stButton"] > button[kind="primary"]:hover {
  background: #2d2d2d !important;
}
div[data-testid="stButton"] > button[kind="primary"]:disabled {
  background: #e5e5e5 !important;
  color: #9b9b9b !important;
}
div[data-testid="stButton"] > button[kind="secondary"] {
  background: #ffffff !important;
  border: 1px solid #d1d1d1 !important;
  color: #0d0d0d !important;
}
div[data-testid="stButton"] > button[kind="secondary"]:hover {
  background: #f7f7f8 !important;
  border-color: #0d0d0d !important;
}

.st-key-send_parse button {
  border-radius: 9999px !important;
  width: 48px;
  min-width: 48px;
  height: 48px;
  padding: 0;
  background: #10a37f !important;
  color: #ffffff !important;
  border: none !important;
}
.st-key-send_parse button:hover {
  background: #1a7f64 !important;
}

.section-title {
  font-size: 20px;
  line-height: 28px;
  font-weight: 600;
  color: #0d0d0d;
  margin: 4px 0 4px 0;
}
.section-cap {
  color: #6e6e80;
  font-size: 14px;
  line-height: 22px;
  margin-bottom: 16px;
}

@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; }
}
</style>
"""


def init_session() -> None:
    defaults: dict[str, Any] = {
        "app_mode": MODE_TEXT_TO_DRAWING,
        "spec": None,
        "confirmed": False,
        "error": None,
        "show_guide": False,
        "form_rev": 0,
        "png_bytes": None,
        "history_id": None,
        "uploaded_drawing_name": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_workspace() -> None:
    st.session_state.spec = None
    st.session_state.confirmed = False
    st.session_state.error = None
    st.session_state.png_bytes = None
    st.session_state.history_id = None
    st.session_state.uploaded_drawing_name = None
    st.session_state.form_rev = int(st.session_state.get("form_rev", 0)) + 1


def render_mode_toggle() -> str:
    current = st.session_state.get("app_mode", MODE_TEXT_TO_DRAWING)
    left, right = st.columns(2, gap="small")
    with left:
        picked_text = st.button(
            LABEL_TEXT_TO_DRAWING,
            key="mode_text_to_drawing",
            type="primary" if current == MODE_TEXT_TO_DRAWING else "secondary",
            use_container_width=True,
        )
    with right:
        picked_drawing = st.button(
            LABEL_DRAWING_TO_TEXT,
            key="mode_drawing_to_text",
            type="primary" if current == MODE_DRAWING_TO_TEXT else "secondary",
            use_container_width=True,
        )
    if picked_text and current != MODE_TEXT_TO_DRAWING:
        reset_workspace()
        st.session_state.app_mode = MODE_TEXT_TO_DRAWING
        st.rerun()
    if picked_drawing and current != MODE_DRAWING_TO_TEXT:
        reset_workspace()
        st.session_state.app_mode = MODE_DRAWING_TO_TEXT
        st.rerun()
    return st.session_state.get("app_mode", MODE_TEXT_TO_DRAWING)


def form_key(name: str) -> str:
    return f"{name}_{st.session_state.get('form_rev', 0)}"


def spec_from_form(base: SpecDraft) -> SpecDraft:
    updated = base.model_copy(deep=True)
    updated.meta.title = st.session_state.get(form_key("fld_title")) or updated.meta.title
    updated.meta.purpose = st.session_state.get(form_key("fld_purpose")) or updated.meta.purpose
    params = updated.solid.params
    if updated.solid.type == "cylinder":
        count = max(len(cylinder_steps_of(updated)), 1)
        steps: list[CylinderStep] = []
        for index in range(count):
            steps.append(
                CylinderStep(
                    outer_diameter=st.session_state.get(form_key(f"step_{index}_od")),
                    inner_diameter=st.session_state.get(form_key(f"step_{index}_id")) or 0,
                    length=st.session_state.get(form_key(f"step_{index}_len")),
                    outer_tol_plus=st.session_state.get(form_key(f"step_{index}_od_tp")),
                    outer_tol_minus=st.session_state.get(form_key(f"step_{index}_od_tm")),
                    inner_tol_plus=st.session_state.get(form_key(f"step_{index}_id_tp")),
                    inner_tol_minus=st.session_state.get(form_key(f"step_{index}_id_tm")),
                )
            )
        params.steps = steps
        sync_cylinder_params(updated)
    else:
        for key, _label in dim_fields(updated.solid.type):
            setattr(params, key, st.session_state.get(form_key(f"fld_{key}")))
    return updated


def replace_cylinder_steps(spec: SpecDraft, steps: list[CylinderStep]) -> None:
    spec.solid.params.steps = steps or [CylinderStep(inner_diameter=0)]
    sync_cylinder_params(spec)
    st.session_state.spec = spec
    st.session_state.confirmed = False
    st.session_state.png_bytes = None
    st.session_state.form_rev = int(st.session_state.get("form_rev", 0)) + 1
    st.rerun()


def dim_input(label: str, key_name: str, value: float | None, *, step: float = 1.0) -> None:
    key = form_key(key_name)
    kwargs: dict[str, Any] = {"min_value": 0.0, "step": step, "key": key}
    if key not in st.session_state:
        kwargs["value"] = float(value or 0)
    st.number_input(label, **kwargs)


def run_parse(user_text: str, has_key: bool) -> None:
    st.session_state.confirmed = False
    st.session_state.error = None
    st.session_state.spec = None
    st.session_state.png_bytes = None
    st.session_state.history_id = None
    if not has_key:
        st.session_state.error = "OPENAI_API_KEY가 없습니다. `.env`에 키를 넣으세요."
        return
    if not user_text.strip():
        st.session_state.error = "설명을 입력하세요."
        return
    try:
        payload = api_summarize(user_text.strip())
        st.session_state.spec = SpecDraft.model_validate(payload["spec"])
        st.session_state.history_id = payload.get("id")
        st.session_state.form_rev = int(st.session_state.get("form_rev", 0)) + 1
        st.rerun()
    except Exception as exc:
        message = str(exc)
        st.session_state.error = message if message.startswith("LLM 파싱 실패") else f"LLM 파싱 실패: {exc}"


def run_extract(uploaded: Any, has_key: bool) -> None:
    st.session_state.confirmed = False
    st.session_state.error = None
    st.session_state.spec = None
    st.session_state.png_bytes = None
    st.session_state.history_id = None
    if not has_key:
        st.session_state.error = "OPENAI_API_KEY가 없습니다. `.env`에 키를 넣으세요."
        return
    if uploaded is None:
        st.session_state.error = "도면 이미지를 업로드하세요."
        return
    try:
        payload = api_extract(uploaded.getvalue(), uploaded.name, uploaded.type or "")
        st.session_state.spec = SpecDraft.model_validate(payload["spec"])
        st.session_state.history_id = payload.get("id")
        st.session_state.uploaded_drawing_name = uploaded.name
        st.session_state.form_rev = int(st.session_state.get("form_rev", 0)) + 1
        st.rerun()
    except Exception as exc:
        st.session_state.error = f"도면 치수 추출 실패: {exc}"


def start_render(spec: SpecDraft) -> None:
    try:
        confirmed = spec_from_form(spec)
        gaps = missing_dimension_labels(confirmed)
        if confirmed.unsupported:
            st.session_state.confirmed = False
            st.session_state.png_bytes = None
            st.session_state.error = "지원하지 않는 형상이라 도면을 만들지 않습니다."
        elif gaps:
            st.session_state.confirmed = False
            st.session_state.png_bytes = None
            st.session_state.error = "치수가 비어 있습니다: " + ", ".join(gaps)
        else:
            st.session_state.spec = confirmed
            st.session_state.confirmed = True
            st.session_state.error = None
            st.session_state.png_bytes = api_render(
                confirmed.model_dump(),
                st.session_state.get("history_id"),
            )
            st.session_state.drawing_version = st.session_state.get("backend_drawing_version")
    except Exception as exc:
        st.session_state.confirmed = False
        st.session_state.png_bytes = None
        st.session_state.error = f"도면 생성 실패: {exc}"
    st.rerun()


def render_cylinder_steps(spec: SpecDraft) -> None:
    steps = cylinder_steps_of(spec)
    if st.button("단 추가", use_container_width=True):
        updated = spec_from_form(spec)
        replace_cylinder_steps(updated, cylinder_steps_of(updated) + [CylinderStep(inner_diameter=0)])

    for index, step in enumerate(steps):
        st.markdown(f"**단 {index + 1}**")
        od, idia, slen = st.columns(3)
        with od:
            dim_input("외경 mm", f"step_{index}_od", step.outer_diameter)
        with idia:
            dim_input("내경 mm", f"step_{index}_id", step.inner_diameter or 0)
        with slen:
            dim_input("길이 mm", f"step_{index}_len", step.length)
        otp, otm, spacer = st.columns(3)
        with otp:
            dim_input("외경 +공차 mm", f"step_{index}_od_tp", getattr(step, "outer_tol_plus", None), step=0.01)
        with otm:
            dim_input("외경 −공차 mm", f"step_{index}_od_tm", getattr(step, "outer_tol_minus", None), step=0.01)
        with spacer:
            st.caption("0이면 도면에 공차를 쓰지 않습니다.")
        itp, itm, _empty = st.columns(3)
        with itp:
            dim_input("내경 +공차 mm", f"step_{index}_id_tp", getattr(step, "inner_tol_plus", None), step=0.01)
        with itm:
            dim_input("내경 −공차 mm", f"step_{index}_id_tm", getattr(step, "inner_tol_minus", None), step=0.01)
        up_col, down_col, del_col = st.columns(3)
        with up_col:
            if st.button("위로", key=form_key(f"step_up_{index}"), use_container_width=True, disabled=index == 0):
                updated = spec_from_form(spec)
                current = cylinder_steps_of(updated)
                current[index - 1], current[index] = current[index], current[index - 1]
                replace_cylinder_steps(updated, current)
        with down_col:
            if st.button(
                "아래로",
                key=form_key(f"step_down_{index}"),
                use_container_width=True,
                disabled=index >= len(steps) - 1,
            ):
                updated = spec_from_form(spec)
                current = cylinder_steps_of(updated)
                current[index + 1], current[index] = current[index], current[index + 1]
                replace_cylinder_steps(updated, current)
        with del_col:
            if st.button(
                "삭제",
                key=form_key(f"step_del_{index}"),
                use_container_width=True,
                disabled=len(steps) <= 1,
            ):
                updated = spec_from_form(spec)
                current = cylinder_steps_of(updated)
                replace_cylinder_steps(updated, [item for i, item in enumerate(current) if i != index])

    total_length = 0.0
    for index, step in enumerate(steps):
        length_key = form_key(f"step_{index}_len")
        if length_key in st.session_state:
            total_length += float(st.session_state.get(length_key) or 0)
        else:
            total_length += float(step.length or 0)
    st.markdown(
        f'<div class="section-title">총 기장 {total_length:g} mm</div>'
        '<div class="section-cap">총 기장은 각 단 길이의 합입니다.</div>',
        unsafe_allow_html=True,
    )


def confirm_caption(shape: str, *, drawing_to_text: bool = False) -> str:
    if shape == "cylinder":
        return "원기둥은 단별 외경·내경·길이입니다. 외경·내경 공차는 +/− 로 넣을 수 있고, 양쪽이 같으면 ±로 그립니다. 중실이면 내경은 0입니다."
    if shape == "plate":
        if drawing_to_text:
            return "판재는 길이, 폭, 두께입니다. 도면에서 읽은 숫자를 확인하고 필요하면 고치세요."
        return "판재는 길이, 폭, 두께입니다. 확인 전에는 도면을 그리지 않습니다."
    if drawing_to_text:
        return "세로는 깊이로 두었습니다. 높이와 바뀌었으면 여기서 고치세요. 도면에서 읽은 숫자를 확인하고 필요하면 고치세요."
    return "세로는 깊이로 두었습니다. 높이와 바뀌었으면 여기서 고치세요. 확인 전에는 도면을 그리지 않습니다."


def load_session_spec() -> SpecDraft | None:
    spec: SpecDraft | None = st.session_state.spec
    if spec is None:
        return None
    try:
        spec = normalize_spec(spec)
    except Exception:
        st.session_state.spec = None
        st.session_state.confirmed = False
        st.session_state.png_bytes = None
        st.session_state.error = "이전 스펙 형식이 오래되어 다시 추출해 주세요."
        st.rerun()
        return None
    st.session_state.spec = spec
    return spec


def render_spec_table(spec: SpecDraft, *, show_render_button: bool) -> None:
    drawing_to_text = not show_render_button
    with st.container(border=True):
        st.markdown('<div class="section-title">치수 확인</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="section-cap">{confirm_caption(spec.solid.type, drawing_to_text=drawing_to_text)}</div>',
            unsafe_allow_html=True,
        )

        if spec.unsupported:
            if drawing_to_text:
                st.warning("지원하지 않는 형상이라 치수를 모두 채우지 못할 수 있습니다.")
            else:
                st.warning("지원하지 않는 형상이라 도면을 만들지 않습니다.")
        if spec.notes:
            st.info(" / ".join(spec.notes))
        if spec.missing_fields:
            st.warning("비워 둔 필드: " + ", ".join(spec.missing_fields))

        c1, c2, c3 = st.columns(3)
        with c1:
            st.text_input("형상", value=SHAPE_LABELS.get(spec.solid.type, spec.solid.type), disabled=True)
        with c2:
            title_kwargs: dict[str, Any] = {"key": form_key("fld_title")}
            if form_key("fld_title") not in st.session_state:
                title_kwargs["value"] = spec.meta.title or ""
            st.text_input("품명", **title_kwargs)
        with c3:
            purpose_kwargs: dict[str, Any] = {"key": form_key("fld_purpose")}
            if form_key("fld_purpose") not in st.session_state:
                purpose_kwargs["value"] = spec.meta.purpose or ""
            st.text_input("용도", **purpose_kwargs)

        fields = dim_fields(spec.solid.type)
        is_cylinder = spec.solid.type == "cylinder" or bool(spec.solid.params.steps)
        if is_cylinder:
            spec.solid.type = "cylinder"
            render_cylinder_steps(spec)
        elif fields:
            cols = st.columns(len(fields))
            for column, (key, label) in zip(cols, fields):
                with column:
                    dim_input(f"{label} mm", f"fld_{key}", getattr(spec.solid.params, key))

        with st.expander("원본 스펙 JSON"):
            st.json(spec.model_dump())

        if show_render_button and st.button("확인 후 도면 생성", type="primary", use_container_width=True):
            start_render(spec)


def render_drawing_preview(spec: SpecDraft) -> None:
    if not st.session_state.confirmed:
        return

    if st.session_state.get("drawing_version") != st.session_state.get("backend_drawing_version"):
        try:
            st.session_state.png_bytes = api_render(
                spec.model_dump(),
                st.session_state.get("history_id"),
            )
            st.session_state.drawing_version = st.session_state.get("backend_drawing_version")
        except Exception as exc:
            st.session_state.error = f"도면 생성 실패: {exc}"
            st.session_state.confirmed = False
            st.rerun()
            return

    with st.container(border=True):
        st.markdown('<div class="section-title">도면</div>', unsafe_allow_html=True)
        png_bytes = st.session_state.get("png_bytes")
        if png_bytes:
            st.image(png_bytes, use_container_width=True)
            title = st.session_state.spec.meta.title or "drawing"
            st.download_button(
                "PNG 다운로드",
                data=png_bytes,
                file_name=f"{title}.png",
                mime="image/png",
                type="primary",
                use_container_width=True,
            )
        else:
            st.error("도면 이미지가 없습니다. 확인 후 도면 생성을 다시 눌러 주세요.")


def render_health_errors(health: dict[str, Any], *, drawing_to_text: bool) -> bool:
    has_key = bool(health.get("has_openai_key"))
    if not health.get("reachable"):
        st.error("백엔드에 연결할 수 없습니다. 다른 터미널에서 `uvicorn backend.main:app --reload --port 8000` 을 실행하세요.")
    elif not has_key:
        if drawing_to_text:
            st.error("OPENAI_API_KEY가 없습니다. `.env`에 키를 넣으세요. 키가 없으면 치수표를 만들지 않습니다.")
        else:
            st.error("OPENAI_API_KEY가 없습니다. `.env`에 키를 넣으세요. 키가 없으면 도면을 만들지 않습니다.")
    return has_key


def render_text_to_drawing_flow(has_key: bool) -> None:
    st.markdown(
        """
        <div class="hero">
          <div class="badge">교육용</div>
          <h1>텍스트로 도면을 만듭니다</h1>
          <p>설명을 보내면 형상에 맞는 치수를 정리해 보여 줍니다. 숫자를 확인한 뒤에만 PNG를 그립니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    text_col, send_col = st.columns([10, 1], vertical_alignment="bottom")
    with text_col:
        user_text = st.text_area(
            "도면 설명",
            height=120,
            label_visibility="collapsed",
            placeholder="메시지를 입력하세요. 예: 선반용 상자, 가로 400mm, 세로 300mm, 높이 250mm.",
            key="user_text",
        )
    with send_col:
        send_clicked = st.button("↑", key="send_parse", help="스펙 추출")

    if st.button("사용 방법", type="secondary", use_container_width=True):
        st.session_state.show_guide = not st.session_state.show_guide

    if send_clicked:
        run_parse(user_text, has_key)

    if st.session_state.show_guide:
        with st.container(border=True):
            st.markdown('<div class="section-title">사용 방법</div>', unsafe_allow_html=True)
            st.markdown(
                """
1. 부품을 한국어로 설명하고 스펙을 추출합니다.
2. 표에서 치수를 확인하고 필요하면 고칩니다. 원기둥은 단별 외경·내경·길이와 공차를 넣을 수 있습니다.
3. 확인 후 도면 생성을 눌러야 PNG를 그립니다. 추출과 렌더를 한 번에 하지 않습니다.
4. API 키가 없거나 스키마가 어긋나면 도면을 만들지 않습니다.
                """
            )

    if st.session_state.error:
        st.error(st.session_state.error)

    spec = load_session_spec()
    if spec is None:
        return
    render_spec_table(spec, show_render_button=True)
    render_drawing_preview(spec)


def render_drawing_to_text_flow(has_key: bool) -> None:
    st.markdown(
        """
        <div class="hero">
          <div class="badge">교육용</div>
          <h1>도면에서 치수를 읽습니다</h1>
          <p>도면을 올리면 형상에 맞는 치수표를 만들어 보여 줍니다. 표 형태는 텍스트 to 도면의 치수 확인과 같습니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    uploaded = st.file_uploader(
        "도면 업로드 (PNG, JPG, WEBP)",
        type=["png", "jpg", "jpeg", "webp"],
        key="drawing_upload",
    )
    if uploaded is not None:
        st.image(uploaded, use_container_width=True, caption=uploaded.name)

    extract_clicked = st.button("치수표 생성", type="primary", use_container_width=True, key="extract_spec")

    if st.button("사용 방법", type="secondary", use_container_width=True):
        st.session_state.show_guide = not st.session_state.show_guide

    if extract_clicked:
        run_extract(uploaded, has_key)

    if st.session_state.show_guide:
        with st.container(border=True):
            st.markdown('<div class="section-title">사용 방법</div>', unsafe_allow_html=True)
            st.markdown(
                """
1. 도면 이미지(PNG, JPG, WEBP)를 올립니다.
2. 치수표 생성을 누르면 치수선·표제란을 읽어 표를 만듭니다.
3. 표 형태는 텍스트 to 도면의 치수 확인과 같습니다. 숫자가 비어 있으면 여기서 고칩니다.
4. 이 흐름의 최종 산출물은 치수표입니다. 도면 PNG는 만들지 않습니다.
                """
            )

    if st.session_state.error:
        st.error(st.session_state.error)

    spec = load_session_spec()
    if spec is None:
        return
    render_spec_table(spec, show_render_button=False)


def main() -> None:
    st.set_page_config(page_title="텍스트 도면 생성기", layout="centered")
    init_session()
    st.markdown(PAGE_CSS, unsafe_allow_html=True)
    mode = render_mode_toggle()

    health = api_health()
    st.session_state.backend_drawing_version = health.get("drawing_version") or ""
    has_key = render_health_errors(health, drawing_to_text=mode == MODE_DRAWING_TO_TEXT)

    if mode == MODE_DRAWING_TO_TEXT:
        render_drawing_to_text_flow(has_key)
        return
    render_text_to_drawing_flow(has_key)


if __name__ == "__main__":
    main()
