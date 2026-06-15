import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
from core.repo_parser import RepoParser


class TestRepoParser(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "foo.py").write_text(
            """
class Foo:
    def bar(self, x: int) -> int:
        return x + 1
"""
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_generate_symbols(self):
        parser = RepoParser(self.root)
        symbols = parser.generate_symbols()
        classes = [s for s in symbols if s["kind"] == "class"]
        methods = [s for s in symbols if s["kind"] == "method"]
        self.assertEqual(len(classes), 1)
        self.assertEqual(classes[0]["name"], "Foo")
        self.assertEqual(len(methods), 1)
        self.assertEqual(methods[0]["name"], "bar")

    def test_get_structure(self):
        parser = RepoParser(self.root)
        structure = parser.get_structure()
        self.assertIn("files", structure)
        self.assertEqual(len(structure["files"]), 1)


if __name__ == "__main__":
    unittest.main()
