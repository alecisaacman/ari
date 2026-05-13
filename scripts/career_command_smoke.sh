#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${ARI_BIN:-}" ]]; then
  ari_cmd="${ARI_BIN}"
elif [[ -x "./.venv312/bin/ari" ]]; then
  ari_cmd="./.venv312/bin/ari"
elif [[ -x "./.venv/bin/ari" ]]; then
  ari_cmd="./.venv/bin/ari"
else
  ari_cmd="ari"
fi

"${ari_cmd}" career status
"${ari_cmd}" career pending
"${ari_cmd}" career next
"${ari_cmd}" career tracker
"${ari_cmd}" career reports
"${ari_cmd}" career command-center
"${ari_cmd}" career command-center --json
