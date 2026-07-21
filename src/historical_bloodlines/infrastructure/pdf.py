from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pypdf import PdfReader, PdfWriter, Transformation


class PageFormat(StrEnum):
    A4 = "a4"
    A5 = "a5"


@dataclass(frozen=True, slots=True)
class PageSpec:
    width: float
    height: float
    margin: float


class PdfBookComposer:
    """Normalize rendered genealogy pages and merge them into one PDF book."""

    PAGE_SPECS = {
        PageFormat.A4: PageSpec(width=841.8898, height=595.2756, margin=14.0),
        PageFormat.A5: PageSpec(width=595.2756, height=419.5276, margin=10.0),
    }
    MAX_UPSCALE = 1.22

    def compose(
        self,
        page_paths: list[Path],
        output_path: Path,
        *,
        page_format: PageFormat,
    ) -> Path:
        if not page_paths:
            raise ValueError("Cannot compose a PDF without pages")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        page_spec = self.PAGE_SPECS[page_format]
        writer = PdfWriter()
        try:
            for page_path in page_paths:
                source_page = PdfReader(str(page_path)).pages[0]
                source_width = float(source_page.mediabox.width)
                source_height = float(source_page.mediabox.height)

                available_width = page_spec.width - page_spec.margin * 2
                available_height = page_spec.height - page_spec.margin * 2
                scale = min(
                    available_width / source_width,
                    available_height / source_height,
                    self.MAX_UPSCALE,
                )
                translated_width = source_width * scale
                translated_height = source_height * scale
                translate_x = (page_spec.width - translated_width) / 2
                translate_y = (page_spec.height - translated_height) / 2

                target_page = writer.add_blank_page(
                    width=page_spec.width,
                    height=page_spec.height,
                )
                target_page.merge_transformed_page(
                    source_page,
                    Transformation()
                    .scale(scale, scale)
                    .translate(translate_x, translate_y),
                )

            with output_path.open("wb") as output_file:
                writer.write(output_file)
        finally:
            writer.close()

        return output_path
