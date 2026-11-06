"""Write /opt/kubespray/BUILDINFO.json at EE build time.

Run with the kubespray venv interpreter (it ships PyYAML through ansible-core):
    /opt/kubespray/venv/bin/python -I buildinfo.py <kubespray tree> <out.json> key=value...

The kube version window is the set of versions present in the kubelet, kubeadm and
kubectl amd64 checksums of the pinned tree: kubespray can only install those. The
wrapper's preflight and the offline contract check compare the extension's
kube_version Enum against this list.
"""

import json
import os
import sys

import yaml


def _ver_key(v):
    return tuple(int(p) for p in v.split("."))


def main():
    tree, out = sys.argv[1], sys.argv[2]
    extra = dict(a.split("=", 1) for a in sys.argv[3:])
    path = os.path.join(tree, "roles/kubespray_defaults/vars/main/checksums.yml")
    with open(path, encoding="utf-8") as fh:
        sums = yaml.safe_load(fh)
    per_tool = [set(sums[f"{t}_checksums"]["amd64"]) for t in ("kubelet", "kubeadm", "kubectl")]
    common = sorted(set.intersection(*per_tool), key=_ver_key)
    latest = {}
    for v in common:
        latest[".".join(v.split(".")[:2])] = v
    info = dict(extra)
    info.update({
        # kubespray's default kube_version is the first kubelet amd64 key
        "kube_version_default": next(iter(sums["kubelet_checksums"]["amd64"])),
        "kube_versions": common,
        "kube_latest_per_minor": latest,
    })
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(info, fh, indent=2, sort_keys=True)
        fh.write("\n")


if __name__ == "__main__":
    main()
