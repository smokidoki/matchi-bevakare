#!/bin/bash
# Installerar MATCHi-bevakaren på Mac och startar den automatiskt vid inloggning.
# Kör:  bash installera_mac.sh  matchi-tennis-DITTÄMNE
set -e
TOPIC="${1:?Ange ditt ntfy-ämne, t.ex: bash installera_mac.sh matchi-tennis-abc123}"
DIR="$(cd "$(dirname "$0")" && pwd)"
command -v python3 >/dev/null || { echo "Installera Python 3 först: https://www.python.org/downloads/"; exit 1; }
python3 -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install -q -r "$DIR/requirements.txt"
NTFY_TOPIC="$TOPIC" "$DIR/.venv/bin/python" "$DIR/matchi_bevakare.py" --test-notis
PLIST="$HOME/Library/LaunchAgents/se.matchi.bevakare.plist"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>se.matchi.bevakare</string>
  <key>ProgramArguments</key><array>
    <string>$DIR/.venv/bin/python</string><string>$DIR/matchi_bevakare.py</string>
  </array>
  <key>EnvironmentVariables</key><dict><key>NTFY_TOPIC</key><string>$TOPIC</string></dict>
  <key>StartInterval</key><integer>300</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$DIR/bevakare.log</string>
  <key>StandardErrorPath</key><string>$DIR/bevakare.log</string>
</dict></plist>
PL
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Klart! Bevakaren kör var 5:e minut. Logg: $DIR/bevakare.log"
echo "Stänga av:  launchctl unload $PLIST"
