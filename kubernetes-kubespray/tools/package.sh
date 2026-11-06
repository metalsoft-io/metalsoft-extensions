#!/bin/bash
# Build the production bundle: playbooks at the zip ROOT, no README/tests, no macOS junk.
# Usage: tools/package.sh   (from kubernetes-kubespray/; version from extension.json)
set -euo pipefail
here=$(cd "$(dirname "$0")/.." && pwd)
version=$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["extensionVersion"])' "$here/extension.json")
grep -q "^k8s_ext_version: \"$version\"" "$here/ansible/roles/globals/defaults/main.yaml" \
  || { echo "k8s_ext_version in globals != extensionVersion $version" >&2; exit 1; }
zip_path="$here/kubernetes-kubespray-v${version}.zip"
rm -f "$zip_path"
(cd "$here/ansible" && zip -qr "$zip_path" . -x '*.DS_Store' -x '*.zip' -x 'README.md' -x '*__pycache__*')
unzip -l "$zip_path" | grep -E ' (deploy|edit-pre)\.yaml$'
unzip -p "$zip_path" roles/globals/defaults/main.yaml | grep '^k8s_ext_version'
shasum -a 256 "$zip_path"
