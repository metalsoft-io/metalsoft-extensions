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
| `branch_release` | String | `stable` | Zabbly package channel: `daily`, `stable` or `lts-6.0`. Selects the repository while `incus_repository_url` is empty (the default); always names the source file (`zabbly-incus-<branch>.sources`) and the `incus_release` output. Must match the channel that `incus_repository_url` names, if it names one (`/zabbly-incus-<channel>/` or `/incus/<channel>/`; MetalSoft's snapshots name `stable`): the deploy stops otherwise. |
| `incus_repository_url` | String | empty | APT repository Incus is installed from. Empty (the default): Zabbly upstream, `https://pkgs.zabbly.com/incus/<branch_release>/`. Set it to install from a mirror instead, for example MetalSoft's snapshot (see "Package repository"). |
| `images_auto_update_interval` | Integer | `6` | Hours between cached image auto-updates ([docs](https://linuxcontainers.org/incus/docs/main/image-handling/#auto-update)). |
| `core_https_port` | Integer | `8443` | HTTPS port the Incus API listens on. |
| `separate_api_and_cluster_traffic` | Boolean | `false` | When true, cluster traffic uses a dedicated port (API port + 1) ([docs](https://linuxcontainers.org/incus/docs/main/howto/cluster_config_networks/#separate-rest-api-and-clustering-networks)). |
| `cluster_member_upgrade_enabled` | Boolean | `false` | When true, edit deployments apply OS/package upgrades to existing members one node at a time before scaling. It does not bring a multi-member cluster to a newer Incus minor release (an upgraded member stops serving its API until every member runs that release, so the one-at-a-time upgrade fails at the first member), and it does not change a member's package source (see "Package repository"). |
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
| `incus_release` | Zabbly channel (`branch_release`); with a snapshot in `incus_repository_url`, Incus stays at that snapshot's version |
| `browser_client_certificate` | PEM user (browser) client certificate trusted by the cluster |
| `browser_client_certificate_key` | PEM private key for the browser certificate (see security note below) |

## Browser access to the Incus UI (client certificate)

Each deployment generates a dedicated user client certificate on the first cluster
member (EC secp384r1, self-signed, valid 10 years, CN `<instance name>-browser-user`)
and registers it in the cluster-wide trust store. The PEM certificate and private key
are published as the `browser_client_certificate` / `browser_client_certificate_key`
outputs so a person can authenticate to the Incus web UI (`cluster_ui_url`).

1. Copy the two output values into local files, keeping the `BEGIN`/`END` lines and
   line breaks intact: `browser-client.crt` and `browser-client.key`.
2. Convert the pair to a PKCS#12 bundle (choose an export password — Firefox asks for
   it at import):

   ```bash
   openssl pkcs12 -export \
     -in browser-client.crt \
     -inkey browser-client.key \
     -name "incus-browser-user" \
     -out incus-browser-user.p12
   ```

   OpenSSL 3 encrypts the bundle with AES-256/PBKDF2, which Firefox 91+ imports fine;
   if an older browser rejects the file, re-run with the additional `-legacy` flag.
3. Import into Firefox: Settings → Privacy & Security → Certificates → View
   Certificates… → Your Certificates → Import… → select `incus-browser-user.p12` and
   enter the export password.
4. Open the `cluster_ui_url` output. Accept the self-signed *server* certificate
   warning first, then select the imported certificate when Firefox prompts for a
   client certificate (restart Firefox if no prompt appears — it caches a "no
   certificate" choice per host). The UI logs you in as a trusted client.

**Security note:** the private key is published as a plaintext extension output —
anyone who can view this extension instance in MetalSoft can read it, and the
certificate grants full, unrestricted admin access to the Incus API and UI. Restrict
instance visibility accordingly. To revoke: `incus config trust list` on any member,
then `incus config trust remove <fingerprint>` and delete
`/var/lib/incus/user-certs/` on the first member.

## Scaling

Edit the deployment's `cluster_instance_count`. The platform populates the `incus_scale_out` / `incus_scale_in` inventory groups and runs `scale.yaml` at both onEdit stages: scale-in nodes are evacuated and removed at preDeploy (while still reachable), scale-out nodes are installed and joined at postDeploy. When `cluster_member_upgrade_enabled` is true, `upgrade.yaml` upgrades the surviving members (serially) before the scale-out join.

## Package repository

By default Incus comes from Zabbly upstream, `https://pkgs.zabbly.com/incus/<branch_release>/`
(site setting `incus_repository_url` left empty). Zabbly keeps only its newest builds, so nodes
deployed at different times can get different Incus versions, and a node whose Incus minor release
differs from the cluster's cannot join it: once Zabbly has moved on, scaling out an older cluster
fails at the join version check. Then set `incus_repository_url` to a snapshot that has the
cluster's version, if one exists, or upgrade every member together by hand first.

To install from another repository, set `incus_repository_url`:

- MetalSoft's dated snapshot of Zabbly stable,
  `https://repo.metalsoft.io/.apt-mirrors/zabbly-incus-stable/20261120/` (Incus 7.6, with every
  suite Zabbly stable publishes for amd64 and arm64: Ubuntu 22.04, 24.04 and 26.04, Debian 12 and
  13). A snapshot is a byte-for-byte copy of upstream on one date, with Zabbly's own signed release
  files, so the bundled `zabbly.asc` verifies it unchanged, and every node deployed with the same
  setting gets the same Incus version. Keep `branch_release` at `stable` with it.
- A mirror at the site: any URL that serves the same layout (`dists/`, `pool/`) with Zabbly's
  signatures, such as a byte-for-byte copy. A mirror that re-signs with its own key does not work:
  the source always uses the bundled `zabbly.asc`.

A changed setting applies to nodes installed after the change (new deployments and scale-out).
`upgrade.yaml` (`cluster_member_upgrade_enabled`) does not rewrite the source file, so it upgrades
a member only as far as the repository that member was installed from.

Before it changes anything on a node, the deploy and scale-out check the setting: it must be one
`http://` or `https://` URL, and a channel the URL names (`/zabbly-incus-<channel>/` or
`/incus/<channel>/`) must equal `branch_release`.

The GB200 OS template (`os-templates`: `Ubuntu/24.04/incus-gb200-nvidia`) installs and holds Incus
from the snapshot before the extension runs. On sites with those hosts, set `incus_repository_url`
to the template's `INCUS_REPO_URL`: the extension rewrites the same source file
(`/etc/apt/sources.list.d/zabbly-incus-stable.sources`). Left empty, those hosts keep the Incus
they were installed with (held; from template 1.4.2 also its web UI), but their source points at
upstream: they then also need `pkgs.zabbly.com`, and nothing refuses a `branch_release` other than
`stable`. The setting applies to every Incus deployment at the site. The template's `README.md`
explains how the snapshots are made.

### Mirroring Zabbly to your own repository server

A mirror for `incus_repository_url` must:

- keep Zabbly's signed release files unchanged (the source always verifies with the bundled
  `zabbly.asc`), so tools that re-sign with their own key, such as aptly or reprepro, do not work;
- keep the `dists/` and `pool/` layout, and be served over HTTP or HTTPS by any web server;
- hold every Ubuntu release and architecture your nodes use. Zabbly stable publishes jammy, noble
  and resolute (plus bookworm and trixie for Debian), for amd64 and arm64.

Two tools that do this:

- `mirror-apt-snapshot.py` (python3 and gpgv only), in the os-templates repository under
  `Ubuntu/24.04/incus-gb200-nvidia/`; MetalSoft's snapshots are made with it. It makes a dated,
  read-only copy: it checks the signature before anything else and every file's SHA256, and
  publishes the directory only when everything checked out. `zabbly.asc` is
  `ansible/roles/incus/files/zabbly.asc` in this extension.

  ```bash
  ./mirror-apt-snapshot.py --url https://pkgs.zabbly.com/incus/stable/ \
      --suite jammy --suite noble --suite resolute --arch amd64 --arch arm64 \
      --key zabbly.asc --dest /var/www/apt/zabbly-incus-stable/20261201
  ```

  Then set `incus_repository_url` to `https://<server>/apt/zabbly-incus-stable/20261201/`. To get
  exactly the Incus that MetalSoft's snapshot holds, use that snapshot as `--url`
  (`https://repo.metalsoft.io/.apt-mirrors/zabbly-incus-stable/20261120/`). Repeat with a new
  `--dest` date for a newer copy; a finished copy is never changed.

- `debmirror` (Debian/Ubuntu package) also keeps Zabbly's release files and checks them, but
  updates one directory in place:

  ```bash
  gpg --dearmor -o zabbly.gpg zabbly.asc
  debmirror --method=https --host=pkgs.zabbly.com --root=incus/stable \
      --dist=jammy,noble,resolute --section=main --arch=amd64,arm64 --nosource \
      --keyring=zabbly.gpg --rsync-extra=none --diff=none /var/www/apt/zabbly-incus-stable
  ```

A copy that is updated in place, such as debmirror run on a timer, behaves like upstream: nodes
installed at different times can get different Incus versions. With dated copies, the version
changes only when `incus_repository_url` is pointed at a newer one, and the old directory must stay
while clusters built from it may still scale out.

## Tests

An offline render/contract harness lives in `tests/` — it validates the configVars fallback chains, the Incus package source and the repository checks, both bootstrap-preseed template branches, the join preseed, and the full outputs payload without any infrastructure:

```bash
cd tests && ansible-playbook -i inventory.yaml render-spec.yaml
```

## Packaging

### Ansible bundle

Playbooks must sit at the archive root (no wrapper directory), and never ship a file named `job.yml` (reserved by the runner):

```bash
cd ansible
zip -r ../incus-v1.1.5.zip . -x '*.DS_Store' -x '*.zip' -x 'README.md'
unzip -l ../incus-v1.1.5.zip   # deploy.yaml, scale.yaml, upgrade.yaml, roles/ at top level
```

Upload to `https://repo.metalsoft.io/.extensions_ms/incus/incus-v1.1.5.zip` (the URL in `extension.json`). Bump the filename version on every change to dodge stale caching.

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
