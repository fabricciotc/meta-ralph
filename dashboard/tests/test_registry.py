import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
from core.registry import ToolRegistry


def dummy_tool(path: str) -> str:
    """Reads a file.

    Args:
        path: file path

    Returns:
        file content
    """
    return f"content of {path}"


class TestToolRegistry(unittest.TestCase):
    def test_register_and_invoke(self):
        reg = ToolRegistry()
        reg.register("read_file", dummy_tool)
        self.assertIn("read_file", reg.list_names())
        result = reg.invoke("read_file", {"path": "foo.txt"})
        self.assertEqual(result, "content of foo.txt")

    def test_schema_extraction(self):
        reg = ToolRegistry()
        reg.register("read_file", dummy_tool)
        schema = reg.get_schema("read_file")
        self.assertEqual(schema["name"], "read_file")
        self.assertIn("path", [p["name"] for p in schema["parameters"]])


if __name__ == "__main__":
    unittest.main()
