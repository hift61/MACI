import argparse
import os
import subprocess
import tempfile
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'enviroment'))

import providers  # noqa: E402
from policy import agent_reasoning_params  # noqa: E402


def parse(*argv):
    parser = argparse.ArgumentParser()
    providers.add_arguments(parser, embed=True)
    return parser.parse_args(list(argv))


class ProviderTests(unittest.TestCase):
    def test_defaults_per_provider(self):
        self.assertEqual(providers.base_url(parse()), "https://openrouter.ai/api/v1")
        self.assertEqual(providers.base_url(parse("--provider", "openai")), "https://api.openai.com/v1")
        self.assertIn("generativelanguage.googleapis.com", providers.base_url(parse("--provider", "gemini")))
        self.assertEqual(providers.base_url(parse("--provider", "gemini", "--base-url", "http://x/v1")), "http://x/v1")

    def test_model_prefix_is_stripped_only_for_matching_provider(self):
        self.assertEqual(providers.model_name(parse("--provider", "openai"), "openai/gpt-6-luna"), "gpt-6-luna")
        self.assertEqual(providers.model_name(parse("--provider", "gemini"), "google/gemini-x"), "gemini-x")
        self.assertEqual(providers.model_name(parse("--provider", "gemini"), "gemini-x"), "gemini-x")
        self.assertEqual(providers.model_name(parse(), "openai/gpt-6-luna"), "openai/gpt-6-luna")

    def test_key_file_then_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "k.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(" secret \n")
            self.assertEqual(providers.read_key(parse("--provider", "openai", "--api-key-file", path)), "secret")
            missing = os.path.join(tmp, "none.txt")
            with mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "g"}, clear=True):
                self.assertEqual(providers.read_key(parse("--provider", "gemini", "--api-key-file", missing)), "g")
            with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(SystemExit):
                providers.read_key(parse("--provider", "openai", "--api-key-file", missing))
        self.assertEqual(providers.read_key(parse("--base-url", "http://127.0.0.1:8080/v1")), "local")

    def test_reasoning_params(self):
        self.assertEqual(providers.reasoning_params(parse(), "low", agent_reasoning_params),
                         agent_reasoning_params("low"))
        self.assertEqual(providers.reasoning_params(parse("--provider", "gemini"), "low", agent_reasoning_params),
                         {"reasoning_effort": "low"})

    def test_embed_model_default(self):
        self.assertEqual(providers.embed_model(parse("--provider", "gemini")), "gemini-embedding-001")
        self.assertEqual(providers.embed_model(parse("--embed-model", "e")), "e")

    def test_key_files_are_gitignored(self):
        for name in ("key.txt", "openai_key.txt", "gemini_key.txt"):
            result = subprocess.run(["git", "check-ignore", "-q", name], cwd=providers.HERE)
            self.assertEqual(result.returncode, 0, name)


if __name__ == "__main__":
    unittest.main()
