"""Textual TUI for victus-suite (package under bin/)."""

import os
import sys

_HERE = os.path.dirname(os.path.realpath(__file__))
_BIN = os.path.dirname(_HERE)
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)
