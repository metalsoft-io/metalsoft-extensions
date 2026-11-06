#!/bin/bash
# In-EE contract check. Run on an x86_64 docker host after tests/render-spec.yaml rendered
# tests/out/create:  tests/contract/run-contract.sh <image>   (from kubernetes-kubespray/)
set -euo pipefail
img=${1:?usage: run-contract.sh <image>}
root=$(cd "$(dirname "$0")/../.." && pwd)
docker run --rm --platform linux/amd64 --user 1000:0 -v "$root:/work:ro" "$img" /bin/bash -euo pipefail -c '
  jq() { python3 -c "import json,sys; print(json.load(open(sys.argv[2]))[sys.argv[1]])" "$@"; }
  test "$(jq kubespray_commit /opt/kubespray/BUILDINFO.json)" = 9751ea6f63244e433a7a6263d9ecf381e57bb8e9
  ansible --version | head -1 | grep -q "core 2.21.5"
  /opt/kubespray/venv/bin/ansible --version | head -1 | grep -q "core 2.19."
  python3 - <<PY
import json
b = json.load(open("/opt/kubespray/BUILDINFO.json"))
d = json.load(open("/work/extension.json"))
enum = [i for i in d["inputs"] if i["label"] == "kube_version"][0]["options"]["values"]
assert set(enum) <= set(b["kube_versions"]), (enum, "not in", b["kube_versions"])
assert enum == sorted(set(b["kube_latest_per_minor"][m] for m in ("1.35", "1.36")), reverse=True), enum
print("enum ok:", enum)
PY
  ks() { env -i PATH=/opt/kubespray/venv/bin:/usr/bin:/bin HOME=/tmp ANSIBLE_CONFIG=/opt/kubespray/src/ansible.cfg \
           ANSIBLE_CACHE_PLUGIN_CONNECTION=/tmp/facts ANSIBLE_LOCAL_TEMP=/tmp/ans ANSIBLE_STDOUT_CALLBACK=default \
           /opt/kubespray/venv/bin/ansible-playbook "$@"; }
  cd /opt/kubespray/src
  inv="-i /work/tests/inventory.yaml -i /work/tests/out/create/inventory"
  ks $inv -e @/work/tests/out/create/run-contract.json playbooks/boilerplate.yml | tail -4
  ks $inv -e @/work/tests/out/create/run-contract.json -e expect_file=/work/tests/out/create/expect.json \
     /work/tests/contract/hostvars-probe.yml | tail -8
  echo CONTRACT-OK'
