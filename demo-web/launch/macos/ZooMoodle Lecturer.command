#!/bin/bash
# Double-click after the folder is on this Mac.
# First run can install the pinned requirements from this repo. It does not
# download a remote script, enable Internet Sharing, or approve a system prompt.
set -euo pipefail
cd "$(dirname "$0")/../.."
echo "ZooMoodle lecturer launcher"
echo "This is not fully automatic hotspot setup."
if [[ ! -x .venv/bin/python ]]; then
  echo "Creating a local virtualenv and installing requirements.txt from this folder."
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
exec .venv/bin/python -m helper.launch_wizard
