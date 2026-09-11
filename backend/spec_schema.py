"""도면 Spec JSON — Pydantic 스키마."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


def _as_number(value: Any) -> float | None:
    if value is None or value is False:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        digits = []
        for ch in text:
            if ch.isdigit() or ch in ".-":
                digits.append(ch)
            elif digits:
                break
        if not digits:
            return None
        try:
            return float("".join(digits))
        except ValueError:
            return None
    return None


class HoleCenter(BaseModel):
    u: float | None = None
    v: float | None = None


class Feature(BaseModel):
    type: str = "hole"
    face: str = "front"
    diameter: float | None = None
    center: HoleCenter = Field(default_factory=HoleCenter)

    @field_validator("center", mode="before")
    @classmethod
    def empty_center(cls, value: Any) -> Any:
        return {} if value is None else value

    @field_validator("diameter", mode="before")
    @classmethod
    def coerce_diameter(cls, value: Any) -> Any:
        return _as_number(value)


class CylinderStep(BaseModel):
    outer_diameter: float | None = None
    inner_diameter: float | None = 0
    length: float | None = None
    outer_tol_plus: float | None = None
    outer_tol_minus: float | None = None
    inner_tol_plus: float | None = None
    inner_tol_minus: float | None = None

    @field_validator(
        "outer_diameter",
        "inner_diameter",
        "length",
        "outer_tol_plus",
        "outer_tol_minus",
        "inner_tol_plus",
        "inner_tol_minus",
        mode="before",
    )
    @classmethod
    def coerce_dim(cls, value: Any) -> Any:
        return _as_number(value)


class SolidParams(BaseModel):
    width: float | None = None
    depth: float | None = None
    height: float | None = None
    diameter: float | None = None
    length: float | None = None
    thickness: float | None = None
    outer_diameter: float | None = None
    inner_diameter: float | None = None
    overall_length: float | None = None
    steps: list[CylinderStep] = Field(default_factory=list)

    @field_validator(
        "width",
        "depth",
        "height",
        "diameter",
        "length",
        "thickness",
        "outer_diameter",
        "inner_diameter",
        "overall_length",
        mode="before",
    )
    @classmethod
    def coerce_dim(cls, value: Any) -> Any:
        return _as_number(value)

    @field_validator("steps", mode="before")
    @classmethod
    def empty_steps(cls, value: Any) -> Any:
        return [] if value is None else value


class Solid(BaseModel):
    type: str = "box"
    params: SolidParams = Field(default_factory=SolidParams)

    @field_validator("params", mode="before")
    @classmethod
    def empty_params(cls, value: Any) -> Any:
        return {} if value is None else value


class SpecMeta(BaseModel):
    title: str = ""
    purpose: str = ""
    material: str = ""
    unit: str = "mm"

    @field_validator("title", "purpose", "material", mode="before")
    @classmethod
    def empty_str(cls, value: Any) -> Any:
        return "" if value is None else str(value)


class SpecDraft(BaseModel):
    schema_version: str = "1.0"
    meta: SpecMeta = Field(default_factory=SpecMeta)
    solid: Solid = Field(default_factory=Solid)
    features: list[Feature] = Field(default_factory=list)
    views: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    unsupported: bool = False
    notes: list[str] = Field(default_factory=list)

    @field_validator("meta", "solid", mode="before")
    @classmethod
    def empty_object(cls, value: Any) -> Any:
        return {} if value is None else value

    @field_validator("schema_version", mode="before")
    @classmethod
    def version_str(cls, value: Any) -> Any:
        return "1.0" if value is None else str(value)

    @field_validator("features", "notes", "missing_fields", "views", mode="before")
    @classmethod
    def empty_list(cls, value: Any) -> Any:
        return [] if value is None else value


SUPPORTED = ("box", "cylinder", "plate")
SHAPE_LABELS = {"box": "직육면체", "cylinder": "원기둥", "plate": "판재"}
SHAPE_ALIASES = {
    "box": "box",
    "cylinder": "cylinder",
    "plate": "plate",
    "직육면체": "box",
    "상자": "box",
    "박스": "box",
    "원기둥": "cylinder",
    "파이프": "cylinder",
    "원통": "cylinder",
    "축": "cylinder",
    "다단": "cylinder",
    "다단 원기둥": "cylinder",
    "다단원기둥": "cylinder",
    "2단 원기둥": "cylinder",
    "3단 원기둥": "cylinder",
    "계단 축": "cylinder",
    "stepped_cylinder": "cylinder",
    "stepped": "cylinder",
    "multi_cylinder": "cylinder",
    "판재": "plate",
    "판": "plate",
}

_CYLINDER_HINTS = (
    "원기둥",
    "원통",
    "파이프",
    "cylinder",
    "stepped",
    "shaft",
    "다단",
)


def canonical_type(raw: str) -> str:
    text = (raw or "").strip()
    if text in SHAPE_ALIASES:
        return SHAPE_ALIASES[text]
    lower = text.lower()
    if lower in SHAPE_ALIASES:
        return SHAPE_ALIASES[lower]
    if any(hint in text or hint in lower for hint in _CYLINDER_HINTS):
        return "cylinder"
    return lower or "box"


def rehydrate_spec(spec: SpecDraft | dict[str, Any]) -> SpecDraft:
    if isinstance(spec, SpecDraft):
        data = spec.model_dump()
    else:
        data = spec
    return SpecDraft.model_validate(data)


def format_tolerance(plus: float | None, minus: float | None) -> str:
    plus_v = abs(float(plus)) if plus else 0.0
    minus_v = abs(float(minus)) if minus else 0.0
    if plus_v == 0 and minus_v == 0:
        return ""
    if plus_v == minus_v:
        return f"±{plus_v:g}"
    parts: list[str] = []
    if plus_v:
        parts.append(f"+{plus_v:g}")
    if minus_v:
        parts.append(f"-{minus_v:g}")
    return "/".join(parts)


def format_diameter_label(value: float, plus: float | None = None, minus: float | None = None) -> str:
    label = f"Ø{value:g}"
    tol = format_tolerance(plus, minus)
    return f"{label} {tol}".strip() if tol else label


def cylinder_steps_of(spec: SpecDraft) -> list[CylinderStep]:
    params = spec.solid.params
    raw_steps = getattr(params, "steps", None) or []
    if raw_steps:
        return [step if isinstance(step, CylinderStep) else CylinderStep.model_validate(step) for step in raw_steps]
    return [
        CylinderStep(
            outer_diameter=getattr(params, "outer_diameter", None) or params.diameter,
            inner_diameter=getattr(params, "inner_diameter", None) or 0,
            length=getattr(params, "overall_length", None) or params.length or params.height,
        )
    ]


def sync_cylinder_params(spec: SpecDraft) -> SpecDraft:
    steps = cylinder_steps_of(spec)
    if not steps:
        steps = [CylinderStep(inner_diameter=0)]
    spec.solid.params.steps = steps
    overall = sum(float(step.length or 0) for step in steps) or None
    spec.solid.params.overall_length = overall
    spec.solid.params.length = overall
    spec.solid.params.height = overall
    spec.solid.params.outer_diameter = steps[0].outer_diameter
    spec.solid.params.inner_diameter = steps[0].inner_diameter or 0
    spec.solid.params.diameter = steps[0].outer_diameter
    return spec


def _notes_reject_supported_cylinder(notes: list[str]) -> bool:
    joined = " ".join(notes)
    return any(token in joined for token in ("다단", "원기둥", "cylinder", "단"))


def normalize_spec(spec: SpecDraft) -> SpecDraft:
    spec = rehydrate_spec(spec)
    spec.schema_version = spec.schema_version or "1.0"
    spec.meta.unit = "mm"
    has_steps = bool(getattr(spec.solid.params, "steps", None))
    spec.solid.type = canonical_type(spec.solid.type)
    if has_steps:
        spec.solid.type = "cylinder"
    if spec.solid.type == "cylinder":
        spec.unsupported = False
        if spec.notes and _notes_reject_supported_cylinder(spec.notes):
            spec.notes = [note for note in spec.notes if "지원" not in note]
        spec.views = ["front"]
        sync_cylinder_params(spec)
    elif spec.solid.type not in SUPPORTED:
        spec.unsupported = True
    elif not spec.views:
        spec.views = ["front", "top", "right"]
    return spec


def dim_fields(shape: str) -> list[tuple[str, str]]:
    if shape == "plate":
        return [("length", "길이"), ("width", "폭"), ("thickness", "두께")]
    if shape == "box":
        return [("width", "가로(폭)"), ("depth", "세로(깊이)"), ("height", "높이")]
    return []


def missing_dimension_labels(spec: SpecDraft) -> list[str]:
    if spec.solid.type == "cylinder":
        missing: list[str] = []
        steps = cylinder_steps_of(spec)
        if not steps:
            missing.append("단 치수")
        for index, step in enumerate(steps, start=1):
            if not step.outer_diameter:
                missing.append(f"단 {index} 외경")
            if not step.length:
                missing.append(f"단 {index} 길이")
            if step.inner_diameter and step.outer_diameter and step.inner_diameter >= step.outer_diameter:
                missing.append(f"단 {index} 내경(외경보다 작아야 함)")
        return missing
    params = spec.solid.params
    missing = []
    for key, label in dim_fields(spec.solid.type):
        value = getattr(params, key, None)
        if value is None or value <= 0:
            missing.append(label)
    return missing


def solid_extents(spec: SpecDraft) -> tuple[float, float, float]:
    p = spec.solid.params
    if spec.solid.type == "cylinder":
        steps = cylinder_steps_of(spec)
        diameter = max((float(step.outer_diameter or 0) for step in steps), default=1.0) or 1.0
        height = sum(float(step.length or 0) for step in steps) or max(float(p.height or 0), 1.0)
        return max(diameter, 1.0), max(diameter, 1.0), max(height, 1.0)
    if spec.solid.type == "plate":
        return (
            max(float(p.length or p.width or 0), 1.0),
            max(float(p.width or p.depth or 0), 1.0),
            max(float(p.thickness or p.height or 0), 1.0),
        )
    return (
        max(float(p.width or 0), 1.0),
        max(float(p.depth or 0), 1.0),
        max(float(p.height or 0), 1.0),
    )
