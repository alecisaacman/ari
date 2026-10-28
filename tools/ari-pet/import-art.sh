#!/bin/sh
# Cut the generated photos of Claude's golden out of their backgrounds and file them as
# the pet's poses: tools/ari-pet/import-art.sh [FOLDER]   (default: ~/Desktop/Claude Pet)
set -eu
here=$(cd "$(dirname "$0")" && pwd)
from=${1:-"$HOME/Desktop/Claude Pet"}
to="$here/art/claude"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
swiftc -O "$here/cutout.swift" -o "$work/cutout"
for pose in sit panting alert asleep sad lifted leap startled; do
  found=$(ls "$from/$pose".* 2>/dev/null | head -n 1 || true)
  if [ -z "$found" ]; then
    echo "missing: $pose"
    continue
  fi
  "$work/cutout" "$found" "$to/$pose.png"
done
