#!/bin/bash
set -e

if [ -z "$1" ]; then
  echo "ERROR: No target host provided" >&2
  exit 1
fi

target="$1"

# Collect host keys. VCF hostSpec sshThumbprint is documented as an RSA SHA256 thumbprint,
# but hardened ESXi 9 hosts may no longer serve ssh-rsa host keys — scan all common types
# and prefer rsa when present.
scan_output=$(ssh-keyscan -T 5 -t rsa,ecdsa,ed25519 "$target" 2>/dev/null | grep -v '^#' || true)
if [ -z "$scan_output" ]; then
  echo "ERROR: ssh-keyscan produced no host keys for $target" >&2
  exit 1
fi

# Prefer the ssh-rsa key; otherwise fall back to the first key found.
key_line=$(printf '%s\n' "$scan_output" | awk '$2 == "ssh-rsa"' | head -n 1)
if [ -z "$key_line" ]; then
  key_line=$(printf '%s\n' "$scan_output" | head -n 1)
  key_type=$(printf '%s\n' "$key_line" | awk '{print $2}')
  echo "WARN: no ssh-rsa host key; using $key_type — if VCF host validation rejects it, set skip_esx_thumbprint_validation=true" >&2
fi

# Extract just the base64 key data (third field)
key_data=$(printf '%s\n' "$key_line" | awk '{print $3}')

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
