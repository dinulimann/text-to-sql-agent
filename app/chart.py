"""Picks a simple chart for a result set, or none."""

import re

DATE_LIKE = re.compile(r"^\d{4}-\d{2}(-\d{2})?")
# Numeric columns that are labels, not measures
TIME_PART = re.compile(r"^(year|quarter|month|week|day)(_?(num|number|of_year))?$", re.I)
ID_LIKE = re.compile(r"(^id$|_id$)", re.I)


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def suggest_chart(columns: list[str], rows: list[list]) -> dict | None:
    """Label column(s) + one or more numeric measures -> bar chart, or a line
    chart over time. "x" lists the columns joined into the label, e.g.
    ["year", "month"] -> "2025-01". Anything else gets no chart."""
    if len(rows) < 2 or len(columns) < 2 or len(rows) > 60:
        return None

    numeric = [i for i in range(len(columns)) if all(_is_number(r[i]) or r[i] is None for r in rows)]
    time_parts = [i for i in numeric if TIME_PART.match(columns[i])]
    measures = [i for i in numeric if i not in time_parts and not ID_LIKE.search(columns[i])]
    text = [i for i in range(len(columns)) if i not in numeric]

    if time_parts:
        label_cols, is_time = time_parts, True
    elif len(text) == 1:
        values = [str(r[text[0]]) for r in rows]
        label_cols = text
        is_time = all(DATE_LIKE.match(v) for v in values) or bool(re.search(r"date|month|week|day|year", columns[text[0]], re.I))
    else:
        return None

    if not measures:
        return None
    return {
        "type": "line" if is_time else "bar",
        "x": [columns[i] for i in label_cols],
        "series": [columns[i] for i in measures[:3]],
    }
