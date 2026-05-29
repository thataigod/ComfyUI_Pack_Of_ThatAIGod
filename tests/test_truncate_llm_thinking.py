import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest
from Truncate_LLM_Thinking import TruncateThinking


class TestTruncateThinking(unittest.TestCase):
    def setUp(self):
        self.node = TruncateThinking()

    def test_removes_single_think_block(self):
        result = self.node.truncate(
            Text="Hello <think>deep reasoning</think> world"
        )
        self.assertEqual(result[0], "Hello  world")
        self.assertEqual(result[1], "deep reasoning")

    def test_removes_multiple_think_blocks(self):
        result = self.node.truncate(
            Text="A<think>first</think>B<think>second</think>C"
        )
        self.assertEqual(result[0], "ABC")
        self.assertEqual(result[1], "first\n\nsecond")

    def test_no_think_block(self):
        result = self.node.truncate(Text="Hello world")
        self.assertEqual(result[0], "Hello world")
        self.assertEqual(result[1], "")

    def test_empty_text(self):
        result = self.node.truncate(Text="")
        self.assertEqual(result, ("", ""))

    def test_custom_tokens(self):
        result = self.node.truncate(**{
            "Text": "Before [THINK]secret reasoning[/THINK] after",
            "Start Token": "[THINK]",
            "End Token": "[/THINK]",
        })
        self.assertEqual(result[0], "Before  after")
        self.assertEqual(result[1], "secret reasoning")

    def test_multiline_think_content(self):
        result = self.node.truncate(
            Text="<think>line1\nline2\nline3</think>done"
        )
        self.assertEqual(result[0], "done")
        self.assertEqual(result[1], "line1\nline2\nline3")

    def test_special_chars_in_tokens(self):
        result = self.node.truncate(**{
            "Text": "x [??] secret [!!] y",
            "Start Token": "[??]",
            "End Token": "[!!]",
        })
        self.assertEqual(result[0], "x  y")
        self.assertEqual(result[1], "secret")

    def test_truncates_long_input(self):
        long_text = "<think>test</think>" * 20000
        result = self.node.truncate(Text=long_text)
        self.assertLess(len(result[0]), 110000)


if __name__ == "__main__":
    unittest.main()
