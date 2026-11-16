"""Stage 37 (Fable review §4 item 5): Tables 1 and 2 of a thesis.

* :func:`describe_many` — descriptive statistics of many variables in one
  table (one row per variable): N, missing, M, SD, median, quartiles,
  minimum and maximum. Each row is :func:`stat_results.describe_quantitative`
  of that variable, so the values are pandas' own (sample SD with n − 1,
  quartiles by linear interpolation, Hyndman–Fan type 7).
* :func:`correlation_table` — the correlations of every pair of 2–16
  variables, each with its N (pairwise-complete), its 95% CI and its p-value,
  with every p of the table adjusted together as one family (Holm,
  Benjamini–Hochberg or Bonferroni; the raw p is kept). Each pair is the
  validated pair engine of the correlation batch
  (``batch_correlation._pair``): Pearson r with SciPy's t-test p and the
  Fisher z interval; Spearman ρ with SciPy's t-approximation p (as SPSS
  reports it) and a percentile bootstrap interval with a fixed seed
  (Fisher z is not applied to ρ).

Both return a :class:`stat_results.StructuredResult` (stored and restored
as every structured result) and need no Flet.
"""

from __future__ import annotations

from itertools import combinations

import pandas as pd

from stat_results import Quantity, StructuredResult, Table, _provenance, describe_quantitative
from variable_rules import looks_like_identifier

MAX_DESCRIBED = 60
MAX_CORRELATED = 16
CI_LEVEL = 0.95


def _check(df: pd.DataFrame, names, low: int, high: int) -> list[str]:
    names = [str(n) for n in names]
    if not low <= len(names) <= high:
        raise ValueError(f"Choose {low}–{high} variables.")
    if len(set(names)) != len(names):
        raise ValueError("Choose each variable only once.")
    for name in names:
        if name not in df.columns:
            raise ValueError(f"Unknown variable: {name}")
        if looks_like_identifier(name):
            raise ValueError(f"{name} is an identifier, not a research measurement.")
        values = df[name]
        if values.notna().any() and pd.to_numeric(values, errors="coerce").isna().all():
            raise ValueError(f"{name} holds text, not numbers (an identifier?).")
    return names


def _cell(quantity: Quantity | None, digits: int = 2) -> str:
    return quantity.text(digits) if quantity is not None else "—"


DESCRIPTIVE_COLUMNS = ("Variable", "N", "Missing", "M", "SD", "Mdn", "Q1", "Q3", "Min", "Max")
DESCRIPTIVE_KEYS = ("n", "missing", "mean", "sd", "median", "q1", "q3", "min", "max")


def describe_many(df: pd.DataFrame, names) -> StructuredResult:
    """One row of descriptive statistics per variable (2–60 variables)."""
    names = _check(df, names, 2, MAX_DESCRIBED)
    rows, quantities, warnings = [], [], []
    for name in names:
        single = describe_quantitative(df[name], name)
        cells = [name]
        for key in DESCRIPTIVE_KEYS:
            quantity = single.quantity(key)
            cells.append(_cell(quantity))
            if quantity is not None:
                quantities.append(Quantity(f"{name}:{key}", f"{name}: {quantity.label}",
                                           quantity.value, quantity.status, quantity.note,
                                           integer=quantity.integer))
        rows.append(tuple(cells))
        warnings += [f"{name}: {w}" for w in single.warnings]
    table = Table("Descriptive statistics", DESCRIPTIVE_COLUMNS, tuple(rows))
    return StructuredResult(
        "descriptives_many", f"Descriptive statistics of {len(names)} variables",
        {"n_total": int(len(df))}, {"variables": names}, tuple(quantities),
        warnings=tuple(warnings + [
            "N and missing are counted per variable (each row uses its own complete values).",
            "SD is the sample SD (n − 1); quartiles use linear interpolation "
            "(Hyndman–Fan type 7)."]),
        tables=(table,), provenance=_provenance())


CORRELATION_COLUMNS = ("Variable 1", "Variable 2", "N", "Coefficient", "95% CI", "p",
                       "p (adjusted)")


def correlation_table(df: pd.DataFrame, names, *, method: str = "pearson",
                      adjust: str = "holm", resamples: int = 2000, seed: int = 37,
                      pearson_confirmed: bool = False) -> StructuredResult:
    """Every pair of ``names`` with N, coefficient, 95% CI, raw and adjusted p."""
    from batch_correlation import MIN_PAIRS, _pair
    from multiple_comparisons import PROCEDURES, adjust as adjust_family

    if method not in ("pearson", "spearman"):
        raise ValueError("Choose Pearson or Spearman.")
    if adjust not in PROCEDURES:
        raise ValueError(f"Unknown adjustment: {adjust}")
    if method == "pearson" and not pearson_confirmed:
        raise ValueError("Confirm the Pearson linearity and outlier review first.")
    names = _check(df, names, 2, MAX_CORRELATED)
    pairs = [_pair(df, a, b, method, CI_LEVEL, resamples, seed, "none", spearman_p="asymptotic")
             for a, b in combinations(names, 2)]
    family = adjust_family([row.p_raw if row.status == "ok" else None for row in pairs], adjust)
    symbol = "r" if method == "pearson" else "ρ"
    rows, quantities = [], []
    for row, p_adjusted in zip(pairs, family.adjusted):
        key = f"{row.x}~{row.y}"
        if row.status != "ok":
            rows.append((row.x, row.y, str(row.n), "—", "—", "—", "—"))
            quantities.append(Quantity.missing(key, f"{symbol}({row.x}, {row.y})", "failed",
                                               row.note))
            continue
        ci = (f"[{row.ci_low:.2f}, {row.ci_high:.2f}]"
              if row.ci_low is not None and row.ci_high is not None else "—")
        rows.append((row.x, row.y, str(row.n), f"{row.estimate:.2f}", ci, _p(row.p_raw),
                     _p(p_adjusted)))
        quantities.append(Quantity(key, f"{symbol}({row.x}, {row.y})", row.estimate,
                                   ci_low=row.ci_low, ci_high=row.ci_high, ci_level=CI_LEVEL,
                                   ci_method=row.ci_method, p=p_adjusted,
                                   p_method=f"{row.p_method}; {family.description}"))
    first = next((row for row in pairs if row.status == "ok"), None)
    warnings = [
        f"Every p of the table is one family: {family.description}; {family.family_size} "
        "tests. Raw p-values are reported next to the adjusted ones.",
        "N is counted per pair (pairwise-complete cases).",
        "Correlation does not establish causation; p at or above α is not evidence of no "
        "association.",
    ]
    if first is not None:
        warnings.append(f"p: {first.p_method}. CI: {first.ci_method}.")
    if any(row.status != "ok" for row in pairs):
        warnings.append(f"Pairs with fewer than {MIN_PAIRS} complete cases or without "
                        "variation are not calculated and not part of the family.")
    label = "Pearson’s r" if method == "pearson" else "Spearman’s ρ"
    table = Table(f"Correlations ({label}) with 95% CI and adjusted p", CORRELATION_COLUMNS,
                  tuple(rows))
    return StructuredResult(
        "correlation_table", f"Correlation matrix of {len(names)} variables ({label})",
        {"n_total": int(len(df))},
        {"variables": names, "method": method, "adjust": adjust, "seed": seed,
         "resamples": resamples}, tuple(quantities), warnings=tuple(warnings),
        tables=(table,), provenance=_provenance())


def _p(value) -> str:
    if value is None:
        return "—"
    return "< .001" if value < 0.001 else f"{value:.3f}".replace("0.", ".", 1)
