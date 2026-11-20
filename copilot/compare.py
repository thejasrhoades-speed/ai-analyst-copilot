"""Decide whether a candidate result matches the gold result.

Tolerant to column names, column order, and extra columns (as long as every gold column
appears), and numbers are compared at the precision the gold answer uses.
Row order matters only when `ordered` is True (top-N questions).
"""
from __future__ import annotations

from collections import Counter


def _decimals(v) -> int:
    if isinstance(v, float):
        s = repr(v)
        return len(s.split(".")[1]) if "." in s and "e" not in s else 0
    return 0


def _norm(v, p: int):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        r = round(float(v), p)
        return int(r) if r == int(r) else r
    return str(v).strip().lower()


def results_match(gold_rows, cand_rows, ordered: bool = False) -> bool:
    if len(gold_rows) != len(cand_rows):
        return False
    if not gold_rows:
        return True
    gcols = list(zip(*gold_rows))
    ccols = list(zip(*cand_rows))
    used, mapping = set(), []
    for g in gcols:
        p = max((_decimals(v) for v in g), default=0)
        gn = [_norm(v, p) for v in g]
        target = Counter(gn)
        found = None
        for i, c in enumerate(ccols):
            if i in used:
                continue
            if Counter(_norm(v, p) for v in c) == target:
                found = (i, p)
                break
        if found is None:
            return False
        used.add(found[0])
        mapping.append(found)
    g_rows = [tuple(_norm(v, max((_decimals(x) for x in gcols[j]), default=0)) for j, v in enumerate(r)) for r in gold_rows]
    c_rows = [tuple(_norm(r[i], p) for i, p in mapping) for r in cand_rows]
    return g_rows == c_rows if ordered else Counter(g_rows) == Counter(c_rows)
