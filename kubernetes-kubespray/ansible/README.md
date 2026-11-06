# kubernetes-kubespray — Ansible bundle

Bundle root = zip root (`tools/package.sh`). This README is excluded from the zip.

## Entry points

| Playbook | Lifecycle task | Timeout | Does |
|---|---|---|---|
| `deploy.yaml` | onCreate postDeploy, onEdit postDeploy | 18000 / 46800 s | create, resume-create, worker scale-out, converge, upgrade, CP scale-out, or no-op; then MetalLB, admin identity, state commit, outputs |
| `edit-pre.yaml` | onEdit preDeploy | 14400 s | every guard of the edit; worker or CP scale-in while the leaving servers still exist; outputs |

The action is chosen from the state recorded on the control-plane nodes, never from the stage. A
failed or retried create therefore resumes as a create.

## Plays (deploy.yaml)

1. localhost: banner, static preflight (EE build info, inputs, site config, VIP/pool allocations)
2. `k8scp:k8sworker`: `wait_for_connection` → `k8s_up`, sudo probe (sudo-rs → sudo.ws)
3. `k8s_up`: node identity (cluster-id marker, CA hashes, kubeadm files), CP state copies
4. localhost: merge state (highest serial), cluster id, anchor CP
5. anchor: API + etcd snapshot (local apiserver/etcd, never the VIP)
6. localhost: plan + guards (`filter_plugins/k8s_ext.py: k8s_plan`), effective settings
7. `k8s_run`: node baseline (cloud-init, apt lock, ufw off, chrony, cluster-id), joiner hygiene
8. localhost: action (nested kubespray), verify
9. CPs: identity refresh, kube-vip renewal hook
10. anchor: MetalLB, admin identity
11. localhost: stale kube-vip restart, state commit
12. anchor: collect outputs; localhost: emit (fail-closed)

## Nested kubespray

`roles/kubespray`:
- `overlay.yaml` renders the overlay inventory into `/tmp/k8s-ks-<ident>/inventory`;
- `run.yaml` writes the run's extra-vars JSON and starts `files/ks-run.sh` async, then watches it with
  `watch-cycle.yaml` (one progress line per minute);
- `files/ks-summary.py` summarises the log: PLAY RECAP, failed/unreachable hosts, fatal lines.

`ks-run.sh` runs `/opt/kubespray/venv/bin/ansible-playbook` from `/opt/kubespray/src`:
- the environment is `env -i` plus an allowlist;
- it uses kubespray's own `ansible.cfg` with fail-fast ssh;
- inventory is `-i <platform inventory> -i <overlay>`;
- verbosity is 0.

Overlay:

| File | Content |
|---|---|
| `hosts.yaml` | `kube_control_plane` and `etcd` in the same explicit order (CP[0] first), `kube_node`, empty `calico_rr`, `k8s_cluster` |
| `host_vars/<h>.yml` | `ip`/`access_ip` (k8s-net IP), `kube_override_hostname`, `etcd_member_name` (recorded), `kube_vip_interface`, `node_labels`. On sudo.ws hosts also `ansible_become_exe` plus a LAZY `ansible_become_password: "{{ ansible_password }}"`; credentials are never copied. |
| `group_vars/all/00-base.yml` | Overridable defaults (containerd docker.io mirror, retention, …) |
| `group_vars/all/90-site-overrides.yml` | Recorded `site_kubespray_overrides` (denylist enforced) |
| `group_vars/all/zz-owned.yml` | Wrapper-owned: kube-vip/VIP endpoint, CNI, CIDRs, proxy mode, add-ons, paths |

`kube_version` is always passed explicitly. It is the deployed version, except in an upgrade, where it
is the target.

## State on the control-plane nodes

| Path | Content |
|---|---|
| `/etc/metalsoft-k8s/state.json` | Every CP. Whole-document writes, `serial` bumped, highest serial wins. Holds phase, cluster_id, kube_version, CP order + etcd member names + server instance ids, CA hashes, create-only snapshot, applied site settings and add-ons, generations, admin identity, pending lists, journal (`operation`), last etcd snapshot. |
| `/etc/metalsoft-k8s/cluster-id` | Every node, written before kubespray touches it |
| `/etc/metalsoft-k8s/admin/metalsoft-admin.kubeconfig` | Every CP, 0600 |
| `/etc/metalsoft-k8s/addons/metallb/` | Vendored manifest, kustomization, pool |
| `/var/backups/metalsoft-k8s/etcd-*.db` | etcd snapshots (anchor; retention = `site_backup_retention_count`) |

## Variables

Derived variables live in `roles/globals/defaults/main.yaml`, all `k8s_`-prefixed. Input labels are
unprefixed, configVars are `site_`, and the platform's `context` is never shadowed.

## Tests

From `kubernetes-kubespray/`:

```bash
python3 -I -m unittest discover -s tests -p 'test_*.py' -v                  # planner + definition contract
(cd tests && ANSIBLE_CONFIG=ansible.cfg ansible-playbook -i inventory.yaml \
   -e @fixtures/sample-variables.json render-spec.yaml)                        # overlay render
tests/contract/run-contract.sh registry.metalsoft.dev/ee/ee-kubernetes-kubespray:ks2.32.0-b1   # x86 docker host
(cd ansible && ansible-lint && ansible-playbook --syntax-check -i localhost, deploy.yaml edit-pre.yaml)
```
