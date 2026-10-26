#!/bin/bash
# Double-click to open the Meeting Library with settings enabled.
# Runs a small server on this computer only (127.0.0.1). Close this window to stop it.
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is needed (it ships with the Xcode command line tools). Install it, then try again."
  read -r -p "Press Enter to close"; exit 1
fi
exec python3 engine/serve.py
