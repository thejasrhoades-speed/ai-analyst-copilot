"""The copilot: question -> SQL -> safe execution -> (optional) explanation."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from .db import notes_text, schema_text
from .guardrails import UnsafeQuery, run_readonly
from .llm import Provider

SQL_PROMPT = """You are a careful data analyst who writes SQLite queries.

DATABASE SCHEMA
{schema}

BUSINESS NOTES
{notes}

RULES
- Write ONE read-only SQLite SELECT query (CTEs allowed). No other statements.
- Use only tables and columns that exist in the schema above.
- Follow the business notes for definitions (revenue, delivery time, English category names, etc.).
- Return only the columns the question asks for, with clear column names.
- If the question asks for a top/bottom N, use ORDER BY and LIMIT.
- Output ONLY the SQL inside a ```sql code block, with no explanation.

QUESTION: {question}
"""

FIX_PROMPT = """{base}

Your previous query:
```sql
{sql}
```
failed with this error:
{error}

Write a corrected query. Output ONLY the SQL inside a ```sql code block."""

EXPLAIN_PROMPT = """A user asked: {question}

The SQL run was:
{sql}

The result (first rows):
{table}

In 2-4 plain-English sentences, answer the question using only these numbers. Do not invent
figures that are not in the result. If the result is empty, say so."""


@dataclass
class Result:
    question: str
    sql: str = ""
    df: pd.DataFrame | None = None
    explanation: str = ""
    attempts: int = 0
    error: str = ""
    truncated: bool = False
    history: list = field(default_factory=list)  # [(sql, error_or_None), ...]

    @property
    def ok(self) -> bool:
        return not self.error and self.df is not None


def extract_sql(text: str) -> str:
    m = re.search(r"```(?:sql|sqlite)?\s*(.*?)```", text, flags=re.S | re.I)
    return (m.group(1) if m else text).strip()


class Copilot:
    def __init__(self, db_path: str, provider: Provider, max_retries: int = 2):
        self.db_path = db_path
        self.provider = provider
        self.max_retries = max_retries
        self._schema = schema_text(db_path)
        self._notes = notes_text(db_path) or "(none)"

    def ask(self, question: str, explain: bool = False) -> Result:
        res = Result(question=question)
        base = SQL_PROMPT.format(schema=self._schema, notes=self._notes, question=question)
        prompt = base
        for attempt in range(1, self.max_retries + 2):
            res.attempts = attempt
            sql = extract_sql(self.provider.generate(prompt))
            res.sql = sql
            try:
                cols, rows, trunc = run_readonly(self.db_path, sql)
                res.df = pd.DataFrame(rows, columns=cols)
                res.truncated = trunc
                res.error = ""
                res.history.append((sql, None))
                break
            except (UnsafeQuery, TimeoutError, Exception) as e:  # noqa: BLE001
                res.error = f"{type(e).__name__}: {e}"
                res.history.append((sql, res.error))
                if isinstance(e, UnsafeQuery):
                    break  # never "retry around" a safety block
                prompt = FIX_PROMPT.format(base=base, sql=sql, error=res.error)
        if res.ok and explain:
            table = res.df.head(20).to_string(index=False)
            res.explanation = self.provider.generate(
                EXPLAIN_PROMPT.format(question=question, sql=res.sql, table=table)).strip()
        return res
