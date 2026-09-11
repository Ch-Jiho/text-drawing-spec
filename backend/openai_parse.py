"""OpenAI로 한국어 텍스트·도면 이미지를 Spec JSON으로만 변환한다. 규칙 파서 폴백 없음."""

from __future__ import annotations

import base64
import json
import os
from io import BytesIO

from openai import OpenAI
from PIL import Image

from spec_schema import SpecDraft, normalize_spec

SYSTEM_PROMPT = """너는 한국어 자연어를 기술 도면용 JSON 스펙으로만 변환한다.
설명 문장, 마크다운, 코드펜스 없이 JSON 객체만 출력한다.

규칙:
- 지원 형상은 box, cylinder, plate 만.
- 2단·3단·다단 원기둥, 계단 축, 단이 여러 개인 원통은 전부 cylinder 이다.
  별도 형상으로 두지 말고 unsupported=false 로 두고 steps 에 단을 넣는다.
- 구, 원뿔, 나사처럼 위 세 가지가 아니면 unsupported=true 와 notes에 이유를 적는다.
- 모르는 스칼라 값은 null 로 두고 missing_fields 에 경로를 넣는다.
- features, views, notes, missing_fields 는 항상 배열이다. 없으면 [] 를 쓴다.
- 단위가 cm 또는 m 이면 mm 로 환산한 숫자만 넣는다. 예: 80cm → 800, 10cm → 100. meta.unit 은 항상 "mm".
- 가로 → width, 세로 → depth, 높이 → height. 세로를 높이로 바꾸지 않는다.
- box: solid.params.width, depth, height. views=["front","top","right"]
- cylinder: solid.type 은 반드시 "cylinder". views=["front"] 만.
  단(단1, 단2, 2단 …)이 있으면 solid.params.steps 배열을 쓴다.
  각 step: outer_diameter(외경/지름), inner_diameter(내경, 중실이면 0), length(그 단의 기장·축 길이),
  outer_tol_plus, outer_tol_minus, inner_tol_plus, inner_tol_minus (공차 mm, 없으면 null).
  ±0.1 이면 plus와 minus를 둘 다 0.1 로 둔다. +0.1/-0.05 이면 plus=0.1, minus=0.05.
  단이 없으면 steps를 원소 1개로 둔다.
  overall_length 는 각 step.length 의 합과 같게 둔다.
- plate: solid.params.length, width, thickness. views=["front","top","right"]
- 원형 구멍이 있으면 features에 { "type":"hole", "face":"front"|"top"|"right", "diameter":number, "center":{"u":number,"v":number} } 를 넣는다.
- schema_version 은 "1.0"

box 예시:
{
  "schema_version": "1.0",
  "meta": { "title": "선반용 상자", "purpose": "storage_box", "material": "wood", "unit": "mm" },
  "solid": { "type": "box", "params": { "width": 400, "depth": 300, "height": 250 } },
  "features": [],
  "views": ["front", "top", "right"],
  "missing_fields": [],
  "unsupported": false,
  "notes": []
}

다단 원기둥 예시 (2단 원기둥, 단1 기장 80cm 외경 10cm, 단2 기장 20cm 외경 20cm):
{
  "schema_version": "1.0",
  "meta": { "title": "2단 원기둥", "purpose": "", "material": "", "unit": "mm" },
  "solid": {
    "type": "cylinder",
    "params": {
      "steps": [
        {"outer_diameter": 100, "inner_diameter": 0, "length": 800, "outer_tol_plus": null, "outer_tol_minus": null, "inner_tol_plus": null, "inner_tol_minus": null},
        {"outer_diameter": 200, "inner_diameter": 0, "length": 200, "outer_tol_plus": null, "outer_tol_minus": null, "inner_tol_plus": null, "inner_tol_minus": null}
      ],
      "overall_length": 1000
    }
  },
  "features": [],
  "views": ["front"],
  "missing_fields": [],
  "unsupported": false,
  "notes": []
}
"""

VISION_PROMPT = (
    SYSTEM_PROMPT
    + """

추가 규칙 (도면 이미지):
- 입력은 기술 도면 이미지다. 치수선, 숫자, 표제란, 투상도를 읽고 Spec JSON으로만 변환한다.
- 치수선·표제란에 적힌 숫자를 우선한다. 픽셀 길이로 추정하지 않는다.
- 단위가 cm 또는 m 이면 mm 로 환산한다. 단위가 없으면 mm 로 본다. meta.unit 은 항상 "mm".
- 표제란의 품명·품번·용도가 있으면 meta.title, meta.purpose 에 넣는다.
- 다단 원기둥·계단 축은 cylinder 이고 steps 에 단을 채운다.
- 읽기 어려운 값은 null 로 두고 missing_fields 에 경로를 넣는다.
"""
)


def _openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY가 없습니다. 프로젝트 루트 .env에 키를 넣으세요.")
    return OpenAI(
        api_key=api_key,
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip() or "https://api.openai.com/v1",
    )


def _openai_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"


def _spec_from_llm_content(content: str | None) -> SpecDraft:
    if not content:
        raise RuntimeError("LLM이 빈 응답을 반환했습니다.")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("LLM 응답이 JSON이 아닙니다.") from exc
    return normalize_spec(SpecDraft.model_validate(data))


def prepare_image_for_vision(image_bytes: bytes) -> tuple[bytes, str]:
    try:
        image = Image.open(BytesIO(image_bytes))
        image.load()
    except Exception as exc:
        raise RuntimeError("이미지 파일을 읽을 수 없습니다.") from exc

    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")

    max_side = 2048
    width, height = image.size
    longest = max(width, height)
    if longest > max_side:
        scale = max_side / longest
        image = image.resize((max(1, int(width * scale)), max(1, int(height * scale))), Image.Resampling.LANCZOS)

    out = BytesIO()
    image.save(out, format="PNG")
    return out.getvalue(), "image/png"


def parse_text_to_spec(user_text: str) -> SpecDraft:
    response = _openai_client().chat.completions.create(
        model=_openai_model(),
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "다음 문장을 Spec JSON으로 변환하라.\n"
                    "다단·2단 원기둥은 cylinder 이며 지원한다. unsupported 로 두지 말고 steps 를 채워라.\n"
                    "필수 키: schema_version, meta, solid, features, views, notes, "
                    "missing_fields, unsupported\n\n"
                    f"{user_text}"
                ),
            },
        ],
    )
    return _spec_from_llm_content(response.choices[0].message.content)


def parse_image_to_spec(image_bytes: bytes, filename: str = "") -> SpecDraft:
    prepared, mime = prepare_image_for_vision(image_bytes)
    encoded = base64.b64encode(prepared).decode("ascii")
    label = filename.strip() or "drawing.png"
    response = _openai_client().chat.completions.create(
        model=_openai_model(),
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": VISION_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "이 도면 이미지를 Spec JSON으로 변환하라.\n"
                            f"파일명: {label}\n"
                            "다단·2단 원기둥은 cylinder 이며 지원한다. unsupported 로 두지 말고 steps 를 채워라.\n"
                            "필수 키: schema_version, meta, solid, features, views, notes, "
                            "missing_fields, unsupported"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{encoded}"},
                    },
                ],
            },
        ],
    )
    return _spec_from_llm_content(response.choices[0].message.content)
