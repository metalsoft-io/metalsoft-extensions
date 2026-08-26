# VMware Cloud Foundation 9

This directory contains the MetalSoft extension definition (application kind) and the Ansible playbooks used to deploy and manage VMware Cloud Foundation (VCF) 9 on bare-metal infrastructure.

For details on MetalSoft extensions, see the official [documentation](https://docs.metalsoft.io/en/latest/content/developer_resources/extensions).

## Repository layout

| Path | Purpose |
| --- | --- |
| `extension.json` | The extension definition registered on the MetalSoft controller |
| `ansible/` | The Ansible bundle (playbooks + `esxi`/`vcf` roles) packaged as a zip |
| `execution-environment.yml` | `ansible-builder` definition for the execution environment image |
| `tests/` | Offline render harness for the SDDC bring-up spec (no infrastructure required) |

Supported VCF version: **9.0.1** (Bill of Materials below).

| Component | Version / build |
| --- | --- |
| ESX | 9.0.1.0-24957456 |
| vCenter Server | 9.0.1.0-24957454 |
| NSX | 9.0.1.0-24952111 |
| SDDC Manager | 9.0.1.0-24962180 |
| VCF Operations | 9.0.1.0-24960351 |
| VCF Operations fleet management | 24960371 |
| VCF Operations collector | 24960349 |
| VCF Automation (optional) | 24965341 |

> **IMPORTANT:** per the Broadcom 9.0.1 BOM, the **VCF Installer 9.0.2.0 build 25151285** OVA is required to deploy the 9.0.1 components. This is why the `ova_name` input defaults to the 9.0.2.0 appliance (`VCF-SDDC-Manager-Appliance-9.0.2.0.25151285.ova`) while `vcf_version` is `9.0.1.0` — it is **not** a version mismatch.

## What changed vs. VCF 5.2.x

- **Cloud Builder is gone.** It is replaced by the **VCF Installer** appliance, which ships as the same OVA as SDDC Manager.
- **The installer embeds no product binaries.** Everything (vCenter, NSX, SDDC Manager, VCF Operations, …) is pulled from an **offline depot** mirror over HTTPS with basic auth.
- **No license keys at bring-up.** The deployment runs in **90-day evaluation mode**; licensing is applied post-deploy in VCF Operations (Business Services). The bring-up spec contains no license keys.
- **Larger management footprint.** VCF Operations, Operations fleet management, and Operations collector appliances are always deployed; VCF Automation is optional.
- **NSX Manager `small` size no longer exists** in 9.x. Allowed values: `medium`, `large`, `xlarge` (default: `medium`).

## Deployment flow

1. ESXi host preparation (firewall, SSH, DNS, NTP, VM Network, certificate verification).
2. VCF Installer OVA deployment — the OVA is downloaded from the offline depot via basic auth and deployed to the first management host.
3. Depot configuration on the installer (offline depot, basic auth) and depot sync.
4. Binary downloads from the depot (~30 minutes to 2 hours from a LAN mirror).
5. SDDC spec validation via the installer API.
6. Bring-up of the management workload domain (~3 hours on physical hosts).
7. **Optional:** creation of a VI workload domain through SDDC Manager (network pool, host commissioning, `POST /v1/domains`) — only when the `workload` instance array has hosts (see the VI Workload Domain section below).

## Prerequisites

### Host requirements

- A MetalSoft environment with bare-metal hosts prepared for VCF deployment.
  - Minimum **3 hosts** (4 recommended and default) for the management domain.
  - Each host must meet VMware VCF hardware requirements (see the [VMware hardware compatibility guides](https://compatibilityguide.broadcom.com/)).
  - Strongly recommended: use hosts from the same manufacturer and model with identical CPU, memory, disk, and network configurations.
  - Each host must have a healthy hardware status with no errors.
  - All hosts must be vSAN-capable; hardware and firmware (including HBA and BIOS) configured for vSAN.
  - Each host must provide at least **two NICs at 10 Gbps or faster** (enforced by VCF validation).
- ESXi hosts **must be pre-installed with exactly ESX 9.0.1.0-24957456** — OS template `esxi-9-24957456-cluster-node`.
  - The ESXi self-signed certificates must be regenerated after the hostname is set (the OS template firstboot should do this); the extension's `esxi` role verifies that the certificate CN matches the host FQDN.

### Network and DNS

- A **routable DNS zone** for all management FQDNs. Do **not** use a `.local` domain — it breaks VCF Automation's services platform.

### Offline depot

- An **offline depot mirror** reachable from the installer:
  - Serves `/PROD` (the `productVersionCatalog` metadata plus the COMP binaries, including the ESX 9.0.1 ISO) over HTTPS with basic auth.
  - If vSAN ESA is enabled (`vsan_esa_enabled`, default is OSA/false), the vSAN HCL file served under `/PROD/vsan/hcl` must be **less than 90 days old**.

## Management appliance footprint

A minimum of **7 management VMs** are deployed: vCenter Server, 3× NSX Manager (plus a VIP), SDDC Manager, VCF Operations, Operations fleet management, and Operations collector. VCF Automation is optional via the `deploy_vcf_automation` input (adds 1 FQDN plus a 2-IP pool and an `internalClusterCidr`).

The extension allocates the following DNS records on the `vcf-mgmt` logical network:

| Record | Role |
| --- | --- |
| `installer.<cluster>.<zone>` | VCF Installer |
| `sddc.<cluster>.<zone>` | SDDC Manager |
| `m-vcs1.<cluster>.<zone>` | Management vCenter Server |
| `m-nsx1.<cluster>.<zone>` | NSX Manager VIP |
| `m-nsx1a.<cluster>.<zone>` / `m-nsx1b.<cluster>.<zone>` / `m-nsx1c.<cluster>.<zone>` | NSX Manager nodes |
| `ops1.<cluster>.<zone>` | VCF Operations |
| `opsfm1.<cluster>.<zone>` | VCF Operations fleet management |
| `opscp1.<cluster>.<zone>` | VCF Operations collector |
| `auto1.<cluster>.<zone>` | VCF Automation (only used when `deploy_vcf_automation` is true) |
| `w-vcs1.<cluster>.<zone>` | Workload domain vCenter Server (only used when the workload array has hosts) |
| `w-nsx1.<cluster>.<zone>` | Workload domain NSX Manager VIP (idem) |
| `w-nsx1a.<cluster>.<zone>` / `w-nsx1b.<cluster>.<zone>` / `w-nsx1c.<cluster>.<zone>` | Workload domain NSX Manager nodes (idem) |

`<cluster>` is the `{{CLUSTER_NAME}}` placeholder — the extension instance name — so records from multiple VCF instances at the same site stay unique. `<zone>` is `{{default_zone_name}}`, the site's default DNS zone.

## Adapting `extension.json` to your environment

The definition in this repository is a template — several values are environment-specific and **must** be changed before registering it on your controller:

### Network profiles

The extension declares four logical networks — `vcf-mgmt`, `vcf-vsan`, `vcf-vmotion`, `vcf-nsx` — and each one's `infrastructure.logicalNetworks[].profileLabel` must match a logical network profile that an operator has already created at the target site (in this repo the profile labels equal the network labels). The profiles are deployment-specific and the extension will fail to deploy if a label does not resolve. `vcf-mgmt` provides the default route and carries all the management appliance IP allocations; `vcf-vsan`, `vcf-vmotion` and `vcf-nsx` only carry IP pools handed to VCF for vmkernel/TEP addressing — one set for the management domain (8, 8 and 20 addresses) and a separate set for the optional workload domain (16, 16 and 20 addresses, role tags `wld-*`). Both the `management` and `workload` instance arrays attach to the same four networks; **all IP allocations and pools (including the `wld-*` ones) are reserved at deploy time even when the workload array is at 0 instances.**

### Input default values

Set the input defaults so they reflect your environment instead of forcing every operator to override them at instance-create time:

| Input | Default in this repo | What to change |
| --- | --- | --- |
| `mgmt_domain_cluster_node_os_template` | *(operator-selected)* | The OS template offered must exist at the target and install exactly ESX 9.0.1.0-24957456 (e.g. `esxi-9-24957456-cluster-node`). |
| `mgmt_domain_instance_count` | `4` (min 3, max 16) | Number of management domain nodes. This is the input operators change later to scale the domain (see Scaling below). |
| `*_password` inputs (installer, SDDC Manager, NSX, vCenter, VCF Operations, Automation) | Example values committed in this repo | **Change every one of them** — they are placeholders, not secrets. New values must satisfy the input's `validationRegEx` (`^[A-Za-z0-9!@#$%^&*+]{12,20}$`); the charset is restricted to what all VCF components accept, so keep validation at the input rather than relaxing it. |
| `vcf_instance_name` | *(empty)* | Optional per-instance VCF instance name; when unset the playbooks derive `<extension_instance_id>-vcf`. |
| `wld_domain_instance_count` | `0` (0 or 3–16; 1 and 2 are rejected via `deniedValues`) | Number of VI workload domain nodes. `0` = management domain only. Change it later to create/scale/delete the workload domain (see below). |
| `wld_domain_cluster_node_server_type` / `wld_domain_cluster_node_os_template` | *(operator-selected)* | Server type and ESXi OS template for workload hosts. **Must be selected even when the count is 0** (ServerType/OsTemplate inputs cannot carry defaults). |
| `wld_vcenter_root_password` / `wld_nsx_manager_admin_password` / `wld_nsx_manager_audit_password` / `wld_sso_admin_password` | Example values committed in this repo | Workload domain appliance credentials and the isolated SSO domain administrator password — **change them** like the other password inputs (same `validationRegEx`). |

### DNS records

All management FQDNs are declared as `dnsRecords` on the `vcf-mgmt` VIP allocations using the `{{default_zone_name}}` placeholder (the site's default DNS zone) — see the record table above. Every record is created with a PTR, and VCF validation requires the full forward **and** reverse round-trip (IP → PTR → FQDN → A → same IP) to succeed.

**ATTENTION**: a DNS provisioning extension is required to exist in MetalSoft, so that the records the platform allocates are actually created and resolvable by the hosts and appliances. Examples can be found in this repo for powerdns and infoblox.

### Site config vars

Admin/site-level settings live in `configVars` and are set **once per site** by an operator (Extension Site Config), not per deployment. The extension must be enabled and its site config saved on the target site **before the first deploy** — config vars without a default (currently `depot_password`) are mandatory at that point. Values reach the playbooks as `configVars.<label>`.

| Config var | Default in this repo | What to change |
| --- | --- | --- |
| `DNSResolvers` | `1.1.1.1` | The DNS resolvers the playbooks write into the ESXi hosts and the bring-up spec (comma-separated string accepted). **These resolvers are configured on all hosts and appliances and MUST be able to resolve the created management records** — handing VCF a public resolver breaks bring-up. |
| `depot_hostname` / `depot_port` / `depot_username` / `depot_password` | `vmware-depot.metalsoft.dev` / `443` / `vmware-depot` / *(no default)* | Point at **your** offline depot mirror (see Prerequisites). The password has no default and is validated before deployment. |
| `ova_name` / `ova_url` / `vcf_version` | `VCF-SDDC-Manager-Appliance-9.0.2.0.25151285.ova` / *(empty)* / `9.0.1.0` | Leave as-is for the 9.0.1 BOM (the 9.0.2.0 installer OVA is intentional — see the note above). When `ova_url` is empty the download URL is derived from the depot. |
| `deployment_architecture_model` | `consolidated` | VCF deployment architecture model handed to the installer spec. |
| `nsx_manager_size` / `vcenter_vm_size` / `vcf_ops_appliance_size` | `medium` / `small` / `small` | Appliance sizing. NSX `small` no longer exists in 9.x (`medium`/`large`/`xlarge`). |
| `deploy_vcf_automation` / `vcf_automation_internal_cluster_cidr` | `false` / `198.18.0.0/15` | Enable VCF Automation and, if needed, change its internal cluster CIDR so it doesn't overlap existing networks. |
| `vsan_failures_to_tolerate` | `1` | vSAN FTT for the management cluster (0–3). |
| `deploy_without_license_keys` | `true` | Must stay `true` on VCF 9 — bring-up runs in evaluation mode and the API rejects the spec otherwise. |
| `skip_gateway_ping_validation` / `validation_debug` | `false` / `false` | Troubleshooting aids for spec validation. |
| `wld_nsx_manager_count` | `3` (1–3) | NSX Manager nodes deployed for the VI workload domain. 3 (high availability) is the VCF default; 1 is allowed for small deployments. |

### Asset URLs

Both entries in `assets[]` must point at artifacts **you** host (see the next two sections):

- `vcf-ansible-bundle` — the URL of the Ansible bundle zip.
- `ee-vcf9-9-0-1` — the execution environment image reference (`repositoryRegistry`, `namespaceRegistry`, `tagRegistry`) and the URL of the image tarball.

### Registering the definition

Once adapted, register and publish with `metalcloud-cli`:

```bash
metalcloud-cli extension create "VMware Cloud Foundation 9 (VCF)" application \
    "VMware Cloud Foundation (VCF)" --definition-source extension.json
metalcloud-cli extension publish <id_or_label>
```

Extensions are created as drafts; only drafts can be updated in place. Once published, update with a new version increment, or archive and recreate to change the definition.

## Outputs

The extension publishes these outputs on the instance (visible in the UI / API after deploy):

| Output | Content |
| --- | --- |
| `installer_url` | VCF Installer UI (`https://installer.<instance>.<zone>/vcf-installer-ui`) |
| `sddc_manager_url` | SDDC Manager UI |
| `vcenter_url` | Management vCenter Server UI |
| `vcenter_sso_username` | Login for the management vCenter (`administrator@vsphere.local`, or `administrator@<psc_sso_domain_name>` when overridden) — password is the `vcenter_sso_admin_password` custom variable set at bring-up |
| `nsx_manager_url` | NSX Manager (VIP) UI |
| `vcf_ops_url` | VCF Operations UI |
| `ops_fleet_mgmt_url` | VCF Operations fleet management UI |
| `ops_collector_url` | VCF Operations collector UI |
| `vcf_automation_url` | VCF Automation UI — empty string when `deploy_vcf_automation` is false |
| `sddc_id` / `datacenter_name` / `cluster_name` | SDDC identifiers (e.g. `212-m` / `212-m-dc1` / `212-m-cl1`) for follow-up automation against the vCenter / SDDC Manager APIs |
| `wld_vcenter_url` / `wld_nsx_manager_url` | Workload domain vCenter / NSX Manager (VIP) UIs — empty strings while the workload array is at 0 instances |
| `wld_vcenter_sso_username` | Login for the workload vCenter's isolated SSO domain (`administrator@wld-<wld_id>-w.sso.local`) — password is the `wld_sso_admin_password` input; empty string while the workload array is at 0 instances |
| `wld_domain_name` | Workload domain name in SDDC Manager (e.g. `212-w`) — empty string while the workload array is at 0 instances |

A playbook returns outputs by writing an `artifacts/<ident>/context.json` whose top-level keys match the declared output labels; the platform stores them on the instance. All values are derived from the `extensionInstanceRecordSet` allocations (the per-instance appliance FQDNs), so every run can recompute them.

**Stored outputs are replaced on every successful run**, and a run that writes no `context.json` wipes them. Every lifecycle playbook therefore ends with a `Publish extension outputs` play (`roles/vcf/tasks/emit-outputs.yaml`, guarded on the context file's existence) — keep that play intact when modifying the bundle, or a no-op edit or scale-in run will silently erase the stored outputs.

## Building and hosting the Ansible bundle

The runtime does not read the `ansible/` directory from git — the playbooks are delivered as a **zip bundle** fetched from the URL declared in the `vcf-ansible-bundle` asset.

Two rules matter when creating the zip:

1. **Playbooks must sit at the archive root** (no wrapper directory) — the runner unzips the bundle into its project directory and runs the requested playbook by bare filename.
2. Never ship a file named `job.yml` — the runner renames the requested playbook to that reserved name.

Build it from inside the `ansible/` directory:

```bash
cd ansible
zip -r ../vmware-cloud-foundation9-v2.3.2.zip . -x '*.DS_Store' -x '*.zip' -x 'README.md'
unzip -l ../vmware-cloud-foundation9-v2.3.2.zip   # deploy.yaml, scale.yaml, roles/ must be at top level
```

Then upload the zip to an **HTTP(S) repository server reachable by the global MetalSoft controller** (the controller downloads it from there — there is no bundle-upload CLI command) and set that URL (max 128 characters) as the `url` of the `vcf-ansible-bundle` asset. The convention used here is:

```
https://repo.metalsoft.io/.extensions_ms/vmware-cloud-foundation9/vmware-cloud-foundation9-v<version>.zip
```

Bump the version in the filename on every change — re-uploading under the same name risks serving a cached/stale bundle, which makes fixes appear to "not take".

## Building the execution environment (EE) image

The site controller runs these playbooks inside an **Ansible execution environment** (a container image) via `ansible-runner`. The bundled [`execution-environment.yml`](execution-environment.yml) is only the **build recipe** — it is *not* read at deploy time. You must build the image from it, publish it to a registry the site controller can reach, and point the controller (or a per-task `OciImage` asset in `extension.json`) at it.

> **Architecture matters: the image must be `linux/amd64` (x86_64).** MetalSoft site controllers run on x86_64. The EE pip-compiles native wheels (`pyVmomi`, `psutil`, …, using the `gcc`/`make`/`*-devel` system packages), so the image is architecture-specific — you cannot just retag an ARM build. If you build on Apple Silicon / any ARM host you **must cross-build for `linux/amd64`**.

### Prerequisites

- Python 3.10+ and `ansible-builder`: `pip install ansible-builder`
- **Docker** with BuildKit (default in modern Docker) and `buildx`.
- For cross-arch builds on ARM, emulation for `linux/amd64`:
  - Docker Desktop ships it (buildx + QEMU) out of the box.
  - On Linux Docker, register the QEMU binfmt handlers first: `docker run --privileged --rm tonistiigi/binfmt --install amd64`.
  - Cross-building under emulation compiles the native wheels slowly — expect several minutes.

### Build (single command)

```bash
ansible-builder build \
  --file execution-environment.yml \
  --tag <registry>/<namespace>/vcf9-ee:9.0.1 \
  --container-runtime docker \
  --extra-build-cli-args "--platform=linux/amd64" \
  --verbosity 3
```

On an x86_64 build host the `--extra-build-cli-args` line is optional; keep it to be explicit.

### Build (two-step, more control)

Generate the build context, then build it with Docker directly:

```bash
ansible-builder create \
  --file execution-environment.yml \
  --context ./ee-context \
  --output-filename Containerfile
docker buildx build \
  --platform=linux/amd64 \
  -f ./ee-context/Containerfile \
  -t <registry>/<namespace>/vcf9-ee:9.0.1 \
  --load \
  ./ee-context
```

(`--load` places the built image into the local Docker image store; use `--push` instead to build-and-push in one step.)

### Verify architecture and publish

```bash
docker image inspect <registry>/<namespace>/vcf9-ee:9.0.1 --format '{{.Architecture}}'
# → must print: amd64   (NOT arm64)
docker save <registry>/<namespace>/vcf9-ee:9.0.1 | gzip > ee-vcf9.9.0.1.tar.gz
```

Upload the resulting tarball to the HTTP repo server and set its URL as the `ee-vcf9-9-0-1` asset's `url`. The image must end up in a **container registry reachable by the site controller** (load the tarball there with `docker load -i ee-vcf9.9.0.1.tar.gz` and push it), and the asset's `repositoryRegistry` / `namespaceRegistry` / `tagRegistry` fields must match that registry location.

Then either set this image as the site controller's default EE, or reference it per-task via the `OciImage` asset in `extension.json`. The image already bundles everything the playbooks shell out to (`dig` via `bind-utils`, `openssh-clients`, `openssl`) plus the required Galaxy collections and VMware SDKs — do **not** rely on installing anything at run time.

## Scaling (scale out / scale in)

Scaling is driven entirely by editing the **`mgmt_domain_instance_count`** input on the deployed extension instance (default 4, minimum 3, maximum 16) — increase it to add ESXi hosts to the management domain, decrease it to remove them.

When the operator saves the edit, the platform adjusts the infrastructure and runs the `onEdit` lifecycle. The same `scale.yaml` playbook is registered at both stages and self-selects what to do via the platform-generated inventory groups `management_scale_out` / `management_scale_in` (empty groups make the corresponding play a no-op); all SDDC Manager API calls are made from the controller via `delegate_to: localhost`:

**Scale in — `onEdit` / `preDeploy` (`scale.yaml`):** runs while the outgoing servers are still provisioned. For each host in `management_scale_in` (serially), it builds the spec, determines the host ID in SDDC Manager, removes the host from the cluster (cluster compact), and decommissions it. After the stage completes, the platform deprovisions and releases the servers.

**Scale out — `onEdit` / `postDeploy` (`scale.yaml`):** once the new servers are provisioned, the `esxi` role prepares them (firewall, SSH, DNS, NTP, VM Network, certificate check), then the `vcf` role builds and validates the spec, commissions the new hosts in SDDC Manager, and expands the management cluster.

Notes:

- Scaling requires a successfully completed initial deployment — the operations run against the live SDDC Manager API.
- The new hosts must satisfy the same requirements as the initial ones (identical hardware recommended, the exact ESX 9.0.1 build, vSAN-capable) and enough free addresses must remain in the vSAN/vMotion/NSX IP pools.
- Both `onEdit` tasks reference the `ee-vcf9-9-0-1` asset (same EE as the initial deploy) and carry a 6-hour `executionTimeout` — a `0→N` edit runs a full workload domain creation (~2-3 h).
- An edit that changes no instance counts runs both stages as no-ops.

## VI Workload Domain

A second instance array, **`workload`**, drives an optional **VI workload domain** created through the SDDC Manager API (`/v1/network-pools`, `/v1/hosts`, `/v1/domains`). It is controlled entirely by the **`wld_domain_instance_count`** input:

- **`0` (default):** management domain only. No workload domain resources are created, and the `wld_*` outputs are empty strings. The `wld-*` DNS records and IP pools are still allocated by the platform (they are part of the extension definition), and the workload server type / OS template inputs must still be selected at create time.
- **`3`–`16`:** a VI workload domain (vSAN principal storage, own vCenter + own NSX cluster, joined to the management SSO domain) is created after the management bring-up. `1` and `2` are rejected at the input (`deniedValues`) — VCF requires at least 3 hosts for a vSAN cluster.

Naming mirrors the management domain with a `-w`/`w-` prefix: domain `<instance-id>-w`, cluster `<instance-id>-w-cl1`, datacenter `<instance-id>-w-dc1`, network pool `<instance-id>-w-np1`, vSphere distributed switch `w-cl1-vds1`, appliances `w-vcs1` / `w-nsx1(a|b|c)`.

**Prerequisites** (in addition to the management ones):

- A completed management domain bring-up (the workload flow talks to SDDC Manager).
- A **vLCM cluster image (personality)** available on SDDC Manager — mandatory for new domains in VCF 9. The management domain image is reused automatically (first available personality; override with the `wld_cluster_image_name` variable).
- Workload hosts on the same ESX 9.0.1 build/express patch level as the management hosts.
- Free addresses in the `wld-vsan-pool` / `wld-vmotion-pool` / `wld-nsx-host-overlay-pool` ranges and resolvable `w-*` DNS records (forward + reverse, like the management ones).

**Lifecycle** (all through editing `wld_domain_instance_count`):

| Edit | What happens |
| --- | --- |
| `0 → N` (N ≥ 3) | Full domain creation at `onEdit`/`postDeploy`: ESXi prep, network pool creation, host commissioning, domain spec validation, `POST /v1/domains`, task wait (~2-3 h). |
| `N → N+k` | New hosts are prepped, commissioned into the workload network pool, and added to the workload cluster (cluster expansion). |
| `N → N-k` (result ≥ 3) | Outgoing hosts are removed from the workload cluster and decommissioned, one at a time (same flow as management scale-in). |
| `N → 0` | **The entire workload domain is DELETED** — marked for deletion, `DELETE /v1/domains/{id}`, hosts decommissioned, network pool removed. |

> **WARNING — `N → 0` is irreversible.** Deleting the workload domain destroys its vSAN datastore and everything on it. Migrate or remove user VMs and **delete any NSX Edge clusters in the domain first** (SDDC Manager refuses/fails the deletion otherwise) — the extension does not check for user workloads before deleting.

Retry safety: every workload flow probes SDDC Manager state first (existing domain → resumed via task retry, commissioned hosts → skipped, existing pool → reused), so a failed lifecycle task can be retried from the platform without manual cleanup.

Details about the input variables for the VCF deployment can be found in the [Ansible README](ansible/README.md), which also documents the playbook flow and the offline spec render test.
