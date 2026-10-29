#!/bin/sh
# Cut a pet's generated photos out of their backgrounds and file them as its poses:
#   tools/ari-pet/import-art.sh [claude|ari] [FOLDER]
# Defaults: the golden from ~/Desktop/Claude Pet; ARI's hummingbird from ~/Desktop/ARI Pet.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
pet=${1:-claude}
case "$pet" in
  claude) default="$HOME/Desktop/Claude Pet" ;;
  ari) default="$HOME/Desktop/ARI Pet" ;;
  *) echo "usage: import-art.sh [claude|ari] [FOLDER]"; exit 2 ;;
esac
from=${2:-$default}
to="$here/art/$pet"
mkdir -p "$to"
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
