"""judge_context.py: decision-point bundles for the judge (anchors, prior-context retrieval, what the agent knew)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import judge_context  # noqa: E402

CODE_V1 = "def decide(observation):\n    # DECISION START\n    return finish('move_forward', distance=20)\n    # DECISION END\n"
CODE_V2 = ("def decide(observation):\n    # DECISION START\n    # B said pad_B is ready: wait for GO\n"
           "    return finish('noop')\n    # DECISION END\n")


def _call(call_id, name, args):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def _step_result(step):
    return {"role": "user", "content": "Simulation step result:\n" + json.dumps({"observation": {"self": {"step": step}}})}


def write_run(folder: Path) -> Path:
    manifest = folder / "run.jsonl"
    archive = []
    for agent in ("A", "B"):
        archive.append({"agent": agent, "message": {"role": "assistant", "content": None,
                                                     "tool_calls": [_call(f"{agent}1", "submit_policy_code",
                                                                          {"code": CODE_V1})]}})
    archive += [{"agent": "A", "message": _step_result(9)},
                {"agent": "A", "message": {"role": "assistant", "content": None, "tool_calls": [
                    _call("A2", "manage_context", {"summary": "B owns pad_B; first sync failed at step 5"})]}},
                {"agent": "A", "message": {"role": "assistant", "content": None, "tool_calls": [
                    _call("A3", "submit_policy_code", {"code": CODE_V2})]}},
                {"agent": "B", "message": {"role": "assistant", "content": None, "tool_calls": [
                    _call("B9", "manage_context", {"summary": "SECRET partner-only plan"})]}}]
    (folder / "run.context_archive.jsonl").write_text("\n".join(json.dumps(e) for e in archive), encoding="utf-8")
    records = []
    for step in range(1, 16):
        events, messages = [], []
        if step == 5:
            events.append({"step": 5, "type": "sync_fail", "agent_ids": ["A"], "group": "g"})
        if step == 6:
            events.append({"step": 6, "type": "move_blocked", "agent_ids": ["A"]})
        if step == 9:
            messages.append({"step": 9, "from": "B", "receiver_id": "A", "content": "pad_B ready, say GO"})
        records.append({"step": step, "task": {"A": "task A", "B": "task B"}, "events": events, "messages": messages,
                        "agents": [{"agent": a, "decision": {
                            "action": {"type": "noop", "memory": {"phase": "wait" if step >= 9 else "go"}},
                            "final_action": {"type": "move_forward" if step < 9 else "noop", "distance": 20}}}
                            for a in ("A", "B")]})
    manifest.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    return manifest


class JudgeContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.manifest = write_run(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_failures_and_messages_become_separate_decision_points(self):
        bundles = judge_context.build_bundles(self.manifest, agent_filter="A", min_anchors=0)
        self.assertEqual([b["step"] for b in bundles], [5, 9])
        self.assertTrue(any("move_blocked" in t for t in bundles[0]["trigger"]))  # step 6 merged into step 5
        self.assertTrue(any("pad_B ready" in t for t in bundles[1]["trigger"]))

    def test_bundle_holds_response_memory_summary_and_only_earlier_context(self):
        bundle = judge_context.build_bundles(self.manifest, agent_filter="A", min_anchors=0)[1]
        self.assertEqual(bundle["task"], "task A")
        self.assertEqual(bundle["memory"], {"phase": "wait"})
        response = "\n".join(t["text"] for t in bundle["response"])
        self.assertIsNone(bundle["summary"])  # the summary was written after the trigger, so it is part of the response
        self.assertIn("first sync failed", response)
        self.assertIn("+    # B said pad_B is ready", response)  # a diff, not the whole code again
        self.assertTrue(all(c["step"] < 9 for c in bundle["retrieved"]))
        self.assertTrue(bundle["actions"][-1].startswith("step 9-15: noop"))  # repeated actions are run-length merged

    def test_partner_internals_never_leak_into_a_bundle(self):
        for bundle in judge_context.build_bundles(self.manifest, agent_filter="A"):
            self.assertNotIn("SECRET", judge_context.render(bundle))

    def test_render_trims_long_fields_when_given_a_budget(self):
        bundle = judge_context.build_bundles(self.manifest, agent_filter="A", min_anchors=0)[1]
        self.assertLess(len(judge_context.render(bundle, budget=20)), len(judge_context.render(bundle)))

    def test_an_agent_with_no_outside_change_still_gets_routine_decision_points(self):
        bundles = judge_context.build_bundles(self.manifest, agent_filter="B")  # B got no message and no failure
        self.assertTrue(bundles)
        self.assertTrue(all("routine" in b["trigger"][0] for b in bundles))

    def test_lexical_similarity_prefers_shared_object_ids(self):
        sim = judge_context.LexicalSimilarity(["pad_B is ready", "the weather is nice"])
        near, far = sim.score("enter pad_B now", ["pad_B is ready", "the weather is nice"])
        self.assertGreater(near, far)

    def test_anchors_are_capped_evenly(self):
        triggers = {s: [f"t{s}"] for s in range(0, 200, 10)}
        anchors = judge_context.select_anchors(triggers, merge_window=4, max_anchors=5)
        self.assertEqual(len(anchors), 5)
        self.assertEqual((anchors[0]["step"], anchors[-1]["step"]), (0, 190))


if __name__ == "__main__":
    unittest.main()
