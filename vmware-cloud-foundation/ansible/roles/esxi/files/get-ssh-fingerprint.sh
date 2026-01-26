#!/bin/bash
set -e

if [ -z "$1" ]; then
  echo "ERROR: No target host provided" >&2
  exit 1
fi

target="$1"

# Collect ONLY RSA host key, output a single line
scan_output=$(ssh-keyscan -T 5 -t rsa "$target" 2>/dev/null || true)
if [ -z "$scan_output" ]; then
  echo "ERROR: ssh-keyscan (rsa) produced no output for $target" >&2
  exit 1
fi

# Extract just the base64 key data (third field)
key_data=$(echo "$scan_output" | grep -v '^#' | awk '{print $3}')

if [ -z "$key_data" ]; then
  echo "ERROR: Could not extract key data from ssh-keyscan output" >&2
  exit 1
fi

# Use Python to calculate SHA256 fingerprint (avoids ssh-keygen uid issues)
fp=$(python3 -c "
import base64
import hashlib
import sys

key_b64 = '$key_data'
try:
    key_bytes = base64.b64decode(key_b64)
    sha256_hash = hashlib.sha256(key_bytes).digest()
    fp = 'SHA256:' + base64.b64encode(sha256_hash).decode('ascii').rstrip('=')
    print(fp)
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)
")

if [ -z "$fp" ] || ! echo "$fp" | grep -q '^SHA256:' ; then
  echo "ERROR: Failed to derive RSA SHA256 fingerprint for $target" >&2
  exit 1
fi

echo "$fp"
