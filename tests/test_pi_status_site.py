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

    def test_criterion_label_rating_is_saved_shown_and_compared(self):
        page = self.get("/eval/run?path=trial/run.jsonl")
        self.assertIn("평가 기회:", page)
        self.assertIn('name="label" value="not_applicable"', page)
        point = page.split('<details id="p-A-9">')[1].split('<details id="p-')[0]
        self.assertIn('value="message_reflection" selected', point)  # message trigger -> 메시지 정보 반영
        form = {"path": "trial/run.jsonl", "agent": "A", "step": 9, "criterion": "message_reflection",
                "label": "yes", "comment": "moved to pad_B after the message"}
        page = self.post("/eval/rate", {**form, "rater": "kim"})
        saved = judge_context.load_anchor_ratings(self.manifest, "kim")["9|A"]
        self.assertEqual((saved["criterion"], saved["label"]), ("message_reflection", "yes"))
        self.assertIn("kim 충족(메시지 정보 반영)", page)
        self.assertIn(" checked>", page.split('<details id="p-A-9">')[1].split('<details id="p-')[0])
        page = self.post("/eval/rate", {**form, "rater": "lee", "label": "unknown"})
        self.assertIn("kim vs lee · 메시지 정보 반영: 공통 1개  일치율=0.000", page)
        self.assertEqual(judge_context.load_all_anchor_ratings(self.manifest), {"kim": {}, "lee": {}})
        for bad in ({"label": "maybe"}, {"criterion": "nope"}, {"comment": " "}):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.post("/eval/rate", {**form, "rater": "kim", **bad})
            self.assertEqual(error.exception.code, 400)

    def test_turn_context_shows_matching_maps_and_only_selected_observation(self):
        records = [json.loads(line) for line in self.manifest.read_text(encoding="utf-8").splitlines()]
        for record in records:
            record["world"] = {"width": 400, "height": 300, "walls": [[190, 0, 10, 200]],
                               "objects": [{"object_id": "door", "type": "door", "x": 200, "y": 210,
                                            "locked": record["step"] < 9}]}
            for a in record["agents"]:
                a.update(position=[record["step"] * 10, 100], facing=90)
        self.manifest.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
        self.manifest.with_suffix(".observations.jsonl").write_text(
            '\n'.join(json.dumps(r) for r in [
                {"step": 9, "agent": "A", "observation": {"inbox": ["A_OBSERVATION_9"],
                 "notice": '<script>alert(1)</script> sk-abcdefghijklmnop'}},
                {"step": 8, "agent": "A", "observation": {"notice": "WRONG_TURN"}},
                {"step": 9, "agent": "B", "observation": {"notice": "SECRET_B_OBSERVATION"}}])
            + '\n{"step":', encoding="utf-8")
        page = self.get("/eval/run?path=trial/run.jsonl")
        point = page.split('<details id="p-A-9">')[1].split('<details id="p-')[0]
        self.assertIn("직전 턴 종료 · step 8", point)
        self.assertIn("행동 후 · step 9", point)
        self.assertEqual(point.count('aria-label="턴 상황 지도"'), 2)
        self.assertIn("A_OBSERVATION_9", point)
        self.assertNotIn("WRONG_TURN", point)
        self.assertNotIn("SECRET_B_OBSERVATION", point)
        self.assertNotIn("<script>", point)
        self.assertNotIn("sk-abcdefghijklmnop", point)
        self.assertIn("[redacted]", point)

    def test_old_logs_show_missing_context_without_breaking_ratings(self):
        page = self.get("/eval/run?path=trial/run.jsonl")
        self.assertIn("이 시점의 지도 기록이 없습니다", page)
        self.assertIn("이 턴의 관찰 기록이 없습니다", page)
        self.assertIn('action="rate"', page)

    def test_first_turn_uses_initial_scene_and_no_later_frame(self):
        from site_turn_context import TurnContext
        self.manifest.with_suffix(".scene.json").write_text(json.dumps({
            "world": {"width": 400, "height": 300, "objects": [], "walls": []},
            "agents": [{"agent": "A", "position": [20, 30], "facing": 0}]
        }, indent=2), encoding="utf-8")
        context = TurnContext(self.manifest)
        page = context.render(1, "A", pi_status_site.esc)
        self.assertIn("직전 턴 종료 · step 0", page)
        self.assertEqual(page.count('aria-label="턴 상황 지도"'), 1)
        self.assertIn("행동 후 · step 1", page)
        self.assertNotIn("pad_B ready", page)

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


class PublicSiteTests(unittest.TestCase):
    """외부 공개용: 비밀번호(Basic 인증)와 읽기 전용"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.manifest = write_run(self.root)
        evaluator = pi_status_site.Evaluator(self.root, read_only=True)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0),
                                          pi_status_site.make_handler(self.root, evaluator, "correct-horse"))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def request(self, path, password=None, data=None):
        import base64
        req = urllib.request.Request(self.base + path, data=data)
        if password is not None:
            req.add_header("Authorization", "Basic " + base64.b64encode(f"any:{password}".encode()).decode())
        with urllib.request.urlopen(req) as response:
            return response.read().decode("utf-8")

    def test_every_page_needs_the_password(self):
        for path in ("/", "/status.json", "/eval", "/eval/run?path=run.jsonl"):
            for password in (None, "wrong"):
                with self.assertRaises(urllib.error.HTTPError) as error:
                    self.request(path, password)
                self.assertEqual(error.exception.code, 401)
        self.assertIn("run.jsonl", self.request("/eval", "correct-horse"))

    def test_read_only_hides_the_rating_form_and_refuses_ratings(self):
        page = self.request("/eval/run?path=run.jsonl", "correct-horse")
        self.assertNotIn('action="rate"', page)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request("/eval/rate", "correct-horse", urllib.parse.urlencode(
                {"path": "run.jsonl", "agent": "A", "step": 9, "rater": "x", "score": 5}).encode())
        self.assertEqual(error.exception.code, 403)
        self.assertEqual(judge_context.load_anchor_ratings(self.manifest, "x"), {})


if __name__ == "__main__":
    unittest.main()
