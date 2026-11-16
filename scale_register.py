"""Stage 37 (Fable review §4 item 2): the scales register.

Several scales are defined in one place and then scored, and their
reliability checked, in one action each. This module holds the logic and
has no Flet import; ``workspace_scales`` is the card of the Data page.

A definition says, for one scale:

* ``name``: the new score column;
* ``items``: its item columns (chosen in the variable panel);
* ``reverse``: the items the researcher confirmed, one by one, as
  reverse-keyed. Nothing is inferred: a possibly reversed item that item
  diagnostics flag is never marked here by the program;
* ``low`` / ``high``: the response range the reversal uses (``low + high −
  x``), typed by the researcher; needed only when an item is reversed;
* ``method``: ``"mean"`` or ``"sum"``, and ``min_answered``: how many items a
  case must have answered. Neither has a default: both are chosen;
* ``confirms``: the scale's confirmations, each with what it was given for
  (Stage 36.8, K1): ``one_construct`` (the items are meant to measure one
  construct, the design confirmation of item diagnostics) and, when the
  values of an item look like a total, ``items_not_totals`` (D5). A change
  of the items, the reversed items or the response range clears them.

Scoring uses the very functions of Data → Prepare (``reverse_item`` for a
reversed item, into ``<item>_reverse``, then ``score_scale``), so a scale
scored here and the same scale scored there give the same column and the
same history records. Reliability is ``item_diagnostics`` on the items as
scored (a reversed item by its reversed column), the method the Analyze
page runs for "Check the quality of a scale".

The register is kept in the project's activity log (``Project
.save_scale_register``): the latest entry is the current register, the
earlier ones its history. Project format 6 is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import math
from typing import Any

import pandas as pd

REGISTER_FORMAT = 1
METHODS = ("mean", "sum")
REVERSE_SUFFIX = "_reverse"
CONFIRMATIONS = ("one_construct", "items_not_totals")


def reversed_name(item: str) -> str:
    """The column a reversed item is written to (Data → Prepare's name)."""
    return f"{item}{REVERSE_SUFFIX}"


@dataclass(frozen=True)
class ScaleDefinition:
    name: str
    items: tuple[str, ...] = ()
    reverse: tuple[str, ...] = ()
    low: float | None = None
    high: float | None = None
    method: str | None = None
    min_answered: int | None = None
    confirms: dict = field(default_factory=dict)       # {key: scope}

    # ------------------------------------------------------------ the items
    def scored_items(self) -> list[str]:
        """The columns the score and its reliability use, in item order."""
        reverse = set(self.reverse)
        return [reversed_name(item) if item in reverse else item for item in self.items]

    def scope(self, key: str) -> dict:
        """What a confirmation of this scale is given for (K1): its items, its
        reversed items and their response range."""
        return {"kind": "design", "confirmation": key, "items": sorted(self.items),
                "reverse": sorted(self.reverse),
                "range": [self.low, self.high] if self.reverse else None}

    def holds(self, key: str) -> bool:
        return self.confirms.get(key) == self.scope(key)

    def with_items(self, items) -> "ScaleDefinition":
        """New items: reversed items no longer among them are dropped, and the
        confirmations no longer hold (they were given for other items)."""
        items = tuple(dict.fromkeys(str(name) for name in items))
        kept = tuple(name for name in self.reverse if name in items)
        return replace(self, items=items, reverse=kept, confirms=_held(self, items, kept))

    def with_reverse(self, item: str, value: bool) -> "ScaleDefinition":
        """Mark (``value``) or unmark one item as reverse-keyed: the explicit
        confirmation of that item. Other confirmations are cleared."""
        if item not in self.items:
            raise ValueError(f"{item} is not an item of {self.name}.")
        reverse = [name for name in self.reverse if name != item]
        if value:
            reverse.append(item)
        reverse = tuple(name for name in self.items if name in set(reverse))
        return replace(self, reverse=reverse, confirms={})

    def with_range(self, low, high) -> "ScaleDefinition":
        changed = (low, high) != (self.low, self.high)
        return replace(self, low=low, high=high, confirms={} if changed and self.reverse
                       else dict(self.confirms))

    def confirm(self, key: str, value: bool) -> "ScaleDefinition":
        if key not in CONFIRMATIONS:
            raise ValueError(f"Unknown confirmation: {key}")
        confirms = dict(self.confirms)
        if value:
            confirms[key] = self.scope(key)
        else:
            confirms.pop(key, None)
        return replace(self, confirms=confirms)

    # ------------------------------------------------------------ storage
    def to_json(self) -> dict:
        return {"name": self.name, "items": list(self.items), "reverse": list(self.reverse),
                "low": self.low, "high": self.high, "method": self.method,
                "min_answered": self.min_answered,
                "confirms": {key: value for key, value in self.confirms.items()}}

    @classmethod
    def from_json(cls, data: Any) -> "ScaleDefinition | None":
        """A stored definition, or None when it is not one this version reads."""
        if not isinstance(data, dict) or not isinstance(data.get("name"), str):
            return None
        items = tuple(str(n) for n in data.get("items") or [] if isinstance(n, str))
        reverse = tuple(str(n) for n in data.get("reverse") or []
                        if isinstance(n, str) and n in items)
        method = data.get("method") if data.get("method") in METHODS else None
        minimum = data.get("min_answered")
        minimum = minimum if isinstance(minimum, int) and not isinstance(minimum, bool) else None
        confirms = {key: value for key, value in (data.get("confirms") or {}).items()
                    if key in CONFIRMATIONS and isinstance(value, dict)}
        return cls(data["name"], items, reverse, _number(data.get("low")),
                   _number(data.get("high")), method, minimum, confirms)


def _held(definition: ScaleDefinition, items, reverse) -> dict:
    """The confirmations that still hold after the items changed (none, unless
    the items and reversed items are the same as before)."""
    if tuple(items) == definition.items and tuple(reverse) == definition.reverse:
        return dict(definition.confirms)
    return {}


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def parse_number(text) -> float | None:
    """A typed number (a decimal comma is read as a point), or None."""
    try:
        value = float(str(text).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def parse_count(text) -> int | None:
    text = str(text or "").strip()
    return int(text) if text.isdigit() else None


# ----------------------------------------------------------------- readiness
def scoring_problems(definition: ScaleDefinition, columns) -> list[tuple[str, dict]]:
    """``(text key, values)`` for what keeps a scale from being scored."""
    from data_preparation import COLUMN_NAME

    problems: list[tuple[str, dict]] = []
    columns = set(map(str, columns))
    if not COLUMN_NAME.fullmatch(definition.name or ""):
        problems.append(("scales.need.name", {}))
    elif definition.name in columns:
        problems.append(("scales.need.new_name", {"name": definition.name}))
    k = len(definition.items)
    if not 2 <= k <= 30:
        problems.append(("scales.need.items", {"count": k}))
    missing = [name for name in definition.items if name not in columns]
    if missing:
        problems.append(("scales.need.columns", {"names": ", ".join(missing)}))
    if definition.reverse:
        if definition.low is None or definition.high is None \
                or definition.low >= definition.high:
            problems.append(("scales.need.range", {}))
    if definition.method not in METHODS:
        problems.append(("scales.need.method", {}))
    if definition.min_answered is None:
        problems.append(("scales.need.min", {}))
    elif not 1 <= definition.min_answered <= max(k, 1):
        problems.append(("scales.need.min_range", {"count": k}))
    elif definition.method == "sum" and definition.min_answered != k:
        problems.append(("scales.need.sum_all", {"count": k}))
    return problems


def totals_among(df: pd.DataFrame, definition: ScaleDefinition) -> list[str]:
    """Items whose values look like totals, not item answers (D5)."""
    from item_diagnostics import item_response_problems

    names = [name for name in definition.items if name in df.columns]
    return [p.name for p in item_response_problems(df, names) if p.looks_like_total]


def reliability_problems(definition: ScaleDefinition, df: pd.DataFrame,
                         session=None) -> list[tuple[str, dict]]:
    """What keeps the reliability of a scale from being checked."""
    problems: list[tuple[str, dict]] = []
    if not 3 <= len(definition.items) <= 40:
        problems.append(("scales.need.items_reliability", {"count": len(definition.items)}))
    columns = set(map(str, df.columns))
    absent = [name for name in definition.scored_items() if name not in columns]
    if absent:
        problems.append(("scales.need.score_first", {"names": ", ".join(absent)}))
    if not definition.holds("one_construct"):
        problems.append(("scales.need.one_construct", {}))
    if totals_among(df, definition) and not definition.holds("items_not_totals"):
        problems.append(("scales.need.not_totals", {}))
    if session is not None:
        for name in definition.scored_items():
            info = session.variables.get(name)
            if info is not None and info.confirmed == "unknown":
                problems.append(("design.confirm_level", {"name": name}))
            elif info is not None and info.confirmed not in ("ordinal", "scale"):
                problems.append(("scales.need.level", {"name": name}))
    return problems


# ------------------------------------------------------------------- scoring
@dataclass
class Scored:
    frame: pd.DataFrame
    steps: list[dict]                      # Data → Prepare's steps, in order
    scored: list[str]                      # the scales scored
    messages: list[str]


def score_all(df: pd.DataFrame, definitions) -> Scored:
    """Score every definition (all must be ready: :func:`scoring_problems`),
    with Data → Prepare's own functions. A reversed column that is already
    there (an item two scales share) is used when it holds exactly
    ``low + high − item``; otherwise scoring stops with an error."""
    import numpy as np

    from data_preparation import reverse_item, score_scale

    frame = df.copy(deep=True)
    steps: list[dict] = []
    done: list[str] = []
    messages: list[str] = []
    for definition in definitions:
        problems = scoring_problems(definition, frame.columns)
        if problems:
            raise ValueError(f"{definition.name}: {problems[0][0]}")
        for item in definition.reverse:
            target = reversed_name(item)
            if target in frame.columns:
                values = pd.to_numeric(frame[item], errors="coerce")
                expected = definition.low + definition.high - values
                present = pd.to_numeric(frame[target], errors="coerce")
                same = np.array_equal(expected.isna(), present.isna()) and bool(
                    (expected.dropna() == present[expected.notna()]).all())
                if not same:
                    raise ValueError(f"{target} exists and is not {definition.low:g} + "
                                     f"{definition.high:g} − {item}.")
                continue
            result = reverse_item(frame, item, target, definition.low, definition.high)
            frame = result.frame
            steps.append(result.step)
        result = score_scale(frame, definition.scored_items(), definition.name,
                             definition.method, int(definition.min_answered))
        frame = result.frame
        step = dict(result.step)
        step["scale_register"] = {"items": list(definition.items),
                                  "reverse": list(definition.reverse),
                                  "range": [definition.low, definition.high]
                                  if definition.reverse else None}
        steps.append(step)
        done.append(definition.name)
        messages.append(result.message)
    return Scored(frame, steps, done, messages)


# ------------------------------------------------------------------- storage
def register_json(definitions) -> dict:
    return {"format": REGISTER_FORMAT, "scales": [d.to_json() for d in definitions]}


def register_from_json(data: Any) -> list[ScaleDefinition]:
    if not isinstance(data, dict) or not isinstance(data.get("scales"), list):
        return []
    found = [ScaleDefinition.from_json(item) for item in data["scales"]]
    return [d for d in found if d is not None]
