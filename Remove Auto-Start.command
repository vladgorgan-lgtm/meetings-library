#!/bin/bash
# Double-click to stop the Meeting Library server and stop it starting at login.
LABEL=com.meetinglibrary.server
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Auto-start removed. Use Start Meeting Library.command to run it by hand."
sleep 3
