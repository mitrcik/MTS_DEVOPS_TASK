"""Unit-тест Markdown-отчёта: длинные и содержащие «|» детали не ломают таблицу проверок."""

from __future__ import annotations

import unittest

from pylib.report import render_markdown


class ReportMarkdownTest(unittest.TestCase):
    def test_check_cells_keep_table_intact(self) -> None:
        data = {
            "kind": "release",
            "id": "v3-notready-1",
            "decision": "rejected",
            "reason": None,
            "started_at": "t0",
            "finished_at": "t1",
            "timeline": [],
            "checks": {
                "candidate_ready": {"status": "failed", "summary": "helm: upgrade failed | Error: " + "x" * 600},
                "preview": {"status": "passed", "summary": "16/16"},
            },
        }
        rows = [line for line in render_markdown(data).splitlines() if line.startswith("| candidate_ready")]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        # code span закрыт, а «|» внутри него экранирован: в строке ровно 4 неэкранированных разделителя
        self.assertEqual(row.count("`"), 2)
        self.assertEqual(row.replace("\\|", "").count("|"), 4)
        self.assertIn("…`", row)


if __name__ == "__main__":
    unittest.main()
