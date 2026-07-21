from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator

from historical_bloodlines.application.dto import GenealogySheetDTO
from historical_bloodlines.application.services.assembler import GenealogyAssembler
from historical_bloodlines.application.services.parser import GenealogyRowParser
from historical_bloodlines.domain import Genealogy
from historical_bloodlines.infrastructure.excel import ExcelGenealogyReader
from historical_bloodlines.infrastructure.graph import (
    GraphvizGenealogyRenderer,
    NetworkXGenealogyValidator,
)
from historical_bloodlines.infrastructure.pdf import (
    PageFormat,
    PageSpec,
    PdfBookComposer,
)


@dataclass(frozen=True, slots=True)
class BuildResult:
    output_path: Path
    warnings: tuple[str, ...] = ()

    def __iter__(self) -> Iterator[object]:
        """Preserve tuple-unpacking compatibility with pre-refactor callers."""
        yield self.output_path
        yield self.warnings


class BuildGenealogyUseCase:
    """Orchestrate workbook reading, domain assembly, validation and rendering."""

    DEFAULT_PAGE_FORMAT = PageFormat.A5
    # Compatibility for callers that used the previous class-level mapping.
    PAGE_SPECS: dict[PageFormat, PageSpec] = PdfBookComposer.PAGE_SPECS

    def __init__(
        self,
        reader: ExcelGenealogyReader | None = None,
        parser: GenealogyRowParser | None = None,
        assembler: GenealogyAssembler | None = None,
        validator: NetworkXGenealogyValidator | None = None,
        renderer: GraphvizGenealogyRenderer | None = None,
        pdf_composer: PdfBookComposer | None = None,
    ) -> None:
        self._reader = reader or ExcelGenealogyReader()
        self._parser = parser or GenealogyRowParser()
        self._assembler = assembler or GenealogyAssembler()
        self._validator = validator or NetworkXGenealogyValidator()
        self._renderer = renderer or GraphvizGenealogyRenderer()
        self._pdf_composer = pdf_composer or PdfBookComposer()

    def execute(
        self,
        input_path: Path,
        output_path: Path,
        *,
        page_format: PageFormat | str = DEFAULT_PAGE_FORMAT,
    ) -> BuildResult:
        sheets = self._reader.read(input_path)
        if not sheets:
            raise ValueError("Workbook contains no genealogy rows")

        output_format = output_path.suffix.casefold()
        if output_format not in {".pdf", ".svg", ".png"}:
            raise ValueError("Output format must be .pdf, .svg or .png")

        selected_page_format = PageFormat(page_format)
        if output_format == ".pdf":
            return self._build_multi_page_pdf(
                sheets,
                output_path,
                page_format=selected_page_format,
            )
        return self._build_separate_images(sheets, output_path)

    def _build_multi_page_pdf(
        self,
        sheets: tuple[GenealogySheetDTO, ...],
        output_path: Path,
        *,
        page_format: PageFormat,
    ) -> BuildResult:
        warnings: list[str] = []

        with TemporaryDirectory(prefix="bloodlines_") as temporary_directory:
            temporary_path = Path(temporary_directory)
            page_paths: list[Path] = []

            for index, sheet in enumerate(sheets, start=1):
                genealogy = self._assemble_sheet(sheet)
                warnings.extend(str(item) for item in genealogy.warnings)
                page_path = (
                    temporary_path
                    / f"{index:03d}_{self._slug(sheet.display_title)}.pdf"
                )
                page_paths.append(
                    self._renderer.render(
                        genealogy,
                        page_path,
                        title=sheet.display_title,
                    )
                )

            self._pdf_composer.compose(
                page_paths,
                output_path,
                page_format=page_format,
            )

        return BuildResult(output_path=output_path, warnings=tuple(warnings))

    def _build_separate_images(
        self,
        sheets: tuple[GenealogySheetDTO, ...],
        output_path: Path,
    ) -> BuildResult:
        warnings: list[str] = []
        output_directory = output_path.parent / output_path.stem
        output_directory.mkdir(parents=True, exist_ok=True)

        for index, sheet in enumerate(sheets, start=1):
            genealogy = self._assemble_sheet(sheet)
            warnings.extend(str(item) for item in genealogy.warnings)
            page_path = output_directory / (
                f"{index:03d}_{self._slug(sheet.display_title)}"
                f"{output_path.suffix.casefold()}"
            )
            self._renderer.render(
                genealogy,
                page_path,
                title=sheet.display_title,
            )

        return BuildResult(output_path=output_directory, warnings=tuple(warnings))

    def _assemble_sheet(self, sheet: GenealogySheetDTO) -> Genealogy:
        parsed_rows = tuple(self._parser.parse(row) for row in sheet.rows)
        genealogy = self._assembler.assemble(parsed_rows)
        self._validator.validate(genealogy)
        return genealogy

    @staticmethod
    def _slug(value: str) -> str:
        normalized = re.sub(r"[^\w.-]+", "_", value.strip(), flags=re.UNICODE)
        return normalized.strip("_") or "genealogy"


__all__ = [
    "BuildGenealogyUseCase",
    "BuildResult",
    "PageFormat",
    "PageSpec",
]
