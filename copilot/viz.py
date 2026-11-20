"""Pick a sensible chart for a result table (no LLM needed)."""
from __future__ import annotations

import re

import pandas as pd


def suggest_chart(df: pd.DataFrame):
    """Return (kind, x, y) or None. kind is 'line' or 'bar'."""
    if df is None or df.empty or df.shape[1] < 2 or len(df) < 2 or len(df) > 60:
        return None
    x = df.columns[0]
    nums = [c for c in df.columns[1:] if pd.api.types.is_numeric_dtype(df[c])]
    if not nums or pd.api.types.is_numeric_dtype(df[x]) and not re.search(r"year|month|day|date", str(x), re.I):
        return None
    y = nums[0]
    is_time = bool(df[x].astype(str).str.match(r"^\d{4}(-\d{2})?$").all())
    return ("line" if is_time else "bar", x, y)
