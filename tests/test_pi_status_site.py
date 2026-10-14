"""pi_status_site.py: live log page and the log evaluation pages (decision points, human rating, judge)."""
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import judge_context  # noqa: E402
import pi_status_site  # noqa: E402
from tests.test_judge_context import write_run  # noqa: E402


class StatusSiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "trial").mkdir()
        self.manifest = write_run(self.root / "trial")
        (self.root / "trial" / "run.log").write_text("step 3/15: cleared=False\nkey sk-abcdefghijklmnop\n",
                                                     encoding="utf-8")
        (self.root / "secret.txt").write_text("nope", encoding="utf-8")
        self.evaluator = pi_status_site.Evaluator(self.root.resolve(), allow_judge=True)
        self.evaluator.client = lambda: object()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0),
                                          pi_status_site.make_handler(self.root.resolve(), self.evaluator))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def get(self, path):
        with urllib.request.urlopen(self.base + path) as response:
            return response.read().decode("utf-8")

    def post(self, path, form):
        data = urllib.parse.urlencode(form).encode()
        with urllib.request.urlopen(urllib.request.Request(self.base + path, data=data)) as response:
            return response.read().decode("utf-8")

    def test_live_status_reads_logs_in_subfolders_and_redacts_keys(self):
        status = json.loads(self.get("/status.json"))
        self.assertEqual(status["maps"][0]["map"], "trial/run")
        self.assertEqual(status["maps"][0]["step"], 3)
        self.assertIn("[redacted]", "\n".join(status["maps"][0]["lines"]))

    def test_eval_lists_runs_and_shows_decision_points(self):
        self.assertIn("trial/run.jsonl", self.get("/eval"))
        page = self.get("/eval/run?path=trial/run.jsonl")
        self.assertIn("step 5", page)
        self.assertIn("pad_B ready", page)
        a_points = [part for part in page.split('<details id="p-')[1:] if part.startswith("A-")]
        self.assertTrue(a_points)
        self.assertFalse(any("SECRET" in part for part in a_points))  # B's own summary never shows in A's points

    def test_human_rating_is_saved_and_shown(self):
        page = self.post("/eval/rate", {"path": "trial/run.jsonl", "agent": "A", "step": 9, "rater": "kim",
                                        "score": 7, "comment": "used the message"})
        self.assertEqual(judge_context.load_anchor_ratings(self.manifest, "kim")["9|A"]["score"], 7)
        self.assertIn("kim 7", page)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post("/eval/rate", {"path": "trial/run.jsonl", "agent": "A", "step": 9, "rater": "kim",
                                     "score": 11})
        self.assertEqual(error.exception.code, 400)

    def test_paths_outside_the_folder_or_non_runs_are_refused(self):
        for path in ("../secret.txt", "secret.txt", "trial/run.context_archive.jsonl", "/etc/passwd"):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.get("/eval/run?path=" + urllib.parse.quote(path))
            self.assertEqual(error.exception.code, 404)

    def test_judge_button_scores_every_decision_point(self):
        with patch("maci_judge.ask_judge", return_value=6.0):
            self.post("/eval/judge", {"path": "trial/run.jsonl"})
            deadline = time.time() + 30
            while not self.evaluator.jobs.get("trial/run.jsonl", "").startswith("완료") and time.time() < deadline:
                time.sleep(0.05)
        self.assertIn("완료", self.evaluator.jobs["trial/run.jsonl"])
        scores = judge_context.judge_scores(self.manifest)
        self.assertTrue(scores and all(v == 6.0 for s in scores.values() for v in s.values()))

    def test_judge_is_refused_unless_allowed(self):
        self.evaluator.allow_judge = False
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post("/eval/judge", {"path": "trial/run.jsonl"})
        self.assertEqual(error.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
