from __future__ import annotations

import html
import re
import textwrap
from dataclasses import dataclass

from historical_bloodlines.domain import Person, ReignPeriod
from historical_bloodlines.infrastructure.graph.models import PersonBox


_TRAILING_COMMA_RE = re.compile(r",+\s*$")
_NON_TITLE_WORD_RE = re.compile(
    r"(?iu)\b(?:с|до|по|в|после|между|ок|около|ум|умер|умерла|р|род|"
    r"родился|родилась|г|гг|н|э|правил|правила|правление)\b\.?"
)
_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)


@dataclass(frozen=True, slots=True)
class PersonLabelFormatter:
    font_size: float
    line_height: float
    text_padding_x: float
    text_padding_y: float
    max_text_line: int
    max_name_line: int | None = None

    def measure(self, person: Person) -> PersonBox:
        name_lines = self._name_lines(person)
        lines = [*name_lines, *self._title_and_reign_lines(person)]

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


    def _name_lines(self, person: Person) -> tuple[str, ...]:
        """Format terminal punctuation independently from the Excel value.

        Older workbooks contain commas typed directly into the ``Имя`` column.
        They are removed first, then restored only when the ``Титул`` column
        contains an actual textual title. A chronology-only value such as
        ``862-879`` or ``ум. 1376`` therefore never produces a comma.
        """

        clean_name = _TRAILING_COMMA_RE.sub("", person.name).rstrip()
        if self._has_textual_title(person):
            clean_name = f"{clean_name},"
        return self.wrap_name(clean_name)

    @staticmethod
    def _has_textual_title(person: Person) -> bool:
        for title in person.titles:
            without_dates = re.sub(r"-?\d{3,4}", " ", title)
            without_date_punctuation = re.sub(
                r"[()\[\]{},.;:–—-]+",
                " ",
                without_dates,
            )
            meaningful_text = _NON_TITLE_WORD_RE.sub(" ", without_date_punctuation)
            if _LETTER_RE.search(meaningful_text):
                return True
        return False

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

    def _title_and_reign_lines(self, person: Person) -> tuple[str, ...]:
        if not person.reign_periods:
            return tuple(
                line
                for title in person.titles
                for line in self.wrap(title)
            )

        entries: list[tuple[str, ReignPeriod | None]] = []
        item_count = max(len(person.titles), len(person.reign_periods))
        for index in range(item_count):
            title = person.titles[index] if index < len(person.titles) else ""
            period = (
                person.reign_periods[index]
                if index < len(person.reign_periods)
                else None
            )
            entries.append((title, period))

        # A complete reign range is the reader's primary chronological anchor.
        # It must always appear first, before any later qualification such as
        # ``император с 962``. Python's sort is stable, so the source order is
        # preserved inside each group.
        entries.sort(
            key=lambda entry: (
                0
                if entry[1] is not None and entry[1].end_year is not None
                else 1
                if entry[1] is not None
                else 2
            )
        )

        items = self._format_reign_items(entries)
        return self.wrap(f"({', '.join(items)})")

    @staticmethod
    def _format_reign_items(
        entries: list[tuple[str, ReignPeriod | None]],
    ) -> list[str]:
        items: list[str] = []
        complete_entries = [
            (title, period)
            for title, period in entries
            if period is not None and period.end_year is not None
        ]
        has_qualifications = any(
            period is None or period.end_year is None
            for _, period in entries
        )
        primary_complete_period = complete_entries[0][1] if complete_entries and has_qualifications else None

        for title, period in entries:
            if period is None:
                if title:
                    items.append(title)
                continue

            if period.end_year is not None:
                dates = f"{period.start_year}-{period.end_year}"
                if primary_complete_period is period:
                    items.append(dates)
                else:
                    items.append(" ".join(part for part in (title, dates) if part))
                continue

            qualification = f"с {period.start_year}"
            items.append(" ".join(part for part in (title, qualification) if part))

        return items

    def wrap_name(self, value: str) -> tuple[str, ...]:
        """Wrap names a little earlier than titles and dates.

        Dense generations are usually widened by long personal names rather
        than by titles. A separate name width makes family components narrower
        while preserving readable title lines. A short trailing parenthetical
        such as ``(ум. 1483)`` is kept with the preceding surname whenever that
        produces only a small controlled overflow.
        """

        width = self.max_name_line or self.max_text_line
        normalized = " ".join(value.split())
        if not normalized:
            return ()

        suffix = ""
        base = normalized
        if normalized.endswith(")") and " (" in normalized:
            candidate_base, candidate_suffix = normalized.rsplit(" (", maxsplit=1)
            candidate_suffix = f"({candidate_suffix}"
            if 3 <= len(candidate_suffix) <= width:
                base = candidate_base
                suffix = candidate_suffix

        lines = list(self._wrap_to_width(base, width))
        if suffix:
            combined = f"{lines[-1]} {suffix}"
            if len(combined) <= width + 5:
                lines[-1] = combined
            else:
                lines.append(suffix)
        return tuple(lines)

    def wrap(self, value: str) -> tuple[str, ...]:
        return self._wrap_to_width(value, self.max_text_line)

    @staticmethod
    def _wrap_to_width(value: str, width: int) -> tuple[str, ...]:
        value = " ".join(value.split())
        if not value:
            return ()
        wrapped = textwrap.wrap(
            value,
            width=width,
            break_long_words=False,
            break_on_hyphens=False,
        )
        return tuple(wrapped or [value])
