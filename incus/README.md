# Incus

This directory contains the MetalSoft extension definition (application kind) and the Ansible playbooks used to deploy and manage [Incus](https://linuxcontainers.org/incus/docs/main/) on bare-metal infrastructure.

For details on MetalSoft extensions, see the official [documentation](https://docs.metalsoft.io/developer_resources/extensions/).

## Prerequisites

- A MetalSoft environment with bare-metal hosts prepared for Incus deployment.
  - At least one host is required for a basic Incus deployment.
  - Each host must have a healthy hardware status with no errors.
  - Each host must provide a minimum of two network interfaces.
- OS templates for Incus (see MetalSoft Ubuntu templates: <https://github.com/metalsoft-io/os-templates/tree/main/Ubuntu/24.04/incus-cluster-node>).
- A logical network profile labeled `incus-mgmt` at the target site.
- **Extension Site Config saved on every target site.** The extension declares `configVars`, so a deployment fails with "Extension not enabled on site" until an operator opens the extension's site config on each site and saves it (all config vars ship with defaults, so this is a one-click save unless overrides are needed).

## Configuration

Settings are split between site-level admin config and per-deployment inputs.

### Site config (`configVars` — set once per site by an operator)

| Variable | Type | Default | Description |
|---|---|---|---|
| `DNSResolvers` | String | `1.1.1.1` | Comma-separated DNS resolver IPs handed to every cluster node (systemd-resolved). |
| `branch_release` | String | `stable` | Zabbly package channel: `daily`, `stable` or `lts-6.0`. |
| `images_auto_update_interval` | Integer | `6` | Hours between cached image auto-updates ([docs](https://linuxcontainers.org/incus/docs/main/image-handling/#auto-update)). |
| `core_https_port` | Integer | `8443` | HTTPS port the Incus API listens on. |
| `separate_api_and_cluster_traffic` | Boolean | `false` | When true, cluster traffic uses a dedicated port (API port + 1) ([docs](https://linuxcontainers.org/incus/docs/main/howto/cluster_config_networks/#separate-rest-api-and-clustering-networks)). |
| `cluster_member_upgrade_enabled` | Boolean | `false` | When true, edit deployments apply OS/package upgrades to existing members one node at a time before scaling. Enable it before scaling out an aged cluster, or the new node's newer Incus version fails the join version check. |
| `cluster_member_force_remove_enabled` | Boolean | `false` | When true, scale-in force-removes a member that stays offline after evacuation. |
| `vars_debugging_enabled` | Boolean | `false` | Print the resolved extension variables during playbook runs. |

Note: these flags apply to every Incus deployment at the site. Values reach the playbooks as `configVars.<label>`.

### Per-deployment inputs

| Variable | Type | Default | Description |
|---|---|---|---|
| `cluster_server_type` | ServerType | — | Server type for the Incus cluster nodes. |
| `cluster_instance_count` | Integer | `1` | Number of nodes (1–50). Changing it on an existing deployment triggers scale-out/scale-in. |
| `cluster_node_os_template` | OsTemplate | — | OS template for the cluster nodes (Ubuntu). |
| `cluster_enabled` | Boolean | `true` | Deploy Incus in clustering mode. |
| `install_ui` | Boolean | `true` | Install the Incus web UI. |
| `storage_driver` | String | `dir` | Storage backend for the default pool: `dir`, `btrfs`, `lvm`, `lvmcluster`, `zfs`, `ceph`, `cephfs` or `cephobject`. |

## Outputs

Published after every successful deployment/edit and visible on the extension instance:

| Output | Description |
|---|---|
| `cluster_api_url` | `https://<first node FQDN>:<core_https_port>` |
| `cluster_ui_url` | Same as the API URL when `install_ui` is true, empty otherwise |
| `cluster_members` | Comma-separated FQDNs of the current cluster members |
| `cluster_member_count` | Number of cluster members |
| `cluster_storage_driver` | Storage driver of the default pool |
| `incus_release` | Zabbly channel the cluster tracks |

## Scaling

Edit the deployment's `cluster_instance_count`. The platform populates the `incus_scale_out` / `incus_scale_in` inventory groups and runs `scale.yaml` at both onEdit stages: scale-in nodes are evacuated and removed at preDeploy (while still reachable), scale-out nodes are installed and joined at postDeploy. When `cluster_member_upgrade_enabled` is true, `upgrade.yaml` upgrades the surviving members (serially) before the scale-out join.

## Tests

An offline render/contract harness lives in `tests/` — it validates the configVars fallback chains, both bootstrap-preseed template branches, the join preseed, and the full outputs payload without any infrastructure:

```bash
cd tests && ansible-playbook -i inventory.yaml render-spec.yaml
```

## Packaging

### Ansible bundle

Playbooks must sit at the archive root (no wrapper directory), and never ship a file named `job.yml` (reserved by the runner):

```bash
cd ansible
zip -r ../incus-v1.1.1.zip . -x '*.DS_Store' -x '*.zip' -x 'README.md'
unzip -l ../incus-v1.1.1.zip   # deploy.yaml, scale.yaml, upgrade.yaml, roles/ at top level
```

Upload to `https://repo.metalsoft.io/.extensions_ms/incus/incus-v1.1.1.zip` (the URL in `extension.json`). Bump the filename version on every change to dodge stale caching.

### Execution environment image

Every lifecycle task runs in the custom EE image declared as the `ee-incus-1-1-0` OciImage asset (wired via each task's `ee` option). The image must be `linux/amd64` — site controllers are x86_64. Note the `ubi10-minimal` base requires an x86-64-v3 CPU (AVX2, Haswell 2013+) on both the build host and the site controller (`grep -m1 -c avx2 /proc/cpuinfo` must print ≥1); a VM build host needs host CPU passthrough:

```bash
ansible-builder build \
  --file execution-environment.yml \
  --tag registry.metalsoft.dev/ee-incus:1.1.0 \
  --container-runtime docker \
  --extra-build-cli-args "--platform=linux/amd64" \
  --verbosity 3

docker image inspect registry.metalsoft.dev/ee-incus:1.1.0 --format '{{.Architecture}}'   # must print amd64

docker push registry.metalsoft.dev/ee-incus:1.1.0
docker save registry.metalsoft.dev/ee-incus:1.1.0 | gzip > ee-incus-1.1.0.tar.gz
# upload the tarball to https://repo.metalsoft.io/.extensions_ms/ee/ee-incus-1.1.0.tar.gz (the OciImage asset url in extension.json)
```

## Registration

```bash
metalcloud-cli extension create "Incus" application "Incus cluster lifecycle management" --definition-source extension.json
metalcloud-cli extension publish <id_or_label>
```

Published extensions cannot be updated in place — iterate in draft, or archive and recreate. After publishing, save the extension site config on every target site (see Prerequisites).

Details about the playbooks can be found in the [Ansible README](ansible/README.md).
