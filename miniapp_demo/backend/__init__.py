"""miniapp_demo backend package.

Ensure `common` (agent_framework + llm) is importable by adding
the miniapp_demo directory to sys.path.
"""
import os
import sys
from pathlib import Path

_miniapp_demo_dir = str(Path(__file__).resolve().parent.parent)
if _miniapp_demo_dir not in sys.path:
    sys.path.insert(0, _miniapp_demo_dir)
