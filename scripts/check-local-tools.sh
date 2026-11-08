#!/usr/bin/env bash
set -u

check_tool() {
  local label="$1"
  local command_name="$2"
  if command -v "$command_name" >/dev/null 2>&1; then
    printf '[FOUND] %-18s %s\n' "$label" "$(command -v "$command_name")"
  else
    printf '[MISSING] %-16s %s\n' "$label" "$command_name"
  fi
}

echo "REEL INTELLIGENCE local capability report"
check_tool "Python" "python3"
check_tool "Tesseract OCR" "tesseract"
check_tool "Poppler PDF text" "pdftotext"
check_tool "FFmpeg" "ffmpeg"
check_tool "FFprobe" "ffprobe"
check_tool "whisper.cpp CLI" "whisper-cli"

echo
echo "Model files are supplied by the operator; this script never downloads models."
echo "The Python package itself has no mandatory processor dependency."
