#!/bin/bash
# In-EE runner test: tests/runner-spec.yaml with the production bundle (x86 docker host).
#   tests/contract/run-runner.sh <image>     (from kubernetes-kubespray/)
set -euo pipefail
img=${1:?usage: run-runner.sh <image>}
root=$(cd "$(dirname "$0")/../.." && pwd)
docker run --rm --platform linux/amd64 --user 1000:0 -v "$root:/work:ro" "$img" /bin/bash -euo pipefail -c '
  mkdir -p /tmp/proj && cp -r /work/ansible/. /tmp/proj/ && cp /work/tests/runner-spec.yaml /tmp/proj/
  cd /tmp/proj
  ANSIBLE_CONFIG=/tmp/proj/ansible.cfg ansible-playbook -i /work/tests/inventory.yaml \
    -e @/work/tests/fixtures/sample-variables.json runner-spec.yaml 2>&1 \
    | grep -E "Kubespray .* \| (summary|start)|class=|RECAP|FATAL|RUNNER-SPEC|fatal|ERROR|failed=" | cut -c1-300'
