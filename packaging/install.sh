#!/usr/bin/env bash
# Install tellme on Ubuntu: system deps, the Python package, a default voice,
# and a systemd user service that starts it at login.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VOICE="${TELLME_VOICE:-en_US-lessac-medium}"

echo "==> Installing system dependencies (requires sudo)"
sudo apt-get update
sudo apt-get install -y \
    python3-gi \
    gir1.2-ayatanaappindicator3-0.1 \
    gir1.2-edataserver-1.2 \
    gir1.2-ecal-2.0 \
    pulseaudio-utils \
    pipx

echo "==> Installing the tellme Python package (isolated pipx venv)"
# Ubuntu marks the system Python "externally managed" (PEP 668), so a plain
# `pip install --user` refuses to run. pipx gives us an isolated venv while
# --system-site-packages keeps the apt-installed GTK/AppIndicator bindings
# above importable; it drops the entry point at ~/.local/bin/tellme, which
# is what tellme.service's ExecStart expects.
pipx ensurepath
pipx install --system-site-packages --force "${REPO_ROOT}"

echo "==> Downloading voice model: ${VOICE}"
"${REPO_ROOT}/scripts/get-voice.sh" "${VOICE}"

echo "==> Installing systemd user service"
mkdir -p "${HOME}/.config/systemd/user"
install -m 0644 "${REPO_ROOT}/packaging/tellme.service" \
    "${HOME}/.config/systemd/user/tellme.service"

systemctl --user daemon-reload
systemctl --user enable --now tellme.service

echo
echo "tellme is installed and running."
echo "  Status:  systemctl --user status tellme"
echo "  Logs:    journalctl --user -u tellme -f"
echo "  Test:    tellme --speak-now"
echo
echo "Tip: to also announce Google events, add your Google account under"
echo "     Settings → Online Accounts (with Calendar enabled)."
