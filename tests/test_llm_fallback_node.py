import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest
from LLM_Fallback_Node import LLM_Fallback_Node


class TestLLMFallbackSwitch(unittest.TestCase):
    def setUp(self):
        self.node = LLM_Fallback_Node()

    def test_returns_generated_when_status_true(self):
        result = self.node.switch(**{
            "Original Input": "fallback",
            "Generated Text": "generated response",
            "Status (Boolean)": True,
        })
        self.assertEqual(result[0], "generated response")

    def test_returns_original_when_status_false(self):
        result = self.node.switch(**{
            "Original Input": "fallback text",
            "Generated Text": "generated",
            "Status (Boolean)": False,
        })
        self.assertEqual(result[0], "fallback text")

    def test_returns_original_when_generated_empty(self):
        result = self.node.switch(**{
            "Original Input": "fallback",
            "Generated Text": "",
            "Status (Boolean)": True,
        })
        self.assertEqual(result[0], "fallback")

    def test_returns_original_when_generated_whitespace(self):
        result = self.node.switch(**{
            "Original Input": "fallback",
            "Generated Text": "   ",
            "Status (Boolean)": True,
        })
        self.assertEqual(result[0], "fallback")

    def test_handles_none_generated_text(self):
        result = self.node.switch(**{
            "Original Input": "fallback",
            "Generated Text": None,
            "Status (Boolean)": True,
        })
        self.assertEqual(result[0], "fallback")

    def test_handles_none_status(self):
        result = self.node.switch(**{
            "Original Input": "fallback",
            "Generated Text": "generated",
            "Status (Boolean)": None,
        })
        self.assertEqual(result[0], "fallback")

    def test_handles_missing_optional_inputs(self):
        result = self.node.switch(**{
            "Original Input": "fallback",
        })
        self.assertEqual(result[0], "fallback")


if __name__ == "__main__":
    unittest.main()
