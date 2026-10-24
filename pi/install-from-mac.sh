#!/usr/bin/env bash
# Copies the box to a Raspberry Pi and sets it up, from the Mac:
#   ./pi/install-from-mac.sh pi@nextstep-box.local
# The Pi needs Raspberry Pi OS Lite (64-bit) with Wi-Fi and SSH turned on (Raspberry Pi Imager settings).
# Copies the repo, the Android helper app and the box's AI key (to ~/.nextstep-box on the Pi, chmod 600).
set -euo pipefail
PI=${1:?usage: ./pi/install-from-mac.sh user@host}
cd "$(dirname "$0")/.."

[ -f helper/build/nextstep-box-helper.apk ] || helper/build.sh
rsync -a --delete --exclude .venv --exclude .git --exclude __pycache__ --exclude .pytest_cache ./ "$PI:nextstep-plug-and-play/"
ssh "$PI" 'mkdir -p ~/.nextstep-box && chmod 700 ~/.nextstep-box'
scp -q ~/.nextstep-box/ai-gateway.key "$PI:.nextstep-box/ai-gateway.key"
ssh "$PI" 'chmod 600 ~/.nextstep-box/ai-gateway.key && cd nextstep-plug-and-play && ./pi/setup.sh'
