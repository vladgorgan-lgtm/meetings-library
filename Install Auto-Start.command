#!/bin/bash
# Double-click once. The Meeting Library server then starts by itself when you log in and
# keeps running in the background. Open http://127.0.0.1:8765/ (or Meeting Library.webloc).
cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"
PY="$(command -v python3)"
if [ -z "$PY" ]; then
  echo "Python 3 is needed (it ships with the Xcode command line tools). Install it, then try again."
  read -r -p "Press Enter to close"; exit 1
fi
LABEL=com.meetinglibrary.server
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/meeting-library.log"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>$PY</string><string>$ROOT/engine/serve.py</string><string>--no-open</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict></plist>
PLISTEOF
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
launchctl bootstrap "gui/$(id -u)" "$PLIST" || { echo "Could not start it. See $LOG"; read -r -p "Press Enter to close"; exit 1; }
for i in 1 2 3 4 5 6 7 8 9 10; do
  curl -fs http://127.0.0.1:8765/api/ping >/dev/null 2>&1 && break
  sleep 1
done
if curl -fs http://127.0.0.1:8765/api/ping >/dev/null 2>&1; then
  echo "Done. The Meeting Library now runs by itself at http://127.0.0.1:8765/"
  open "http://127.0.0.1:8765/"
else
  echo "The server did not answer. Check $LOG"
fi
sleep 3
