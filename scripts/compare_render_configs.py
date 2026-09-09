#!/usr/bin/env python3
"""Render presets from the SAME workbook and report actual fit-to-page font sizes.

Run with Poetry (or PYTHONPATH=src). The output directory must not already exist:
  poetry run python scripts/compare_render_configs.py book.xlsx --output-dir trial
Add --publisher for outlined EPS + PNG previews alongside each PDF.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path
import subprocess

from pypdf import PdfReader

from historical_bloodlines.application.services.build_genealogy import BuildGenealogyUseCase
from historical_bloodlines.config.render import load_render_config
from historical_bloodlines.infrastructure.excel import ExcelGenealogyReader
from historical_bloodlines.infrastructure.graph import GraphvizGenealogyRenderer
from historical_bloodlines.infrastructure.pdf import PageFormat, PdfBookComposer


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(source: Path, output: Path, configs: list[Path], publisher: bool) -> bool:
    # Validate all inputs before starting. Never mix a partial run with old output.
    settings = [load_render_config(path) for path in configs]
    sheets = ExcelGenealogyReader().read(source)
    if not sheets:
        raise ValueError("Workbook contains no genealogy rows")
    names = [path.stem for path in configs]
    if len(set(names)) != len(names):
        raise ValueError("Config filenames must have unique stems")
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "input_file": source.name, "input_sha256": sha256(source),
        "python": platform.python_version(),
        "graphviz": subprocess.run(["dot", "-V"], capture_output=True, text=True, check=True).stderr.strip(),
        "units": "Native points; fitted_body_pt = font_size_pt * uniform PDF scale",
        "variants": [],
    }
    success = True
    for path, config in zip(configs, settings):
        folder = output / path.stem
        folder.mkdir()
        (folder / "render-settings.yaml").write_text(config.to_yaml(), encoding="utf-8")
        builder = BuildGenealogyUseCase(render_config=config)
        pages, results = [], []
        page_format = PageFormat(config.pdf.page_format)
        paper = PdfBookComposer.PAGE_SPECS[page_format]
        for index, sheet in enumerate(sheets, 1):
            row = {"page": index, "title": sheet.display_title}
            try:
                genealogy = builder._assemble_sheet(sheet)
                renderer = GraphvizGenealogyRenderer(config)
                native = folder / f"{index:03d}.native.pdf"
                renderer.render(genealogy, native, title=sheet.display_title)
                box = PdfReader(native).pages[0].mediabox
                width, height = float(box.width), float(box.height)
                scale = min((paper.width - 2 * paper.margin) / width,
                            (paper.height - 2 * paper.margin) / height,
                            PdfBookComposer.MAX_UPSCALE)
                row.update(native_width_pt=width, native_height_pt=height, pdf_scale=scale,
                           native_body_pt=renderer.FONT_SIZE, fitted_body_pt=renderer.FONT_SIZE * scale,
                           route_issues=len(renderer.last_geometry["issues"]),
                           warnings=list(map(str, genealogy.warnings)))
                if publisher:
                    eps = folder / f"{index:03d}.eps"
                    renderer.render(genealogy, eps, title=sheet.display_title)
                    body = eps.read_text(encoding="latin1").split("%%EndPageSetup", 1)[1]
                    if "cairo_image" in body:
                        raise ValueError("Unexpected raster image in outlined EPS body")
                    renderer.render(genealogy, folder / f"{index:03d}.preview.png", title=sheet.display_title)
                pages.append(native)
            except Exception as exc:
                success = False
                row["error"] = str(exc)
            results.append(row)
            print(f"{path.stem} {index:02d}/{len(sheets)}: " +
                  (str(row["error"]) if "error" in row else f'{row["fitted_body_pt"]:.2f} pt on {page_format}'), flush=True)
        if len(pages) == len(sheets):
            PdfBookComposer().compose(pages, folder / "genealogy.pdf", page_format=page_format)
        report["variants"].append({"config": path.name, "config_sha256": sha256(path),
                                   "page_format": page_format.value, "pages": results})
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return success


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, action="append", help="Repeat to compare custom presets")
    parser.add_argument("--publisher", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    configs = args.config or [root / "config" / f"render.{name}.yaml" for name in ("default", "plus2", "plus3")]
    try:
        ok = compare(args.input, args.output_dir, configs, args.publisher)
    except Exception as exc:
        parser.exit(1, f"Comparison failed: {exc}\n")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
