import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import criteria_judge as cj  # noqa: E402
import judge_context  # noqa: E402


def part(choice, p):
    rest = {"present": "absent", "absent": "present"}.get(choice)
    probs = {choice: p, rest: 1 - p} if rest else {choice: p, **{k: (1 - p) / 2 for k in cj.LABELS if k != choice}}
    return {"choice": choice, "probabilities": probs}


def answer(opp, opp_p, label, label_p):
    return {c: {"opportunity": part(opp, opp_p), "label": part(label, label_p)} for c in judge_context.CRITERIA}


class VerdictTests(unittest.TestCase):
    C = "message_reflection"

    def test_unanimous_confident_yes_is_accepted(self):
        v = cj.verdict({"a": answer("present", .9, "yes", .85), "b": answer("present", .95, "yes", .9)}, ["a", "b"], self.C)
        self.assertEqual((v["status"], v["label"]), ("accepted", "yes"))

    def test_low_mean_probability_is_held(self):
        v = cj.verdict({"a": answer("present", .9, "no", .7), "b": answer("present", .9, "no", .8)}, ["a", "b"], self.C)
        self.assertEqual(v, {"status": "held", "reason": "label_low_confidence"})

    def test_disagreement_is_held(self):
        v = cj.verdict({"a": answer("present", .9, "yes", .9), "b": answer("present", .9, "no", .9)}, ["a", "b"], self.C)
        self.assertEqual(v["reason"], "label_disagree")

    def test_opportunity_gates_the_label(self):
        v = cj.verdict({"a": answer("absent", .9, "yes", .9), "b": answer("absent", .85, "yes", .9)}, ["a", "b"], self.C)
        self.assertEqual(v["status"], "not_applicable")
        v = cj.verdict({"a": answer("present", .9, "yes", .9), "b": answer("absent", .9, "yes", .9)}, ["a", "b"], self.C)
        self.assertEqual(v["reason"], "opportunity_disagree")

    def test_agreed_unknown_and_missing_model(self):
        v = cj.verdict({"a": answer("present", .9, "unknown", .9), "b": answer("present", .9, "unknown", .9)}, ["a", "b"], self.C)
        self.assertEqual(v["status"], "unknown")
        self.assertEqual(cj.verdict({"a": answer("present", .9, "yes", .9)}, ["a", "b"], self.C)["reason"], "missing")

    def test_weighted_rule_follows_the_heavier_model(self):
        per_model = {"a": answer("present", .9, "yes", .9), "b": answer("present", .6, "no", .7)}
        v = cj.verdict(per_model, ["a", "b"], self.C, threshold=0.5, weights={"a": 2, "b": 1})
        self.assertEqual((v["status"], v["label"]), ("accepted", "yes"))
        v = cj.verdict(per_model, ["a", "b"], self.C, threshold=0.5, weights={"a": 1, "b": 3})
        self.assertEqual((v["status"], v["label"]), ("accepted", "no"))
        v = cj.verdict(per_model, ["a", "b"], self.C, threshold=0.9, weights={"a": 2, "b": 1})
        self.assertEqual(v["status"], "held")

    def test_score_is_yes_share_of_accepted(self):
        points = [{"agent": "A", "step": 1, "verdicts": {
            "message_reflection": {"status": "accepted", "label": "yes"},
            "responsive_dialogue": {"status": "accepted", "label": "no"},
            "error_nonrepetition": {"status": "held", "reason": "label_disagree"},
            "feedback_adaptation": {"status": "unknown"},
            "epistemic_consistency": {"status": "accepted", "label": "yes"}}}]
        s = cj.summarize(points)
        self.assertAlmostEqual(s["overall"]["score"], 0.6667, places=4)
        self.assertIsNone(s["by_criterion"]["feedback_adaptation"]["score"])


class AskTests(unittest.TestCase):
    def test_parses_all_questions_and_resumes(self):
        calls = []

        def fake_urlopen(request, timeout):
            calls.append(json.loads(request.data)["model"])
            answers = {}
            for c in judge_context.CRITERIA:
                answers[f"{c}__opportunity"] = {"choice": "present", "probabilities": {"present": .9, "absent": .1}}
                answers[f"{c}__label"] = {"choice": "yes", "probabilities": {"yes": .9, "no": .05, "unknown": .05}}
            return io.BytesIO(json.dumps({"answers": answers, "usage": {"cost": 0.001}}).encode())
        bundle = {"agent": "A", "step": 3, "task": "t"}
        with tempfile.TemporaryDirectory() as tmp, mock.patch("urllib.request.urlopen", fake_urlopen), \
                mock.patch.object(judge_context, "render", lambda b: "DP"):
            manifest = Path(tmp) / "run.jsonl"
            manifest.write_text("{}\n", encoding="utf-8")
            result = cj.judge_run(manifest, [bundle], ["a", "b"], "https://example.invalid/d", "k", log=lambda _: None)
            self.assertEqual(result["summary"]["overall"]["score"], 1.0)
            self.assertAlmostEqual(result["cost_this_call"], 0.002)
            cj.judge_run(manifest, [bundle], ["a", "b"], "https://example.invalid/d", "k", log=lambda _: None)
        self.assertEqual(calls, ["a", "b"])

    def test_decisions_url(self):
        self.assertEqual(cj.decisions_url("https://openrouter.ai/api/v1/"), "https://openrouter.ai/api/alpha/decisions")


if __name__ == "__main__":
    unittest.main()
