# Slurm extension — Ansible bundle

This directory is the root of the bundle zip (`slurm-vX.Y.Z.zip`). This README is excluded
from the zip.

## Playbooks and stages

| Stage | Playbook | What it does |
|---|---|---|
| onCreate postDeploy | `deploy.yaml` | full converge: preflight, node baseline (+ NVIDIA, one reboot), head services, compute nodes, slurm.conf, validation, outputs |
| onEdit preDeploy | `scale-in.yaml` | guards (head not resized, create-only inputs unchanged), drain/requeue/remove `slurmcompute_scale_in` nodes, outputs |
| onEdit postDeploy | `deploy.yaml` | same converge: adds new nodes (full treatment), reconciles existing nodes (no reboot/upgrade), validates new nodes inside a MAINT reservation |

`deploy.yaml` plays, in order:

1. `localhost`: banner (bundle version), cluster preflight (`roles/node/tasks/preflight-cluster.yaml`)
2. `slurmhead:slurmcompute`: reachability probe → group `slurm_up`; sudo-rs aware become probe
3. head: read state (`/etc/slurm-ext`: cluster.json, node registry, pending-validation list) — new/existing node sets are frozen here; Ubuntu-source opt-in gate (`source-gate.yaml`, skipped for clusters created with it)
4. `slurmhead:slurmcompute:&slurm_up`: role `node` (OS preflight, apt, upgrade new nodes, /etc/hosts, chrony, ufw, accounts, role `nvidia`, single reboot, Open MPI, Apptainer)
5. head: `slurm` `head.yaml` (secrets, MUNGE, NFS `/shared`, Slurm build/install, MySQL + slurmdbd, admin user, user tools, cluster.json)
6. compute: `slurm` `compute.yaml` (MUNGE key, `/shared` mount, packages, configless slurmd, user sync, SSH policy, raw facts)
7. head: `slurm` `controller.yaml` (pending list, registry merge, render + apply slurm.conf, sacctmgr, validation reservation)
8. compute: `slurm` `join.yaml` (MUNGE cross-check, start slurmd, wait for registration)
9. head: `slurm` `validate.yaml` (clears the pending list) + `collect-outputs.yaml`
10. `localhost`: `emit-outputs.yaml` (context.json, fail-closed)

## Inventory groups

The instance-array labels are `slurmhead` and `slurmcompute` — deliberately without hyphens:
controllers ≥ v7.4.4 rewrite `-` to `_` in inventory group names (the recordSet keeps the raw
label), so a hyphenated label would yield different group names on different controllers.
On edit the platform adds `slurmcompute_scale_out` / `slurmcompute_scale_in` (omitted when
empty; scale-in hosts are not in `slurmcompute`). The playbooks only use the globals
`sl_head_label` / `sl_compute_label` and the plays' `hosts:` patterns.

## Head-node state (`/etc/slurm-ext`, root 0700)

| Path | Content |
|---|---|
| `cluster.json` | cluster UUID, create-only input values, Slurm source/version (drift check) |
| `nodes.d/<inventory host>.json` | node registry: Slurm name, address, `slurmd -C` topology, RealMemory, GRES |
| `pending-validation.json` | scale-out nodes registered but not yet validated (re-validated by the next run) |
| `applied-conf.sha256` | digest of slurm/cgroup/gres.conf last applied and verified (forces `scontrol reconfigure` after an interrupted run) |
| `munge.key` | the cluster MUNGE key (source for every node's `/etc/munge/munge.key`) |
| `secrets/` | `db_password`, `admin_password` (initial), `cluster_uuid`, `admin_ssh_key` pair |
| `bootstrapped` | marker: the first deploy finished its validation |
| `last_uid` | highest uid handed out by `slurm-useradd` (uids are never reused) |

## Variables

- All derivations live in `roles/globals/defaults/main.yaml` (`sl_` prefix, never colliding with
  input/configVar/output labels). Every play lists `roles: [globals]` first.
- Inputs: `extensionInstanceVariables.<label>`; site config: `configVars.<label>`.
- Head-node state is published as facts on the head (`sl_cluster_state_fact`,
  `sl_registry_state`, `sl_outputs_fact`) and read everywhere through `hostvars`.

## Head-node helpers (`roles/slurm/files`, installed to `/usr/local/sbin`)

| Helper | Purpose |
|---|---|
| `slurm-ext-registry` | node registry (`/etc/slurm-ext/nodes.d`) dump/put/delete |
| `slurm-ext-build` | build `slurm-smd*` debs from the checksum-pinned SchedMD tarball |
| `slurm-ext-wait-nodes` | wait until nodes register with a valid configuration |
| `slurm-ext-drain` | drain → wait → requeue/cancel → DOWN (scale-in, admin maintenance); fails closed: exit 3 node in a reservation, 4 jobs did not leave, 5 slurmctld not answering |
| `slurm-useradd`, `slurm-userdel` | cluster user management |
| `slurm-usersync` | `--export` on the head, `--import` on compute nodes (timer) |

## Tests

```bash
cd ../tests
ansible-playbook -i inventory.yaml definition-spec.yaml render-spec.yaml
ansible-playbook -i inventory-scale.yaml render-spec-scale.yaml
ansible-playbook -i inventory-head-scale.yaml guard-spec.yaml
cd ../ansible && ansible-playbook --syntax-check -i ../tests/inventory.yaml deploy.yaml scale-in.yaml && ansible-lint
```
