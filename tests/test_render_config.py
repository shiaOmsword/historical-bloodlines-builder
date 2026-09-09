from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest
from openpyxl import Workbook
from pypdf import PdfReader
from typer.testing import CliRunner

from historical_bloodlines.application.services.build_genealogy import (
    BuildGenealogyUseCase, BuildResult,
)
from historical_bloodlines.config.render import (
    RenderConfig, RenderConfigurationError, TypographyConfig, load_render_config,
)
from historical_bloodlines.infrastructure.excel import ExcelGenealogyReader
from historical_bloodlines.infrastructure.graph import GraphvizGenealogyRenderer

ROOT = Path(__file__).resolve().parents[1]
HEADERS = ["\u2116", "\u0418\u043c\u044f", "\u0422\u0438\u0442\u0443\u043b", "\u041d\u0430\u0447\u0430\u043b\u043e \u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u044f", "\u041a\u043e\u043d\u0435\u0446 \u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u044f", "\u0414\u0435\u0442\u0438", "\u0411\u0440\u0430\u043a"]


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BLOODLINES_RENDER_CONFIG", raising=False)
    monkeypatch.delenv("BLOODLINES_DATA_DIR", raising=False)


@pytest.fixture
def workbook_path(tmp_path):
    path = tmp_path / "family.xlsx"
    book = Workbook()
    sheet = book.active
    sheet.title = "Config family"
    sheet.append(HEADERS)
    sheet.append([1, "Parent A", "King of a large country", 1000, 1020, "Child", "Parent B"])
    sheet.append([2, "Parent B", "Queen", None, None, "Child", "Parent A"])
    sheet.append([3, "Child", "Prince", None, None, "Grandchild", None])
    sheet.append([4, "Grandchild", None, None, None, None, None])
    book.save(path)
    return path


def write_config(path, font):
    path.write_text(f"typography:\n  font_size_pt: {font}\n", encoding="utf-8")
    return path


def test_defaults_and_explicit_default_preset():
    defaults = load_render_config()
    assert defaults == load_render_config(ROOT / "config/render.default.yaml")
    renderer = GraphvizGenealogyRenderer(defaults)
    assert (renderer.FONT_SIZE, renderer.LINE_HEIGHT) == (13.2, 15)
    assert renderer.MAX_HORIZONTAL_STRETCH == 1.0
    assert renderer.FONT_FAMILY == "Roboto"


@pytest.mark.parametrize("name,font,leading", [("plus2", 15.2, 18), ("plus3", 16.2, 19)])
def test_presets_and_instance_isolation(name, font, leading):
    config = load_render_config(ROOT / f"config/render.{name}.yaml")
    changed = GraphvizGenealogyRenderer(config)
    default = GraphvizGenealogyRenderer()
    assert (changed.FONT_SIZE, changed.LINE_HEIGHT) == (font, leading)
    assert (default.FONT_SIZE, default.LINE_HEIGHT) == (13.2, 15)
    assert changed._labels.line_height == leading


def test_partial_bom_and_snapshot(tmp_path):
    path = tmp_path / "style.yaml"
    path.write_text("\ufeff# \u0428\u0440\u0438\u0444\u0442\n" + "typography:\n  font_size_pt: 15.2\n", encoding="utf-8")
    cfg = load_render_config(path)
    assert cfg.layout.person_gap_pt == 34
    assert cfg.source_path == path.resolve()
    snapshot = tmp_path / "snapshot.yaml"
    snapshot.write_text(cfg.to_yaml(), encoding="utf-8")
    loaded = load_render_config(snapshot)
    assert loaded.typography.resolved_line_height_pt == 18
    assert loaded.to_yaml() == cfg.to_yaml()
    assert "source_path" not in cfg.to_yaml()


def test_fractional_leading_uses_same_integer_for_boxes_and_html(workbook_path):
    config = RenderConfig(typography=TypographyConfig(font_size_pt=15.2, line_height_pt=17.4))
    renderer = GraphvizGenealogyRenderer(config)
    builder = BuildGenealogyUseCase(render_config=config)
    genealogy = builder._assemble_sheet(ExcelGenealogyReader().read(workbook_path)[0])
    person = next(iter(genealogy.persons.values()))
    box = renderer._labels.measure(person)
    assert renderer.LINE_HEIGHT == 18
    assert box.height == len(box.lines) * 18 + 4
    assert 'HEIGHT="18"' in renderer._labels.html_label(person)


def test_discovery_and_priority(tmp_path, monkeypatch):
    local = write_config(tmp_path / "render.yaml", 14)
    data = tmp_path / "data"
    data.mkdir()
    mounted = write_config(data / "render.yaml", 15)
    env = write_config(tmp_path / "environment.yaml", 16)
    explicit = write_config(tmp_path / "explicit.yaml", 17)
    assert load_render_config().source_path == local
    monkeypatch.setenv("BLOODLINES_DATA_DIR", str(data))
    assert load_render_config().source_path == mounted
    monkeypatch.setenv("BLOODLINES_RENDER_CONFIG", str(env))
    assert load_render_config().source_path == env
    assert load_render_config(explicit).source_path == explicit
    env.unlink()
    with pytest.raises(RenderConfigurationError):
        load_render_config()
    assert load_render_config(explicit).typography.font_size_pt == 17
    with pytest.raises(RenderConfigurationError):
        load_render_config(tmp_path / "missing.yaml")


@pytest.mark.parametrize("text", [
    "version: 2", "version: true", "version: 1.0", "wat: 1", "[]", "typography: []",
    "typography:\n  font_size: 15", "typography:\n  font_size_pt: true",
    "typography:\n  font_size_pt: .nan", "typography:\n  font_size_pt: .inf",
    "typography:\n  font_size_pt: 0", "typography:\n  font_size_pt: '15'",
    "typography:\n  line_height_pt: 10", "layout:\n  max_name_line: 12.5",
    "layout:\n  person_gap_pt: 0", "pdf:\n  page_format: a3",
    "version: 1\nversion: 1", "typography:\n  font_size_pt: 15\n  font_size_pt: 16",
    "1: 1", "typography: &x {font_size_pt: 15}\nlayout: *x",
    "!!python/object/apply:os.system ['echo NEVER_EXECUTE']", "{broken",
    "typography:\n  font_size_pt: " + "9" * 400,
])
def test_invalid_configs_fail_closed(tmp_path, text):
    path = tmp_path / "bad.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(RenderConfigurationError, match="bad.yaml"):
        load_render_config(path)


def test_large_binary_and_empty_configs(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_bytes(b"#" * 65537)
    with pytest.raises(RenderConfigurationError, match="64 KiB"):
        load_render_config(path)
    path.write_bytes(b"\xff\xff")
    with pytest.raises(RenderConfigurationError):
        load_render_config(path)
    path.write_text("# Empty configuration\n")
    assert load_render_config(path) == RenderConfig()


@pytest.mark.parametrize("preset", ["default", "plus2", "plus3"])
def test_configured_render_keeps_geometry_determinism_and_vector_eps(tmp_path, workbook_path, preset):
    cfg = load_render_config(ROOT / f"config/render.{preset}.yaml")
    b = BuildGenealogyUseCase(render_config=cfg)
    g = b._assemble_sheet(ExcelGenealogyReader().read(workbook_path)[0])
    r = GraphvizGenealogyRenderer(cfg)
    first = r.render(g, tmp_path / "first.svg", title="Family")
    assert r.last_geometry["issues"] == ()
    second = r.render(g, tmp_path / "second.svg", title="Family")
    assert first.read_bytes() == second.read_bytes()
    assert f'font-size="{cfg.typography.font_size_pt:.2f}"' in first.read_text()
    eps = r.render(g, tmp_path / "family.eps", title="Family")
    content = eps.read_text(encoding="latin1")
    assert content.startswith("%!PS-Adobe")
    assert "cairo_image" not in content.split("%%EndPageSetup", 1)[1]
    assert "Parent A" not in content


def test_usecase_and_cli_page_override(tmp_path, workbook_path):
    from historical_bloodlines.cli import app
    path = tmp_path / "a4.yaml"
    path.write_text("pdf:\n  page_format: a4\n")
    builder = BuildGenealogyUseCase(render_config_path=path)
    first = tmp_path / "a4.pdf"
    builder.execute(workbook_path, first)
    assert float(PdfReader(first).pages[0].mediabox.width) == pytest.approx(841.8898)
    second = tmp_path / "a5.pdf"
    result = CliRunner().invoke(app, ["-i", str(workbook_path), "-o", str(second), "--render-config", str(path), "--paper", "a5"])
    assert result.exit_code == 0, result.output
    assert float(PdfReader(second).pages[0].mediabox.width) == pytest.approx(595.2756)
    bad = CliRunner().invoke(app, ["--render-config", str(tmp_path / "not-there.yaml")])
    assert bad.exit_code == 1
    assert "Build failed" in bad.output


def test_bot_reloads_per_job_but_snapshot_survives_mid_job_edit(monkeypatch, tmp_path):
    import historical_bloodlines.presentation.telegram.generation as module
    config_path = write_config(tmp_path / "render.yaml", 15.2)
    created = []

    class FakeBuilder:
        def __init__(self):
            self.render_config = load_render_config()
            self.seen = []
            created.append(self)

        def execute(self, input_path, output_path):
            self.seen.append(self.render_config.typography.font_size_pt)
            if output_path.suffix == ".eps":
                target = output_path.with_suffix("")
                target.mkdir()
                (target / "001.eps").write_text("test EPS")
                (target / "001.preview.png").write_bytes(b"preview")
                write_config(config_path, 16.2)  # edit while first job is running
            else:
                target = output_path
                target.write_bytes(b"test PDF")
            return BuildResult(target)

    monkeypatch.setattr(module, "BuildGenealogyUseCase", FakeBuilder)
    service = module.TelegramGenerationService()
    one = service.build(tmp_path / "unused.xlsx", tmp_path / "one")
    service.build(tmp_path / "unused.xlsx", tmp_path / "two")
    assert [b.seen for b in created] == [[15.2, 15.2], [16.2, 16.2]]
    with ZipFile(one.publisher_zip_path) as z:
        text = z.read("genealogy_publisher/render-settings.yaml").decode()
        assert "font_size_pt: 15.2" in text
