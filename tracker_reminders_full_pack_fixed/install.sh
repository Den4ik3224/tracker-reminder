#!/usr/bin/env bash
set -euo pipefail

echo "== Tracker → Reminders installer (MSK 20:00, .env, auto yc install) =="
USER_HOME="${HOME}"
ENV_PATH="${USER_HOME}/.tracker_reminders.env"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python3 not found. Please install Python 3."
  exit 1
fi

# ensure yc
if ! command -v yc >/dev/null 2>&1; then
  echo "[yc] Yandex Cloud CLI not found. Installing..."
  if command -v brew >/dev/null 2>&1; then
    brew tap yandex-cloud/yc || true
    brew install yandex-cloud-cli || true
  fi
  if ! command -v yc >/dev/null 2>&1; then
    /bin/bash -c "curl -sSL https://storage.yandexcloud.net/yandexcloud-yc/install.sh | bash"
    if [ -d "${HOME}/yandex-cloud/bin" ]; then
      export PATH="${HOME}/yandex-cloud/bin:${PATH}"
      echo 'export PATH="$HOME/yandex-cloud/bin:$PATH"' >> "${HOME}/.zshrc" 2>/dev/null || true
      echo 'export PATH="$HOME/yandex-cloud/bin:$PATH"' >> "${HOME}/.bash_profile" 2>/dev/null || true
    fi
  fi
  if ! command -v yc >/dev/null 2>&1; then
    echo "[yc] ERROR: Could not install yc automatically."; exit 1
  fi
fi

read -r -p "Enter CLOUD_ORG_ID (Cloud Organization ID): " CLOUD_ORG_ID
read -r -p "Enter YT_BOARD_ID (numeric board id, e.g. 582): " YT_BOARD_ID
read -r -p "Extra filter (YT_QUERY_XTRA), default 'Status: !Closed': " YT_QUERY_XTRA
YT_QUERY_XTRA="${YT_QUERY_XTRA:-Status: !Closed}"
read -r -p "Assignee filter (YT_ASSIGNEE) e.g. 'me()' or 'unassigned' or 'user1,user2' [empty to skip]: " YT_ASSIGNEE
read -r -p "Reminders list prefix (REM_LIST_PREFIX) [optional]: " REM_LIST_PREFIX

cat > "${ENV_PATH}" <<EOF
# Tracker → Reminders configuration
CLOUD_ORG_ID=${CLOUD_ORG_ID}
YT_BOARD_ID=${YT_BOARD_ID}
YT_QUERY_XTRA=${YT_QUERY_XTRA}
YT_ASSIGNEE=${YT_ASSIGNEE}
REM_LIST_PREFIX=${REM_LIST_PREFIX}
EOF

echo "Config saved to ${ENV_PATH}"
echo "Installing Python dependency: yandex_tracker_client"
python3 -m pip install --user yandex_tracker_client >/dev/null

BIN_DIR="${USER_HOME}/bin"
mkdir -p "${BIN_DIR}"
SCRIPT_PATH="${BIN_DIR}/tracker_to_reminders.py"
cp "$(dirname "$0")/tracker_to_reminders.py" "${SCRIPT_PATH}"
chmod +x "${SCRIPT_PATH}"

PLIST="${USER_HOME}/Library/LaunchAgents/com.tracker.reminders.sync.plist"
mkdir -p "$(dirname "${PLIST}")"
cat > "${PLIST}" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.tracker.reminders.sync</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${HOME}/yandex-cloud/bin</string>
    <key>TRACKER_REMINDERS_ENV</key><string>${ENV_PATH}</string>
  </dict>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>${SCRIPT_PATH}</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key><integer>3</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key><string>/tmp/tracker2reminders.out</string>
  <key>StandardErrorPath</key><string>/tmp/tracker2reminders.err</string>
  <key>RunAtLoad</key><true/>
</dict>
</plist>
PL

launchctl unload "${PLIST}" >/dev/null 2>&1 || true
launchctl load  "${PLIST}"

echo "LaunchAgent installed: com.tracker.reminders.sync"
echo "Running initial sync (guard may skip if not Tue 20:00 MSK)..."
/usr/bin/python3 "${SCRIPT_PATH}" || true
echo "Done."
