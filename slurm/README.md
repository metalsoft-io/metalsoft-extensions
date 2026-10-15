# Slurm HPC Cluster

MetalSoft **application** extension that deploys and manages a [Slurm](https://slurm.schedmd.com/overview.html)
workload-manager cluster on bare metal: one head node plus a scalable group of compute nodes
(CPU-only or NVIDIA GPU), on Ubuntu 26.04 LTS. Tenants self-serve the cluster from the catalog;
scaling the compute group out or in is an edit of the extension instance.

Extension docs: [docs.metalsoft.io](https://docs.metalsoft.io) → Developer Resources → Extensions.

## What gets deployed

```
                 tenant users (ssh)
                        │
        ┌───────────────▼────────────────┐        slurm-net (untagged, 1 NIC/server)
        │ head node  (slurmhead, 1)      │◄──────────────────────────────────────────┐
        │  slurmctld  scheduler          │                                           │
        │  slurmdbd + MySQL  accounting  │   configless: compute nodes fetch         │
        │  NFS server  /shared           │   slurm.conf from slurmctld               │
        │  login: sbatch / srun / sacct  │                                           │
        └───────────────┬────────────────┘                                           │
                        │ /shared (NFS)   munge auth                                 │
   ┌────────────────────┼─────────────────────┬────────────────────────┐             │
┌──▼───────────┐ ┌──────▼───────┐       ┌─────▼────────┐  compute nodes (slurmcompute, N)
│ slurmd       │ │ slurmd       │  ...  │ slurmd       │  NVIDIA driver on GPU servers
└──────────────┘ └──────────────┘       └──────────────┘  Open MPI, Apptainer
```

**Slurm in five minutes**

| Term | Meaning |
|---|---|
| `slurmctld` | the controller ("brain"): keeps the node list and the job queue, decides where jobs run |
| `slurmd` | agent on every compute node; starts the job processes |
| `slurmdbd` | accounting daemon in front of MySQL: job history (`sacct`), per-user/account limits, fair-share |
| MUNGE | shared-key authentication between all Slurm daemons (clocks must be in sync) |
| partition | a job queue = a set of nodes (here one, default name `compute`, with all nodes) |
| job / step | `sbatch script.sh` queues a job; each `srun` inside it is a step |
| GRES | generic resources — GPUs, requested with `--gpus=N` or `--gres=gpu:h100:N` |
| account / association | user ↔ account mapping in the accounting DB; jobs are only accepted for users that have one |

## Repository layout

| Path | Purpose |
|---|---|
| `extension.json` | the extension definition |
| `ansible/` | the Ansible bundle (zip root) — see [ansible/README.md](ansible/README.md) |
| `execution-environment.yml` | `ee-slurm` execution-environment image (ansible-builder v3) |
| `tests/` | offline definition/render/contract tests (no infrastructure needed) |

## Software

| Component | Version / source |
|---|---|
| OS | Ubuntu 26.04 LTS (`resolute`), x86_64 only |
| Slurm (default) | **SchedMD 26.05.4** built on the head node from the checksum-pinned release tarball into `slurm-smd*` packages (25.11.8 selectable) |
| Slurm (optional) | Ubuntu 26.04 archive `slurm-wlm` 25.11.2 — **has known unpatched CVEs**, needs the site admin opt-in |
| Accounting DB | MySQL 8.4 (Ubuntu main), local to the head node |
| MPI | Open MPI 5 (Ubuntu), PMIx 5 — `srun --mpi=pmix` |
| Containers | Apptainer (official Apptainer PPA, unprivileged) |
| NVIDIA | Ubuntu archive `-server-open` driver, **Canonical-signed prebuilt kernel modules** (no DKMS: works with Secure Boot), branch 580 (LTSB) or 595; Fabric Manager on NVSwitch systems |
| Ansible | `ee-slurm` image, ansible-core 2.21, builtin modules only |

## Prerequisites (per site)

1. **Logical network profile `slurm-net`** at the site (untagged, single NIC). Adapt
   `infrastructure.logicalNetworks[].profileLabel` in `extension.json` to use another name.
2. **OS template**: the **Ubuntu 26.04 LTS** template `ubuntu-26-04-lts-waitforssh`
   (`Ubuntu/26.04/oob-u26-04-lts-waitforssh` in MetalSoft's os-templates repository). Every node
   must use it — other OSes fail the preflight. It must reboot into the OS and use the
   `wait_for_ssh` ready method: the post-deploy playbook runs before the platform powers
   instances on, so the stock `ubuntu-26-04-lts` (power off + `wait_for_power_off`) leaves the
   servers off and the playbook fails with `No route to host`.
3. **Internet access** from the servers (Ubuntu archive, download.schedmd.com, Apptainer PPA;
   developer.download.nvidia.com only for HGX B200/B300).
4. **Extension site config saved on every site** — the extension has site-level settings
   (configVars, below). Until the site config is enabled and saved, deploys fail with
   *"Extension slurm not enabled on site &lt;id&gt;"*. All settings have defaults, so saving is one click:
   `echo '[{"label":"nvidia_driver_branch","value":"580"}]' | metalcloud-cli extension site-config set <ext> <site> --config-source pipe`
5. **`ee-slurm` image** reachable by the site controllers (see *Execution environment image*).
   The ubi10-minimal base needs an x86-64-v3 (AVX2) CPU on the site controller.
6. **Server types**: head node ≥ 16 GB RAM with enough local disk for `/shared` (home
   directories) — or use the external NFS input for bulk data. Instance DNS records stay enabled
   (the 26.04 template derives the host name from them).
7. **Controller** `release-v7.5` or newer (Enum inputs, per-task execution environments).

## Configuration

### Site config (configVars — set once per site by an operator)

| Variable | Type | Default | Description |
|---|---|---|---|
| `nvidia_driver_branch` | String | `580` | NVIDIA driver branch: `580` (long-term support, until 2028) or `595` |
| `nvidia_blackwell_hgx_enabled` | Boolean | `false` | allow HGX B200/B300 (NVLink5) nodes: adds NVIDIA's CUDA apt repo, pinned so only `nvlsm` comes from it, plus InfiniBand management tools. **Experimental** (not yet validated on hardware). Off: such nodes fail with a clear message |
| `allow_ubuntu_slurm_source` | Boolean | `false` | allow tenants to pick `slurm_source=ubuntu` (Ubuntu's Slurm 25.11.2 with known unpatched security issues) |

### Per-deployment inputs

| Input | Type | Default | Create-only | Description |
|---|---|---|---|---|
| `head_server_type` | ServerType | — | yes | head node (controller, DB, NFS, login); ≥ 16 GB RAM |
| `compute_server_type` | ServerType | — | yes | every compute node (CPU or GPU) |
| `compute_count` | Integer 1–128 | `2` | no | edit to scale out/in |
| `os_template` | OsTemplate | — | yes | **Ubuntu 26.04 LTS required** |
| `slurm_source` | Enum `upstream`/`ubuntu` | `upstream` | yes | see *Software* |
| `slurm_version` | Enum `26.05.4`/`25.11.8` | `26.05.4` | yes | SchedMD release (upstream only) |
| `cluster_name` | String | `slurm` | yes | Slurm ClusterName |
| `partition_name` | String | `compute` | yes | default partition (not `default`) |
| `admin_username` | String | `slurmadmin` | yes | cluster admin (sudo + Slurm administrator); not a system / OS-template user |
| `admin_ssh_public_key` | String | `""` | no | extra public key for the admin (a key pair is generated anyway) |
| `install_nvidia_driver` | Boolean | `true` | yes | install the NVIDIA driver on GPU nodes; off: GPUs are used only if the OS image already ships a working driver |
| `install_apptainer` | Boolean | `true` | yes | Apptainer on all nodes |
| `external_nfs_export` | String | `""` | yes | optional `host:/path` mounted at `/data` on all nodes |
| `scale_in_drain_timeout_minutes` | Integer 0–720 | `60` | no | scale-in: wait this long for jobs on removed nodes before requeue/cancel |

"Create-only" inputs are recorded at create; an edit that changes one fails at onEdit
preDeploy (before any server is touched) — revert it.

## Outputs

| Output | Description |
|---|---|
| `head_node_ip`, `head_node_hostname` | the head (login) node |
| `ssh_command` | `ssh <admin>@<head ip>` |
| `admin_user`, `admin_password` | cluster admin and its **initial** password (changing it later is not reflected) |
| `admin_ssh_private_key` | generated ed25519 private key of the admin (also its own key for `ssh <node>`) |
| `slurm_cluster_name`, `slurm_installed_version`, `default_partition` | Slurm facts |
| `compute_node_count`, `compute_nodes`, `gpu_total` | current compute nodes (Slurm names) and GPUs |
| `data_mount` | external NFS export mounted at `/data`, or empty |

**Security note**: `admin_password` and `admin_ssh_private_key` are declared `isPassword`
(masked by controllers that honour it); anyone who can read the extension instance
credentials can log in as the cluster admin. Rotate after handover: `passwd` and replace the
key in `~/.ssh/authorized_keys` (managed block: keep the block markers, add your own keys
outside it). If a deploy fails before the outputs are written: log in with the OS-template
user and `sudo cat /etc/slurm-ext/secrets/admin_password`.

## Deployment flow

`deploy.yaml` (onCreate postDeploy): preflight → reachability/become probe → node baseline
(full upgrade, NVIDIA driver, one reboot) → head services (MUNGE, NFS, Slurm build, MySQL,
slurmdbd, admin) → compute nodes → slurm.conf + slurmctld → slurmd → validation (srun on every
node, batch job, MPI over PMIx, GPU job, sacct) → outputs.

Typical first deploy: 30–60 min (the Slurm build on the head takes ~10–30 min, GPU servers
add a reboot with long POST times). `executionTimeout` is 5 h.

## GPU support

| Class | Status |
|---|---|
| PCIe GPUs (L40S, H100/H200 PCIe/NVL, RTX PRO 6000, A100 PCIe …) | supported |
| HGX A100 / H100 / H200 (NVSwitch) | supported — Fabric Manager + NSCQ from the Ubuntu archive, started before slurmd |
| HGX B200 / B300 (NVLink5) | **experimental**, needs the `nvidia_blackwell_hgx_enabled` site config |
| GB200/GB300 (arm64), pre-Turing (V100, P100) | not supported (preflight fails) |

GPUs are detected automatically. With `install_nvidia_driver=false` the extension neither
installs a driver nor blacklists nouveau: Slurm gets only the GPUs a driver already present in
the OS image exposes (none → the node is CPU-only). Slurm uses `AutoDetect=nvidia` (no NVML): GPU allocation is
accounted (`gres/gpu`), but MIG and per-job GPU utilisation metrics are not available in v1.
Node definitions carry a GPU type derived from the model name (`h100`, `a100`, `l40s`,
`rtx_pro_6000`, …): `srun --gpus=2 …` or `srun --gres=gpu:h100:2 …`.

## Scaling

- **Scale out** (raise `compute_count`): new servers get the full node baseline (upgrade,
  driver, one reboot), are added to slurm.conf with `scontrol reconfigure` (no daemon restarts),
  and are validated inside a short MAINT reservation so queued jobs cannot race the check.
  Existing nodes are only reconciled — never rebooted or upgraded. New nodes stay *pending
  validation* until the check passed: if the edit fails after they joined, the next edit (a
  no-op edit is enough) validates them again.
- **Scale in** (lower `compute_count`): MetalSoft chooses which servers leave. At onEdit
  preDeploy they are drained (no new jobs), running jobs get `scale_in_drain_timeout_minutes`
  to finish, then batch jobs that allow it are **requeued** (restart on other nodes) and the
  rest (interactive, `--no-requeue`) are **cancelled**; the nodes are removed from slurm.conf
  before the servers are released. A node in a tenant reservation blocks the scale-in
  (delete the reservation first; the extension's own `metalsoft-validate` hold is released
  automatically). slurmctld must be running — otherwise the scale-in stops before touching
  any node.
- The head node cannot be scaled; at least one compute node must remain.
- An unreachable **existing** node does not block an edit (it stays DOWN in Slurm); an
  unreachable **new** node fails the edit.

## Operating the cluster

- **Users** (on the head node):
  `sudo slurm-useradd [--account A] [--ssh-key "ssh-ed25519 …"] alice` (prints an initial
  password; compute nodes pick the user up within a minute, then the accounting association is
  created) · `sudo slurm-userdel [--cancel-jobs] [--remove-home] alice`. Uids are never
  handed to another user: a removed user's kept home stays theirs, and re-adding the same
  name restores its uid and home.
  Regular users log in to the head node; compute nodes refuse their SSH logins
  (`srun --jobid=<id> --overlap --pty bash` opens a shell inside a running job).
- **Site settings**: add partitions, limits, QOS references, etc. to `/etc/slurm/local.conf`
  (included at the end of slurm.conf, shipped to the nodes, never overwritten), then
  `sudo scontrol reconfigure`. Do not add a second `Default=YES` partition.
- **Patching** (kernel, NVIDIA driver and Slurm are excluded from unattended upgrades; everything
  else keeps receiving security updates): per node `sudo apt full-upgrade`, then
  `sudo scontrol reboot ASAP nextstate=RESUME <node>` — the node drains, reboots when idle and
  returns to service.
- **Node failure**: the node goes DOWN; batch jobs are requeued; once it registers again it
  returns to service automatically (`ReturnToService=2`).
- **Head node failure**: running jobs continue; new submissions and `/shared` I/O wait until the
  head is back. Re-imaging the head loses the cluster state — the next run refuses to continue
  (cluster-id guard); redeploy instead.
- **Repair**: a no-op edit re-runs the converge (reinstalls missing pieces, re-validates).
- **Backups** (manual in v1): `mysqldump --single-transaction slurm_acct_db`,
  `tar /etc/slurm /etc/slurm-ext /var/spool/slurmctld`, and `/shared/home`.
- **Logs**: `journalctl -u slurmctld|slurmd|slurmdbd|munge`, `/var/log/slurm/*.log`,
  Slurm build log `/var/lib/slurm-ext/build/build-<version>.log`.

## Tenant quick start (also shown at login on the head node)

```bash
ssh slurmadmin@<head_node_ip>                       # outputs: ssh_command / admin_password / key
sinfo                                               # nodes and partitions
cat > hello.sh <<'EOF'
#!/bin/bash
#SBATCH --nodes=2 --ntasks-per-node=1 --time=00:05:00
srun hostname
EOF
sbatch hello.sh && squeue -u $USER                  # queue a batch job
srun --pty bash                                     # interactive shell on a compute node
srun --gpus=1 nvidia-smi                            # GPU job
mpicc -o mpi_app mpi_app.c && srun --mpi=pmix -N2 ./mpi_app
srun --gpus=1 apptainer exec --nv docker://nvcr.io/nvidia/pytorch:25.10-py3 python -c 'import torch; print(torch.cuda.is_available())'
sacct                                               # job history
```

Storage: `/shared/home/$USER` (all nodes, on the head node), `/data` (external NFS, if
configured), `/tmp` (node-local). Jobs without `--time` run unlimited (`MaxTime=INFINITE`);
setting `--time` lets the backfill scheduler start them earlier.

## Not in v1

High availability, separate login nodes, InfiniBand/RoCE fabrics, NVIDIA enroot/pyxis,
slurmrestd, DCGM/NVML (MIG, GPU metrics), monitoring, LDAP/SSSD, pam_slurm_adopt, Lmod/CUDA
toolkit (use NGC containers), upgrades of the Slurm version of an existing cluster.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| deploy fails "Extension slurm not enabled on site" | save the extension site config on that site |
| preflight: `slurm_source=ubuntu … allow_ubuntu_slurm_source` | site admin opt-in missing (or use upstream) |
| node `INVAL` / drain reason `Low RealMemory` / `gres` count | hardware differs from the registered definition (e.g. a GPU lost); fix the node, `sudo scontrol update nodename=<n> state=resume` |
| `Munge decode failed` / unmunge fails | clock skew or different `/etc/munge/munge.key`; a no-op edit restores the key |
| user missing on a compute node | `systemctl status slurm-usersync.timer`; `/shared` must be mounted |
| NVIDIA: "signed modules not yet published" | a brand-new kernel; retry after Canonical publishes the modules |
| existing node "needs a reboot" warning | reboot it with `scontrol reboot ASAP nextstate=RESUME <node>` |
| scale-in fails "node(s) in a reservation" | delete/shrink the reservation, retry the edit |
| scale-in fails "slurmctld is not responding" | the head's slurmctld is down: `sudo systemctl status slurmctld`, `journalctl -u slurmctld`; fix it, retry the edit |
| scale-in fails "jobs still on … after cancellation" | jobs stuck completing: `squeue -w <nodes>`; once gone (or the node rebooted) retry the edit |
| `sinfo`/`squeue`: "Unable to contact slurm controller" | slurmctld down (see above); after a head reboot it starts on its own, compute nodes reconnect |
| slurmd: "Unable to determine this slurmd's NodeName" | the node is not (or no longer) in slurm.conf, e.g. removed outside a scale-in; a no-op edit re-registers servers that are still in the compute group |
| `slurm-useradd`: "home … exists and belongs to uid …" | `/shared/home/<name>` belongs to another account; move it away or pick another name |
| "These inputs cannot change after the cluster was created" | revert the create-only input in the edit |

## Tests

Offline (no infrastructure, ansible-core ≥ 2.20 locally):

```bash
cd tests
ansible-playbook -i inventory.yaml definition-spec.yaml render-spec.yaml
ansible-playbook -i inventory-scale.yaml render-spec-scale.yaml
ansible-playbook -i inventory-head-scale.yaml guard-spec.yaml
cd ../ansible
ansible-playbook --syntax-check -i ../tests/inventory.yaml deploy.yaml scale-in.yaml
ansible-lint
```

`definition-spec.yaml` checks extension.json against the extension contract (labels, regex
lengths and defaults, one label namespace, `ee` on every task, timeouts, version = bundle
name); the render specs check registry parsing, GPU naming, slurm.conf/gres.conf/cgroup.conf,
the /etc/hosts block, scale-in/out node sets, the pending-validation set, the cluster CIDR
from both recordSet subnet shapes, the Ubuntu-source gate, create-only drift detection and the
outputs payload against the declared output labels.

## Packaging

### Ansible bundle

```bash
cd ansible
zip -r ../slurm-v1.0.0.zip . -x '*.DS_Store' -x '*.zip' -x 'README.md'
unzip -l ../slurm-v1.0.0.zip | grep -E ' (deploy|scale-in)\.yaml$'   # playbooks at the zip root
unzip -p ../slurm-v1.0.0.zip roles/globals/defaults/main.yaml | grep sl_ext_version
```

Upload to `https://repo.metalsoft.io/.extensions_ms/slurm/slurm-v1.0.0.zip` (the AnsibleBundle
`url`). Bump `extensionVersion`, `sl_ext_version` and the zip name together on every change
(`tests/definition-spec.yaml` enforces it).

### Execution environment image

Build on an **x86_64 host**: the UBI 10 base requires an x86-64-v3 CPU, and amd64 emulation on
Apple Silicon (OrbStack / Docker Desktop / Rosetta) stops at the first `RUN` with
*"Fatal glibc error: CPU does not support x86-64-v3"*. Without ansible-builder on the build
host, generate the context anywhere (`ansible-builder create --file execution-environment.yml
--context <dir> --output-filename Dockerfile`) and run the `docker build` there.

```bash
ansible-builder build --file execution-environment.yml \
  --tag registry.metalsoft.dev/ee-slurm:1.0.0 --container-runtime docker \
  --extra-build-cli-args "--platform=linux/amd64 --provenance=false --sbom=false"
docker image inspect registry.metalsoft.dev/ee-slurm:1.0.0 --format '{{.Os}}/{{.Architecture}}'   # linux/amd64
docker run --rm registry.metalsoft.dev/ee-slurm:1.0.0 ansible --version   # core 2.21.5
docker push registry.metalsoft.dev/ee-slurm:1.0.0
docker save registry.metalsoft.dev/ee-slurm:1.0.0 | gzip > ee-slurm-1.0.0.tar.gz
```

`--provenance=false --sbom=false` keeps a single image manifest (no attestation manifest
list) — the same tarball layout the other MetalSoft EEs load from.

Upload the tarball to `https://repo.metalsoft.io/.extensions_ms/ee/ee-slurm-1.0.0.tar.gz`.
Site controllers cache EE images **by tag**: on every rebuild bump `tagRegistry` and the tarball
name in the OciImage asset.

## Registration

```bash
metalcloud-cli extension create "Slurm HPC Cluster" application \
  "Slurm HPC/AI cluster on bare metal" --definition-source extension.json
metalcloud-cli extension activate <id_or_label>      # 'publish' is deprecated in CLI 7.5
```

Published extensions cannot be updated in place — iterate as a draft, or bump the version.
