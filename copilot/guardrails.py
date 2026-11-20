"""Safety layer: only read-only SELECT queries may run, with row and time limits."""
from __future__ import annotations

import re
import sqlite3
import time

MAX_ROWS = 1000
TIMEOUT_SECONDS = 10

_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,
}


class UnsafeQuery(Exception):
    """Raised when a query is not a single read-only SELECT."""


def clean_sql(sql: str) -> str:
    """Strip comments and a trailing semicolon, and require one SELECT/WITH statement."""
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        raise UnsafeQuery("Empty query.")
    if ";" in sql:
        raise UnsafeQuery("Only one statement is allowed.")
    if not re.match(r"(?is)^(select|with)\b", sql):
        raise UnsafeQuery("Only SELECT queries are allowed.")
    return sql


def _authorizer(action, arg1, arg2, db_name, source):
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def run_readonly(db_path: str, sql: str, max_rows: int = MAX_ROWS, timeout: float = TIMEOUT_SECONDS):
    """Run a query read-only. Returns (columns, rows, truncated).

    Three layers: text check (clean_sql), a read-only connection, and a SQLite
    authorizer that denies anything except reads. A progress handler aborts slow queries.
    """
    sql = clean_sql(sql)
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        con.set_authorizer(_authorizer)
        deadline = time.monotonic() + timeout
        con.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10000)
        try:
            cur = con.execute(sql)
            rows = cur.fetchmany(max_rows + 1)
        except sqlite3.DatabaseError as e:
            if "interrupted" in str(e).lower():
                raise TimeoutError(f"Query took longer than {timeout}s and was stopped.") from e
            raise
        cols = [d[0] for d in cur.description] if cur.description else []
        truncated = len(rows) > max_rows
        return cols, rows[:max_rows], truncated
    finally:
        con.close()
