"""Schema introspection: builds the text the LLM sees about the database."""
from __future__ import annotations

import sqlite3
from pathlib import Path


def schema_text(db_path: str, sample_rows: int = 2) -> str:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        out = []
        for t in tables:
            info = con.execute(f'PRAGMA table_info("{t}")').fetchall()
            cols = ", ".join(f"{c[1]} {c[2] or ''}".strip() + (" PK" if c[5] else "") for c in info)
            n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            line = f"TABLE {t} ({n} rows): {cols}"
            fks = con.execute(f'PRAGMA foreign_key_list("{t}")').fetchall()
            if fks:
                line += "\n  FOREIGN KEYS: " + ", ".join(f"{f[3]} -> {f[2]}.{f[4]}" for f in fks)
            if sample_rows:
                rows = con.execute(f'SELECT * FROM "{t}" LIMIT {sample_rows}').fetchall()
                names = [c[1] for c in info]
                for r in rows:
                    short = {n_: (str(v)[:40] if v is not None else None) for n_, v in zip(names, r)}
                    line += f"\n  e.g. {short}"
            out.append(line)
        return "\n".join(out)
    finally:
        con.close()


def notes_text(db_path: str) -> str:
    """Optional business notes stored next to the database as <name>.notes.md."""
    p = Path(db_path).with_suffix(".notes.md")
    return p.read_text(encoding="utf-8") if p.exists() else ""
