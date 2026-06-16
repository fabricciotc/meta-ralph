from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.chat_formatter import format_chat_response


SAMPLE_NOISY = """• Using `dotnet` and `humanizer` skills.Hola. `dotnet` y `humanizer` están activos. ¿Qué querés que haga?
• User is greeting "Hola". The system reminder requires invoking relevant skills before any response or action.
• Skills loaded. Need respond to greeting. Since user said "Hola" and context is a software factory, respond in Spanish concisely.
To resume this session: kimi -r session_32c8f7d0-4913-48ea-b1f9-048f5054983e"""


SAMPLE_FOLDER = """• La solución de consola en .NET se está creando dentro de este mismo repo, en la carpeta: **`GestionProductos/`**
• The user asks in Spanish about folder location. We must invoke dotnet skill first.
To resume this session: kimi -r session_02528c1d-98c5-43c2-af8d-23ff3ce3f2f9"""


class TestChatFormatter(unittest.TestCase):
    def test_strips_internal_reasoning_and_session_footer(self):
        result = format_chat_response(SAMPLE_NOISY)
        self.assertIn("Hola", result["reply"])
        self.assertNotIn("system reminder", result["reply"])
        self.assertNotIn("To resume this session", result["reply"])
        self.assertGreaterEqual(len(result["trace"]), 1)
        self.assertIn("dotnet", result["meta"]["skills"])

    def test_keeps_user_facing_folder_answer(self):
        result = format_chat_response(SAMPLE_FOLDER)
        self.assertIn("GestionProductos", result["reply"])
        self.assertNotIn("The user asks", result["reply"])

    def test_empty_input(self):
        result = format_chat_response("")
        self.assertEqual(result["reply"], "")


if __name__ == "__main__":
    unittest.main()
