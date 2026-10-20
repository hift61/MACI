import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import maci_judge  # noqa: E402


class DecisionsJudgeTests(unittest.TestCase):
    def test_fewshot_file_has_rubric_and_examples(self):
        data = json.loads(Path(maci_judge.FEWSHOT_FILE).read_text(encoding="utf-8"))
        self.assertTrue(data["rubric"])
        self.assertEqual(len(data["examples"]), 3)

    def test_expected_value_and_request_body(self):
        sent = {}

        def fake_urlopen(request, timeout):
            sent.update(json.loads(request.data))
            return io.BytesIO(json.dumps({"answers": {"q": {"choice": "2", "probabilities": {"2": 0.5, "4": 0.5}}},
                                          "usage": {"cost": 0.001}}).encode())
        fewshot = {"rubric": "R", "examples": [{"decision_point": "X", "human_score": 3}]}
        with mock.patch("urllib.request.urlopen", fake_urlopen), mock.patch("time.sleep"):
            answer = maci_judge.ask_decisions("https://example.invalid/d", "k", "m", "DP", fewshot, log=lambda _: None)
        self.assertEqual(answer, {"score": 3.0, "argmax": 2, "cost": 0.001})
        self.assertEqual(sent["state"]["decision_point"], "DP")
        self.assertEqual(len(sent["questions"]["q"]["criteria"]), 11)

    def test_failure_gives_nan(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("down")), mock.patch("time.sleep"):
            answer = maci_judge.ask_decisions("https://example.invalid/d", "k", "m", "DP", {"rubric": "R", "examples": []}, log=lambda _: None)
        self.assertNotEqual(answer["score"], answer["score"])


if __name__ == "__main__":
    unittest.main()
