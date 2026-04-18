"""Validation test suite for Yunxi daily mode."""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent
if str(_root / "src") not in sys.path:
    sys.path.insert(0, str(_root / "src"))
if str(_root / "tests") not in sys.path:
    sys.path.insert(0, str(_root / "tests"))
