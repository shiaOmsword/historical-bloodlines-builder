"""Versioned, immutable rendering settings; sizes are native points, not PDF points."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import math
import os
from pathlib import Path
from typing import Any

import yaml


class RenderConfigurationError(ValueError):
    """An explicit configuration is invalid; never silently fall back."""


def _number(name: str, value: object, minimum: float, maximum: float) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not minimum <= value <= maximum
        or not math.isfinite(value)
    ):
        raise RenderConfigurationError(
            f"{name}: expected a finite number between {minimum:g} and {maximum:g}"
        )


@dataclass(frozen=True, slots=True)
class TypographyConfig:
    font_size_pt: float = 13.2
    # None follows font size. Integer leading matches Graphviz HTML row heights.
    line_height_pt: float | None = None
    title_font_size_pt: float = 19.0
    note_font_size_pt: float = 9.0

    def __post_init__(self) -> None:
        _number("typography.font_size_pt", self.font_size_pt, 8, 32)
        _number("typography.title_font_size_pt", self.title_font_size_pt, 10, 48)
        _number("typography.note_font_size_pt", self.note_font_size_pt, 6, 24)
        if self.line_height_pt is not None:
            _number(
                "typography.line_height_pt", self.line_height_pt,
                self.font_size_pt * 1.05, self.font_size_pt * 3,
            )

    @property
    def resolved_line_height_pt(self) -> float:
        value = self.line_height_pt
        if value is None:
            value = self.font_size_pt * (15.0 / 13.2)
        # Use the SAME height in box measurement and HTML rows; otherwise a
        # fractional line height silently makes Graphviz taller than the router.
        return float(math.ceil(value - 1e-9))

    @property
    def note_line_height_pt(self) -> float:
        return 10.5 * (self.note_font_size_pt / 9.0)


@dataclass(frozen=True, slots=True)
class RenderLayoutConfig:
    person_gap_pt: float = 34.0
    component_gap_pt: float = 22.0
    layer_gap_pt: float = 30.0
    page_margin_x_pt: float = 18.0
    page_margin_y_pt: float = 16.0
    min_page_width_pt: float = 560.0
    max_text_line: int = 20
    max_name_line: int = 16

    def __post_init__(self) -> None:
        for name, low, high in (
            ("person_gap_pt", 24, 200),
            ("component_gap_pt", 12, 200),
            ("layer_gap_pt", 24, 200),
            ("page_margin_x_pt", 0, 200),
            ("page_margin_y_pt", 0, 200),
            ("min_page_width_pt", 100, 4000),
        ):
            _number(f"layout.{name}", getattr(self, name), low, high)
        for name in ("max_text_line", "max_name_line"):
            value = getattr(self, name)
            if type(value) is not int or not 4 <= value <= 120:
                raise RenderConfigurationError(f"layout.{name}: expected integer 4..120")


@dataclass(frozen=True, slots=True)
class PdfConfig:
    page_format: str = "a5"

    def __post_init__(self) -> None:
        if self.page_format not in ("a5", "a4"):
            raise RenderConfigurationError("pdf.page_format: expected a5 or a4")


@dataclass(frozen=True, slots=True)
class RenderConfig:
    version: int = 1
    typography: TypographyConfig = field(default_factory=TypographyConfig)
    layout: RenderLayoutConfig = field(default_factory=RenderLayoutConfig)
    pdf: PdfConfig = field(default_factory=PdfConfig)
    source_path: Path | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.version) is not int or self.version != 1:
            raise RenderConfigurationError("version: only version 1 is supported")

    def to_yaml(self) -> str:
        """A standalone snapshot of effective settings (no environment/secrets)."""
        values = {
            "version": self.version,
            "typography": asdict(self.typography),
            "layout": asdict(self.layout),
            "pdf": asdict(self.pdf),
        }
        values["typography"]["line_height_pt"] = self.typography.resolved_line_height_pt
        return yaml.safe_dump(values, sort_keys=False, allow_unicode=True)


class _ConfigLoader(yaml.SafeLoader):
    """Safe YAML without duplicate keys, merge keys or recursive aliases."""

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(yaml.AliasEvent):
            raise RenderConfigurationError("YAML aliases are not supported in render config")
        return super().compose_node(parent, index)

    def construct_mapping(self, node: Any, deep: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise RenderConfigurationError("Configuration keys must be strings")
            if key in result:
                raise RenderConfigurationError(f"Duplicate configuration key: {key}")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _mapping(value: Any, where: str, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RenderConfigurationError(f"{where}: expected a YAML mapping")
    unknown = set(value) - allowed
    if unknown:
        raise RenderConfigurationError(f"{where}: unknown keys: {', '.join(sorted(unknown))}")
    return value


def load_render_config(path: Path | str | None = None) -> RenderConfig:
    """Priority: explicit path > env > data/render.yaml > cwd/render.yaml > defaults.

    data means BLOODLINES_DATA_DIR, when set (in Docker this is /data). Relative
    explicit/environment paths resolve against cwd. Selected files are strict;
    omitted auto-discovery files are optional. A call returns a fresh snapshot.
    """
    selected: Path | None = None
    if path is not None:
        selected = Path(path).expanduser()
    elif os.getenv("BLOODLINES_RENDER_CONFIG"):
        selected = Path(os.environ["BLOODLINES_RENDER_CONFIG"]).expanduser()
    else:
        candidates = []
        if os.getenv("BLOODLINES_DATA_DIR"):
            candidates.append(Path(os.environ["BLOODLINES_DATA_DIR"]).expanduser() / "render.yaml")
        candidates.append(Path.cwd() / "render.yaml")
        selected = next((item for item in candidates if item.exists()), None)
    if selected is None:
        return RenderConfig()
    try:
        # Bound parsing cost even for accidentally selected large/binary files.
        with selected.open("rb") as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise RenderConfigurationError("Configuration exceeds 64 KiB")
        value = yaml.load(raw.decode("utf-8-sig"), Loader=_ConfigLoader)
        if value is None:  # A comment-only file is equivalent to defaults.
            value = {}
        root = _mapping(value, "root", {"version", "typography", "layout", "pdf"})
        sections = {}
        for name, cls in (
            ("typography", TypographyConfig), ("layout", RenderLayoutConfig), ("pdf", PdfConfig),
        ):
            section = _mapping(root.get(name, {}), name, {f.name for f in fields(cls)})
            sections[name] = cls(**section)
        return RenderConfig(version=root.get("version", 1), source_path=selected.resolve(), **sections)
    except (OSError, UnicodeError, yaml.YAMLError, RecursionError, RenderConfigurationError) as exc:
        raise RenderConfigurationError(f"Render config {selected}: {exc}") from exc
