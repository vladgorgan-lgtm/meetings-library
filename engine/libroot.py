"""Where the library lives. One rule, shared by every engine script.

  --library PATH   explicit, wins
  $MEETING_LIBRARY  next
  default          the folder that contains engine/

The engine is code; the library root is data. Keeping the lookup in one place is
what lets the same engine run against your archive or against kit/sample/.
"""
import os
import sys

ENGINE = os.path.dirname(os.path.abspath(__file__))


def library_root(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    for i, a in enumerate(argv):
        if a == "--library" and i + 1 < len(argv):
            return os.path.abspath(os.path.expanduser(argv[i + 1]))
        if a.startswith("--library="):
            return os.path.abspath(os.path.expanduser(a.split("=", 1)[1]))
    env = os.environ.get("MEETING_LIBRARY")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.dirname(ENGINE)
