from __future__ import annotations

import html
import textwrap
from dataclasses import dataclass

from historical_bloodlines.domain import Person
from historical_bloodlines.infrastructure.graph.models import PersonBox


@dataclass(frozen=True, slots=True)
class PersonLabelFormatter:
    font_size: float
    line_height: float
    text_padding_x: float
    text_padding_y: float
    max_text_line: int

    def measure(self, person: Person) -> PersonBox:
        name_lines = self.wrap(person.name)
        lines: list[str] = list(name_lines)
        for title in person.titles:
            lines.extend(self.wrap(title))
        if person.reign_periods:
            periods = ", ".join(
                f"{period.start_year}-{period.end_year}"
                for period in person.reign_periods
            )
            lines.extend(self.wrap(f"({periods})"))

        max_chars = max((len(line) for line in lines), default=1)
        # Conservative Sans estimate. It intentionally slightly overestimates
        # Cyrillic labels so connector lines never enter the text.
        width = max(
            58.0,
            max_chars * self.font_size * 0.57 + self.text_padding_x * 2,
        )
        height = max(
            18.0,
            len(lines) * self.line_height + self.text_padding_y * 2,
        )
        return PersonBox(
            person_id=person.id,
            lines=tuple(lines),
            name_line_count=len(name_lines),
            width=width,
            height=height,
        )

    def html_label(self, person: Person) -> str:
        box = self.measure(person)
        output_lines: list[str] = []
        for index, line in enumerate(box.lines):
            escaped = html.escape(line)
            if person.is_placeholder:
                escaped = f"<I>{escaped}</I>"
            elif index < box.name_line_count:
                escaped = f"<B>{escaped}</B>"
            output_lines.append(escaped)
        return f"<{'<BR/>'.join(output_lines)}>"

    def wrap(self, value: str) -> tuple[str, ...]:
        value = " ".join(value.split())
        if not value:
            return ()
        wrapped = textwrap.wrap(
            value,
            width=self.max_text_line,
            break_long_words=False,
            break_on_hyphens=False,
        )
        return tuple(wrapped or [value])
