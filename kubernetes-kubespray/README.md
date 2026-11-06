# kubernetes-kubespray — MetalSoft extension

Vanilla upstream Kubernetes on Ubuntu 26.04 bare metal, deployed and operated by wrapping
[kubespray](https://github.com/kubernetes-sigs/kubespray) (pinned release tag `v2.32.0`):

- **Control plane:** 1, 3 or 5 nodes, with stacked etcd.
- **Workers:** 1–100, scalable in place.
- **API endpoint:** a kube-vip VIP in ARP mode.
- **LoadBalancer Services:** IPs from MetalLB (L2).
- **Storage:** local-path is the default StorageClass.
- **Admin access:** a revocable admin kubeconfig, delivered as an output.

## What gets deployed

| Component | Version / source | Notes |
|---|---|---|
| Kubernetes | `1.36.4` (default) or `1.35.8` | The latest patch of each minor in the tag's checksums |
| kubespray | `v2.32.0` (`9751ea6f`) plus backport #13580 | Run nested from the execution environment |
| Container runtime | containerd (kubespray default) | docker.io is pulled through `mirror.gcr.io` first |
| etcd | stacked, on the control-plane nodes (`etcd_deployment_type: host`) | Odd member count only |
| CNI | Calico, VXLAN | Pod / service CIDRs are create-only inputs |
| kube-proxy | iptables (default) or nftables (experimental) | Create-only |
| API VIP | kube-vip v1.0.3, ARP, on every control-plane node | Platform `api-vip` allocation |
| LoadBalancer | MetalLB v0.16.1 (upstream manifest, images pinned by digest), L2 | Platform `lb-pool` ipRange (4 requested; the platform reserves 5) |
| DNS | CoreDNS + nodelocaldns | Upstream servers: site config, or the nodes' resolvers |
| Storage | local-path-provisioner 0.0.37, default StorageClass | Node-local disk, no replication; data is lost when its node is removed |
| Add-ons | metrics-server (on), Gateway API CRDs (off) | Add-only toggles |
| Secrets | encrypted at rest (secretbox), on from create | — |

## Prerequisites per site

- **Logical network profile.** The extension's `profileLabel` (default `k8s-net`) must provide one untagged L2 network with a default gateway and internet egress, sized
  for the nodes + 1 VIP + 5 LoadBalancer IPs. If the profile hands every infrastructure the same
  VLAN, only **one** infrastructure can use it at a time; the infrastructure designer shows the
  error for a second one ("VLAN … is not available").
- **OS template.** `ubuntu-26-04-lts-waitforssh`, which reboots and waits for SSH before the postDeploy
  tasks run.
- **Site config.** The extension's site config saved on the site, even with all defaults; without it
  application deploys fail with "not enabled on site".
- **Egress from the nodes:**
  - `github.com`, `objects.githubusercontent.com`, `raw.githubusercontent.com`;
  - `dl.k8s.io`, `registry.k8s.io`, `quay.io`, `ghcr.io`, `mirror.gcr.io`, `registry-1.docker.io`;
  - the Ubuntu archive.
- **DNS provisioning extension: optional.** Without it, everything runs on IPs and `api_url` is the
  VIP. With it, `api.<instance>.<zone>` is used when it resolves to the VIP.

## Configuration

### Inputs (tenant)

| Input | Default | Rule |
|---|---|---|
| `control_plane_server_type`, `worker_server_type`, `os_template` | – | Fixed after create |
| `control_plane_count` | 1 | 1, 3 or 5. Change by exactly 2; only a worker increase may share its edit |
| `worker_count` | 1 | 1–100. Combinable with converge |
| `kube_version` | 1.36.4 | Upgrade one minor at a time, never down, alone in its edit |
| `kube_proxy_mode` | iptables | iptables or nftables. Fixed after create |
| `pod_network_cidr` / `service_network_cidr` / `cluster_dns_domain` | 10.233.64.0/18 / 10.233.0.0/18 / cluster.local | Fixed after create |
| `metrics_server_enabled` / `local_path_provisioner_enabled` / `gateway_api_crds_enabled` / `metallb_enabled` | on / on / off / on | Add-only: switching one off is refused |
| `drain_timeout_minutes` | 10 | 1–30, per node, for scale-in and upgrades |
| `drain_policy` | respect-pdb | `force-after-timeout` evicts anyway after the timeout |
| `converge_generation` | 0 | Raise it to re-run the full kubespray converge and apply new site settings |
| `admin_credential_generation` | 1 | Raise it to rotate the admin kubeconfig |

### Site config (configVars, all with defaults)

| configVar | Default | Effect |
|---|---|---|
| `site_kubespray_overrides` | empty | Extra kubespray group_vars (YAML/JSON, or base64 of either). Extension-managed keys are rejected; create-only keys apply only at create. Takes effect on create or a `converge_generation` bump. |
| `site_dns_servers` | empty | Upstream DNS for CoreDNS (≤3). Empty means the nodes' resolvers. |
| `site_ntp_servers` | empty | chrony sources. Empty means the site NTP servers from the record set, else Ubuntu's defaults. |
| `site_admin_cert_validity_days` | 365 | Validity of the admin client certificate |
| `site_auto_renew_certificates` | true | kubespray monthly control-plane certificate renewal |
| `site_backup_retention_count` | 5 | etcd snapshots and kubeadm backups kept on the nodes |
| `site_ansible_forks` | 50 | Parallelism of the nested kubespray runs |

Site settings are recorded on the cluster when they are applied. Later edits keep the recorded settings, so
new nodes match old ones, until `converge_generation` is raised.

## Outputs

| Output | Content |
|---|---|
| `api_url` | `https://<api fqdn or VIP>:6443` |
| `api_vip`, `api_fqdn` | VIP; fqdn only when it resolves to the VIP |
| `admin_kubeconfig` | isPassword. kubeconfig of `metalsoft-admin-g<N>` (group `metalsoft:cluster-admin:g<N>`) |
| `admin_kubeconfig_expires`, `admin_credential` | Certificate expiry; identity and its revoke command |
| `ca_cert` | Cluster CA (PEM) |
| `kubernetes_version`, `kubespray_version` | Running version; kubespray tag/commit and EE tag |
| `control_plane_nodes`, `worker_nodes` | Node names |
| `lb_pool_ranges` | MetalLB address range(s) |
| `cluster_id`, `cluster_status`, `etcd_last_snapshot` | Health summary of the last run |

Every run re-emits every output; a run that cannot produce complete outputs fails instead.

## Lifecycle

| Edit | preDeploy (`edit-pre.yaml`) | postDeploy (`deploy.yaml`) |
|---|---|---|
| create | – | `cluster.yml`, MetalLB, admin identity |
| `worker_count` up | guards | `facts.yml` + `scale.yml --limit <new>` |
| `worker_count` down | cordon all leavers, bounded drains (unreachable leavers: out-of-service taint instead of a drain), `remove_node.yml` (no reset), quiesce | verify |
| `converge_generation` up / add-on on | guards | `cluster.yml` at the running version |
| `kube_version` up one minor | version + health guards | etcd snapshot, `upgrade_cluster.yml` (CPs serial, workers in ≤5 batches), uncordon fix |
| `control_plane_count` +2 (optionally with `worker_count` up) | guards | snapshot, `cluster.yml --limit etcd:kube_control_plane[:<new workers>]`, same-version CP refresh (`skip_downloads`), commit |
| `control_plane_count` −2 | kube-vip moved off leavers, drain (unreachable leavers: out-of-service taint), `etcdctl member remove` (unreachable first, back-to-back), survivors refreshed | verify |
| nothing structural | guards | health, admin identity renew/rotate, outputs |

The platform runs onEdit only when an input changes. **Refused edits** fail at preDeploy, before
any server changes, with an `E-K8S-NNN` message, for example:
- a create-only input changed;
- the version stepped by more than one minor, or downgraded;
- control-plane or version changes combined with anything else (except a worker increase together with a
  control-plane increase);
- an add-on switched off;
- a generation lowered;
- the last schedulable worker removed.

State lives on the control-plane nodes (`/etc/metalsoft-k8s/state.json`, see `ansible/README.md`).
Retries resume from it.

## Operating

- **Revoke the admin kubeconfig:** `kubectl delete clusterrolebinding metalsoft-admin-g<N>`. That generation
  is never re-bound. The next edit (for example raising `admin_credential_generation`) issues g<N+1>.
- **Lost etcd quorum:** stop etcd on the surviving member and restore the newest
  `/var/backups/metalsoft-k8s/etcd-*.db` with `etcdutl snapshot restore` as a single member, or use
  kubespray `recover-control-plane.yml` (see the kubespray docs).
- **Replacing a dead node:** the platform chooses which server leaves on a count decrease. A specific
  dead node needs operator work.

## Known platform behaviour

- `ipRanges[].ipCount` cannot reference an input, so the MetalLB pool size is fixed.
- Draft extensions cannot be instantiated; test with an active version.
- **Never skip a failed preDeploy task of a scale-in.** The platform then removes the servers without
  the extension's preparation: for control planes that loses etcd quorum. Fix the cause instead.
- **Scale-in deploys need `allowDataLoss: true`**; otherwise the platform refuses the deploy before
  any task runs.
- **Bundles are cached by URL.** Never replace a zip under the same name; ship a new version.
- A refused edit (E-K8S-NNN) leaves the deploy blocked. Skip the refused tasks (only when no servers
  change), set the input back and deploy again.

## Test coverage

Tested live: create (1 + 1, 3 + 2, without DNS integration), edits that change nothing structural,
workers up and down, control planes 1 → 3, 3 → 1 and 3 → 5 → 3, control planes and workers up in
one edit, removing a powered-off worker and a powered-off control plane (etcd quorum kept), upgrade
1.35 → 1.36, refused downgrade and refused even control-plane counts, converge, admin credential
rotation and revocation, API VIP and MetalLB failover.

Not yet tested live (covered only by the offline tests and the design guards):
- a retry halfway through a create, an upgrade or a control-plane scale-out;
- an upgrade whose drain is blocked by a PodDisruptionBudget;
- certificate renewal, secrets encryption at rest, `site_kubespray_overrides`, switching an add-on on.

## Repository layout

| Path | Purpose |
|---|---|
| `extension.json` | Definition, regenerated by `tools/write-extension-json.py` |
| `execution-environment.yml`, `ee/` | EE build: kubespray tag, backports, `buildinfo.py` |
| `ansible/` | Bundle (zip root); see [ansible/README.md](ansible/README.md) |
| `tools/package.sh` | Builds `kubernetes-kubespray-v<version>.zip` |

## Tests

```bash
python3 -m unittest discover -s tests -p 'test_*.py'          # planner and definition checks
(cd tests && ANSIBLE_CONFIG=ansible.cfg ansible-playbook -i inventory.yaml \
   -e @fixtures/sample-variables.json render-spec.yaml)        # offline render of the kubespray inventory
(cd ansible && ansible-playbook --syntax-check -i localhost, deploy.yaml edit-pre.yaml)
tests/contract/run-contract.sh <ee-image>                      # in-EE check, on an x86_64 docker host
```

Live tests on a site: [tests/e2e/README.md](tests/e2e/README.md); results in
[tests/e2e/RESULTS.md](tests/e2e/RESULTS.md).

## Packaging and registration

```bash
tools/package.sh   # builds kubernetes-kubespray-v<version>.zip
# upload the zip to https://repo.metalsoft.io/.extensions_ms/kubernetes-kubespray/

export METALCLOUD_ENDPOINT=https://<controller> METALCLOUD_API_KEY=<api key>

# register (starts as a draft), then activate
metalcloud-cli extension create kubernetes-kubespray application \
  "Vanilla upstream Kubernetes via kubespray" --definition-source extension.json
metalcloud-cli extension activate <extension id>

# enable it on each site: every configVar has a default, so save the defaults (or edit them first)
jq '[.configVars[] | {label, value: .defaultValue}]' extension.json \
  | metalcloud-cli extension site-config set <extension id> <site id or label> --config-source pipe
```

The extension needs a v7.5.0 controller or later.


Bump `extensionVersion` (`tools/write-extension-json.py`), `k8s_ext_version` (globals) and the zip name
together.

## Execution environment image

`registry.metalsoft.dev/ee/ee-kubernetes-kubespray:ks2.32.0-b1`. The tag is `ks<kubespray tag>-b<build>`,
independent of the extension version. Tags are immutable: on every rebuild, bump `-bN` in
`EE_TAG`, in the OciImage `tagRegistry` and in the tarball name. Site controllers cache images
by tag.

The image contains two Ansible installs that never mix. The wrapper bundle runs on the system
Python (core 2.21; the 26.04 nodes need ≥ 2.20). kubespray runs **nested** from
`/opt/kubespray/src` with its own venv and `ansible.cfg` (kubespray hard-requires
2.19.0 ≤ core < 2.20.0).

Build on an **x86_64 host**. UBI 10 needs x86-64-v3, which Apple Silicon amd64 emulation lacks.

```bash
# on the Mac
ansible-builder create --file execution-environment.yml --context /tmp/ee-ctx --output-filename Dockerfile
COPYFILE_DISABLE=1 tar -C /tmp/ee-ctx -cf - . | ssh <build-host> 'mkdir -p ee-ctx && tar -xf - -C ee-ctx'
# on the build host
cd ee-ctx && docker build --platform=linux/amd64 --provenance=false --sbom=false \
  -t registry.metalsoft.dev/ee/ee-kubernetes-kubespray:ks2.32.0-b1 .
docker run --rm registry.metalsoft.dev/ee/ee-kubernetes-kubespray:ks2.32.0-b1 cat /opt/kubespray/BUILDINFO.json
docker save registry.metalsoft.dev/ee/ee-kubernetes-kubespray:ks2.32.0-b1 | gzip > ee-kubernetes-kubespray-ks2.32.0-b1.tar.gz
# push from a host with registry credentials (the Mac): docker load -i <tarball>; docker push <ref>
```

The build fails closed if:
- the kubespray archive's sha256 doesn't match;
- a backport no longer applies;
- the venv isn't on core 2.19;
- any entry playbook fails `--syntax-check`.

The OciImage asset uses `namespaceRegistry: "ee"`,
`repositoryRegistry: "ee-kubernetes-kubespray"` and `tagRegistry: "ks2.32.0-b1"`. The site agent loads the
tarball from the asset `url` first and pulls only if that fails.

Build `ks2.32.0-b1` (2026-10-27): 1.09 GB unpacked, tarball 208 MB, sha256
`2d32694b03f3607ee4251f5aca9d9141589fe1279720b3abc30cfabab805f396`. Pushed digest
`sha256:386c27a0a35a4f8f11fb4ed8a46a7caf2c8eaf51f3dd1f5109f4e2b57eb1978e`.

## Moving to a new kubespray release (maintainers)

1. Update `KUBESPRAY_TAG`, `KUBESPRAY_COMMIT` and `KUBESPRAY_ARCHIVE_SHA256` (GitHub archive of the
   commit SHA), and `KUBESPRAY_ANSIBLE_CORE` from the tag's `requirements.txt`. Bump `EE_TAG`.
2. Drop the backports that the new tag contains. Re-check the overlay variables
   (`roles/kubespray/templates/*.j2`) against the release notes; v2.33 drops `loadbalancer_apiserver`
   (#13392), which needs a kube-vip endpoint rework.
3. Regenerate the `kube_version` Enum from `BUILDINFO.json` `kube_latest_per_minor`.
4. Rebuild and release it as a new extension version.

Existing clusters stay on their extension version: the platform cannot move an instance to a
newer extension version, so a cluster outside the Kubernetes window of its version is redeployed.
