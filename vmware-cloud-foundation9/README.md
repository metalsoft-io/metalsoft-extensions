# VMware Cloud Foundation 9

This directory contains the MetalSoft extension definition (application kind) and the Ansible playbooks used to deploy and manage VMware Cloud Foundation (VCF) 9 on bare-metal infrastructure.

For details on MetalSoft extensions, see the official [documentation](https://docs.metalsoft.io/en/latest/content/developer_resources/extensions).

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
| `installer.<zone>` | VCF Installer |
| `sddc.<zone>` | SDDC Manager |
| `m-vcs1.<zone>` | Management vCenter Server |
| `m-nsx1.<zone>` | NSX Manager VIP |
| `m-nsx1a.<zone>` / `m-nsx1b.<zone>` / `m-nsx1c.<zone>` | NSX Manager nodes |
| `ops1.<zone>` | VCF Operations |
| `opsfm1.<zone>` | VCF Operations fleet management |
| `opscp1.<zone>` | VCF Operations collector |
| `auto1.<zone>` | VCF Automation (only used when `deploy_vcf_automation` is true) |

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
docker push <registry>/<namespace>/vcf9-ee:9.0.1
```

Then either set this image as the site controller's default EE, or reference it per-task as an `OciImage` asset in `extension.json`. The image already bundles everything the playbooks shell out to (`dig` via `bind-utils`, `openssh-clients`, `openssl`) plus the required Galaxy collections and VMware SDKs — do **not** rely on installing anything at run time.

## Configuration

The configuration is primarily driven by the `extension.json` file, which defines various parameters for the deployment.

Key variables that define the MetalSoft infrastructure are:

```yaml
mgmt_domain_cluster_node_server_type: Represents the server type for the VCF management domain.
mgmt_domain_instance_count: Number of nodes in the VCF management domain (default: 4, minimum: 3). Modifying this value triggers horizontal scaling (scale-out/scale-in) for the management domain.
mgmt_domain_cluster_node_os_template: OS template name for VCF management domain nodes (must install ESX 9.0.1.0-24957456, e.g. 'esxi-9-24957456-cluster-node').
```

Details about the input variables for the VCF deployment can be found in the [Ansible README](ansible/README.md).
