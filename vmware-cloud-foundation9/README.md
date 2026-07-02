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

## Configuration

The configuration is primarily driven by the `extension.json` file, which defines various parameters for the deployment.

Key variables that define the MetalSoft infrastructure are:

```yaml
mgmt_domain_cluster_node_server_type: Represents the server type for the VCF management domain.
mgmt_domain_instance_count: Number of nodes in the VCF management domain (default: 4, minimum: 3). Modifying this value triggers horizontal scaling (scale-out/scale-in) for the management domain.
mgmt_domain_cluster_node_os_template: OS template name for VCF management domain nodes (must install ESX 9.0.1.0-24957456, e.g. 'esxi-9-24957456-cluster-node').
```

Details about the input variables for the VCF deployment can be found in the [Ansible README](ansible/README.md).
