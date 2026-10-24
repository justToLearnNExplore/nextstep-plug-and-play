#!/usr/bin/env bash
# Sets up a Raspberry Pi (Raspberry Pi OS Lite, 64-bit) as a NextStep Box. Run on the Pi, in the repo:
#   ./pi/setup.sh
# Installs Python, ADB, sound tools and espeak-ng; turns on the I2S microphone + amplifier (HARDWARE.md);
# lets the box use phones over USB; and starts the box at every power-on.
set -euo pipefail
cd "$(dirname "$0")/.."

sudo apt-get update -q
sudo apt-get install -y -q python3-venv python3-gpiozero python3-lgpio adb alsa-utils espeak-ng

CONFIG=/boot/firmware/config.txt
if ! grep -q '^dtoverlay=googlevoicehat-soundcard' "$CONFIG"; then
  printf '\n# NextStep Box: INMP441 microphone + MAX98357A amplifier on I2S\ndtparam=i2s=on\ndtoverlay=googlevoicehat-soundcard\n' \
    | sudo tee -a "$CONFIG" >/dev/null
  REBOOT=1
fi

sudo usermod -aG plugdev,audio,gpio "$USER"  # phones over USB, sound, button and light without root

python3 -m venv --system-site-packages .venv  # gpiozero comes from the system
.venv/bin/pip install -q -e .
mkdir -p ~/.nextstep-box && chmod 700 ~/.nextstep-box
[ -f ~/.nextstep-box/ai-gateway.key ] || echo "Note: put the box's key in ~/.nextstep-box/ai-gateway.key (chmod 600)."
[ -f helper/build/nextstep-box-helper.apk ] || echo "Note: copy helper/build/nextstep-box-helper.apk from the Mac."

sed "s|@USER@|$USER|; s|@DIR@|$PWD|g" pi/nextstep-box.service | sudo tee /etc/systemd/system/nextstep-box.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable -q nextstep-box
if [ -n "${REBOOT:-}" ]; then
  echo "Set up. Reboot once so the microphone and speaker appear:  sudo reboot"
else
  sudo systemctl restart nextstep-box
  echo "Set up and running. Its log:  journalctl -u nextstep-box -f"
fi
