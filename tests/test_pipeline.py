"""Offline tests: no API key needed. Run:  python -m unittest discover -s tests -v"""
import json
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from copilot.compare import results_match
from copilot.core import Copilot, extract_sql
from copilot.guardrails import UnsafeQuery, clean_sql, run_readonly
from copilot.llm import FunctionProvider
from eval import evaluate, summarize

DB = "data/olist.db"
QS = json.loads(Path("eval/questions_olist.json").read_text())
GOLD = {q["question"]: q["gold_sql"] for q in QS}


def oracle(prompt):
    q = re.search(r"QUESTION: (.*)", prompt).group(1).strip()
    return f"```sql\n{GOLD[q]}\n```"


class Guardrails(unittest.TestCase):
    def test_blocks_writes(self):
        for bad in ["DROP TABLE orders", "DELETE FROM orders", "UPDATE orders SET order_status='x'",
                    "INSERT INTO sellers VALUES (1,2,3,4)", "PRAGMA table_info(orders)",
                    "ATTACH DATABASE 'x.db' AS x", "CREATE TABLE t (a int)"]:
            with self.assertRaises(Exception, msg=bad):
                run_readonly(DB, bad)

    def test_blocks_multi_statement_and_comment_tricks(self):
        with self.assertRaises(UnsafeQuery):
            clean_sql("SELECT 1; DROP TABLE orders")
        with self.assertRaises(UnsafeQuery):
            clean_sql("/* hi */ DELETE FROM orders")

    def test_select_works_and_limits_rows(self):
        cols, rows, trunc = run_readonly(DB, "SELECT * FROM order_items", max_rows=50)
        self.assertEqual(len(rows), 50)
        self.assertTrue(trunc)
        cols, rows, trunc = run_readonly(DB, "WITH x AS (SELECT 1 AS a) SELECT a FROM x")
        self.assertEqual(rows, [(1,)])

    def test_timeout(self):
        slow = "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r) SELECT COUNT(*) FROM r"
        with self.assertRaises(TimeoutError):
            run_readonly(DB, slow, timeout=1)

    def test_db_unchanged_after_attacks(self):
        n = sqlite3.connect(DB).execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        self.assertEqual(n, 99441)


class Compare(unittest.TestCase):
    def test_tolerances(self):
        gold = [("SP", 1.5), ("RJ", 2.25)]
        self.assertTrue(results_match(gold, [(2.25, "rj", "x"), (1.5, "sp", "y")]))  # order, case, extra col
        self.assertFalse(results_match(gold, [("SP", 1.6), ("RJ", 2.25)]))
        self.assertTrue(results_match([(12.56,)], [(12.5612,)]))
        self.assertFalse(results_match([(1,), (2,)], [(2,), (1,)], ordered=True))


class Pipeline(unittest.TestCase):
    def test_extract_sql(self):
        self.assertEqual(extract_sql("text ```sql\nSELECT 1\n``` more"), "SELECT 1")

    def test_oracle_gets_everything_right(self):
        cp = Copilot(DB, FunctionProvider(oracle))
        with tempfile.TemporaryDirectory() as d:
            res = evaluate(cp, QS, Path(d) / "r.json", log=lambda *_: None)
        self.assertEqual(len(res), len(QS))
        self.assertTrue(all(r["first_attempt_correct"] for r in res), [r["id"] for r in res if not r["first_attempt_correct"]])

    def test_retry_recovers_from_bad_sql(self):
        calls = []

        def flaky(prompt):
            calls.append(prompt)
            if "failed with this error" not in prompt:
                return "```sql\nSELECT nonexistent_col FROM orders\n```"
            return "```sql\nSELECT COUNT(*) FROM orders\n```"

        r = Copilot(DB, FunctionProvider(flaky)).ask("How many orders?")
        self.assertTrue(r.ok)
        self.assertEqual(r.attempts, 2)
        self.assertEqual(r.df.iloc[0, 0], 99441)

    def test_unsafe_sql_is_not_retried(self):
        r = Copilot(DB, FunctionProvider(lambda p: "```sql\nDROP TABLE orders\n```")).ask("drop it")
        self.assertFalse(r.ok)
        self.assertEqual(r.attempts, 1)
        self.assertIn("UnsafeQuery", r.error)

    def test_wrong_answers_are_scored_wrong_and_resume_works(self):
        def sometimes_wrong(prompt):
            q = re.search(r"QUESTION: (.*)", prompt).group(1).strip()
            return "```sql\nSELECT 0\n```" if q == QS[0]["question"] else oracle(prompt)

        cp = Copilot(DB, FunctionProvider(sometimes_wrong))
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "r.json"
            first = evaluate(cp, QS[:3], out, log=lambda *_: None)
            self.assertFalse(first[0]["final_correct"])
            self.assertTrue(first[1]["final_correct"])
            more = evaluate(cp, QS[:5], out, log=lambda *_: None)  # resumes: only 2 new
            self.assertEqual(len(more), 5)
            self.assertIn("All", summarize(more))


if __name__ == "__main__":
    unittest.main()
