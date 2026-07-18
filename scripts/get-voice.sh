#!/usr/bin/env bash
# Download a Piper voice model for tellme.
#
# Usage:
#   scripts/get-voice.sh [VOICE_NAME]
#
# VOICE_NAME defaults to en_US-lessac-medium. Models are fetched from the
# rhasspy/piper-voices repository on HuggingFace and placed in
# ${XDG_DATA_HOME:-$HOME/.local/share}/tellme/voices/.
#
# A voice consists of two files: <name>.onnx and <name>.onnx.json.
set -euo pipefail

VOICE="${1:-en_US-lessac-medium}"
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/tellme/voices"
BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main"

# Voice names look like: <lang>_<REGION>-<name>-<quality>
# HuggingFace path is:  <lang>/<lang>_<REGION>/<name>/<quality>/<full-name>.onnx
lang="${VOICE%%_*}"                 # en
locale="$(echo "$VOICE" | cut -d- -f1)"   # en_US
rest="${VOICE#*-}"                  # lessac-medium
name="${rest%%-*}"                  # lessac
quality="${rest#*-}"                # medium

url_dir="${BASE}/${lang}/${locale}/${name}/${quality}"

mkdir -p "$DEST"

download() {
    local file="$1"
    local url="${url_dir}/${file}"
    echo "Downloading ${file} ..."
    if command -v curl >/dev/null 2>&1; then
        curl -fL --retry 3 -o "${DEST}/${file}" "$url"
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "${DEST}/${file}" "$url"
    else
        echo "Error: need curl or wget to download voices." >&2
        exit 1
    fi
}

download "${VOICE}.onnx"
download "${VOICE}.onnx.json"

echo "Installed voice '${VOICE}' to ${DEST}"
