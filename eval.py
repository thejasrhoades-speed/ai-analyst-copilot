"""Evaluate the copilot against questions with known-correct (gold) SQL.

Usage:
  python eval.py --db data/olist.db --provider gemini
  python eval.py --provider groq --limit 10          # quick smoke test
Results are saved after every question, so you can stop and re-run later (rate limits!):
it resumes where it left off. Use --fresh to start over.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from copilot.compare import results_match
from copilot.core import Copilot
from copilot.guardrails import run_readonly
from copilot.llm import get_provider


def evaluate(copilot, questions, out_path: Path, fresh=False, log=print):
    done = {}
    if out_path.exists() and not fresh:
        done = {r["id"]: r for r in json.loads(out_path.read_text())["results"]}
    for q in questions:
        if q["id"] in done:
            continue
        _, gold_rows, _ = run_readonly(copilot.db_path, q["gold_sql"])
        res = copilot.ask(q["question"], explain=False)
        correct_by_attempt = []
        for sql, err in res.history:
            if err:
                correct_by_attempt.append(False)
                continue
            try:
                _, rows, _ = run_readonly(copilot.db_path, sql)
                correct_by_attempt.append(results_match(gold_rows, rows, q["ordered"]))
            except Exception:  # noqa: BLE001
                correct_by_attempt.append(False)
        rec = {
            "id": q["id"], "difficulty": q["difficulty"], "question": q["question"],
            "generated_sql": res.sql, "attempts": res.attempts, "error": res.error,
            "first_attempt_correct": bool(correct_by_attempt and correct_by_attempt[0]),
            "final_correct": bool(correct_by_attempt and correct_by_attempt[-1]),
            "executed_first_try": bool(res.history and res.history[0][1] is None),
        }
        done[q["id"]] = rec
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({"results": list(done.values())}, indent=1))
        log(f"{q['id']} [{q['difficulty']:6s}] first={'Y' if rec['first_attempt_correct'] else 'n'} "
            f"final={'Y' if rec['final_correct'] else 'n'} attempts={rec['attempts']}")
    return list(done.values())


def summarize(results) -> str:
    def pct(a, b):
        return f"{100 * a / b:.1f}%" if b else "-"

    lines = ["| Difficulty | Questions | Executes 1st try | Correct 1st try | Correct after retry |",
             "|---|---|---|---|---|"]
    groups = [("easy", [r for r in results if r["difficulty"] == "easy"]),
              ("medium", [r for r in results if r["difficulty"] == "medium"]),
              ("hard", [r for r in results if r["difficulty"] == "hard"]),
              ("**All**", results)]
    for name, rs in groups:
        n = len(rs)
        lines.append(f"| {name} | {n} | {pct(sum(r['executed_first_try'] for r in rs), n)} | "
                     f"{pct(sum(r['first_attempt_correct'] for r in rs), n)} | "
                     f"{pct(sum(r['final_correct'] for r in rs), n)} |")
    return "\n".join(lines)


def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/olist.db")
    ap.add_argument("--questions", default="eval/questions_olist.json")
    ap.add_argument("--provider", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--limit", type=int, default=None, help="only the first N questions")
    ap.add_argument("--fresh", action="store_true", help="ignore saved results and start over")
    a = ap.parse_args()

    interval = float(os.getenv("MIN_INTERVAL", "6"))
    prov = get_provider(a.provider, a.model, min_interval=interval)
    qs = json.loads(Path(a.questions).read_text())[: a.limit]
    out = Path("eval/results") / f"{prov.name}_{prov.model.replace('/', '_')}.json"
    t0 = time.time()
    results = evaluate(Copilot(a.db, prov), qs, out, fresh=a.fresh)
    results = [r for r in results if r["id"] in {q["id"] for q in qs}]
    table = summarize(results)
    (out.with_suffix(".md")).write_text(f"Model: {prov.name} / {prov.model}\n\n{table}\n")
    print(f"\nModel: {prov.name} / {prov.model}  ({time.time() - t0:.0f}s, {prov.calls_made} API calls, {prov.cache_hits} cached)\n")
    print(table)


if __name__ == "__main__":
    main()
