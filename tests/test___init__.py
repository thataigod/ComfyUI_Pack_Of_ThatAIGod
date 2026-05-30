import importlib
import os
import sys
import types
import unittest
from unittest.mock import patch

import _utils

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

comfy_mock = types.ModuleType('comfy')
comfy_mock.utils = types.ModuleType('comfy.utils')
comfy_mock.utils.common_upscale = None
sys.modules['comfy'] = comfy_mock
sys.modules['comfy.utils'] = comfy_mock.utils

server_mock = types.ModuleType('server')
class PromptServerMock:
    instance = type('inst', (), {'send_sync': lambda *a: None})()
server_mock.PromptServer = PromptServerMock
sys.modules['server'] = server_mock


class TestInit(unittest.TestCase):
    def test_import_error_path_logs_warning(self):
        if '__init__' in sys.modules:
            del sys.modules['__init__']

        with patch.object(_utils, "safe_import") as mock_safe:
            def side_effect(name):
                if name == "LLM_Node":
                    return None
                return importlib.import_module(name)
            mock_safe.side_effect = side_effect

            import __init__ as pkg
            self.assertIn("LLM_Node", pkg._import_errors)
            self.assertGreater(len(pkg.NODE_CLASS_MAPPINGS), 0)


if __name__ == "__main__":
    unittest.main()
