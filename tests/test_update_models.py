import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import update_models  # noqa: E402


class FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self._body


class FakeOpener:
    def __init__(self, pages):
        self.pages = pages
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        return FakeResponse(self.pages[len(self.requests) - 1])


class UpdateModelsTests(unittest.TestCase):
    def test_fetch_models_follows_after_id_pagination(self):
        opener = FakeOpener(
            [
                {
                    "data": [{"id": "claude-sonnet-5", "display_name": "Sonnet 5"}],
                    "first_id": "claude-sonnet-5",
                    "last_id": "claude-sonnet-5",
                    "has_more": True,
                },
                {
                    "data": [{"id": "claude-haiku-5", "display_name": "Haiku 5"}],
                    "first_id": "claude-haiku-5",
                    "last_id": "claude-haiku-5",
                    "has_more": False,
                },
            ]
        )

        result = update_models.fetch_models("test-key", page_size=1, opener=opener)

        self.assertEqual([model["id"] for model in result["data"]], ["claude-sonnet-5", "claude-haiku-5"])
        self.assertEqual(result["first_id"], "claude-sonnet-5")
        self.assertEqual(result["last_id"], "claude-haiku-5")
        self.assertFalse(result["has_more"])
        self.assertEqual(len(opener.requests), 2)
        self.assertEqual(parse_qs(urlparse(opener.requests[0][0].full_url).query), {"limit": ["1"]})
        self.assertEqual(
            parse_qs(urlparse(opener.requests[1][0].full_url).query),
            {"limit": ["1"], "after_id": ["claude-sonnet-5"]},
        )
        self.assertEqual(opener.requests[0][0].get_header("X-api-key"), "test-key")

    def test_fetch_models_rejects_duplicate_ids(self):
        opener = FakeOpener(
            [
                {
                    "data": [{"id": "claude-sonnet-5"}],
                    "first_id": "claude-sonnet-5",
                    "last_id": "claude-sonnet-5",
                    "has_more": True,
                },
                {
                    "data": [{"id": "claude-sonnet-5"}],
                    "last_id": "claude-sonnet-5",
                    "has_more": False,
                },
            ]
        )
        with self.assertRaises(update_models.APIError):
            update_models.fetch_models("test-key", opener=opener)

    def test_render_and_update_readme_marked_section(self):
        document = update_models.build_document(
            {
                "data": [
                    {
                        "id": "claude-sonnet-5",
                        "display_name": "Claude | Sonnet 5",
                        "created_at": "2026-07-24T00:00:00Z",
                        "max_input_tokens": 1000000,
                        "max_tokens": 128000,
                    }
                ],
                "first_id": "claude-sonnet-5",
                "last_id": "claude-sonnet-5",
                "has_more": False,
            },
            "2026-08-01T00:00:00Z",
        )
        table = update_models.render_table(document)
        self.assertIn("Claude \\| Sonnet 5", table)
        self.assertIn("`claude-sonnet-5`", table)
        self.assertIn("1,000,000", table)

        with tempfile.TemporaryDirectory() as temporary:
            readme = Path(temporary) / "README.md"
            readme.write_text(
                "before\n"
                + update_models.BEGIN_MARKER
                + "\nold\n"
                + update_models.END_MARKER
                + "\nafter\n",
                encoding="utf-8",
            )
            update_models.update_readme(readme, document)
            result = readme.read_text(encoding="utf-8")
            self.assertTrue(result.startswith("before\n"))
            self.assertTrue(result.endswith("after\n"))
            self.assertEqual(result.count(update_models.BEGIN_MARKER), 1)
            self.assertNotIn("old", result)

    def test_write_json_does_not_include_api_key(self):
        document = update_models.build_document(
            {"data": [], "first_id": None, "last_id": None, "has_more": False},
            "2026-08-01T00:00:00Z",
        )
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "nested" / "models.json"
            update_models.write_json(output, document)
            text = output.read_text(encoding="utf-8")
            self.assertIn('"data": []', text)
            self.assertNotIn("test-key", text)


if __name__ == "__main__":
    unittest.main()
