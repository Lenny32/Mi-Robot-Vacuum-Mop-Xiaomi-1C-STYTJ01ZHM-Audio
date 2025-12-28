#!/usr/bin/env bash
set -e

OUT_DIR="out_audio"
ARCHIVE="voice.tar.gz"

cd "$OUT_DIR"
tar -czf "../$ARCHIVE" *.ogg
cd - >/dev/null

md5sum "$ARCHIVE"
