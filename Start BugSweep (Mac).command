#!/bin/sh
# Double-click this file to open BugSweep.
cd "$(dirname "$0")" || exit 1

if command -v python3 >/dev/null 2>&1; then
    exec python3 -m bugsweep
fi

echo
echo "  BugSweep needs Python, which isn't installed on this Mac yet."
echo
echo "  1. Go to https://www.python.org/downloads/ and download the macOS installer."
echo "  2. Open it and follow the steps."
echo "  3. Double-click this file again."
echo
echo "  Stuck? Contact tech support - see support.json in this folder for details."
open "https://www.python.org/downloads/"
read -r -p "Press Enter to close..." _
