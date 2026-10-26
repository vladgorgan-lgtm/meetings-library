#!/usr/bin/env python3
"""Moved to engine/build_index.py. Kept so older commands keep working."""
import os, runpy, sys
HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "engine", "build_index.py")
sys.argv[0] = TARGET
runpy.run_path(TARGET, run_name="__main__")
