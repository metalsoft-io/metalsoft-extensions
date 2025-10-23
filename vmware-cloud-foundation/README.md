# VMware Cloud Foundation

This directory contains the MetalSoft extension definition (Application kind) and the Ansible playbooks used to deploy and manage VMware Cloud Foundation (VCF) on bare-metal infrastructure.

Details about the input variables for the VCF deployment can be found in the [Ansible README](ansible/README.md).

For details on MetalSoft extensions, see the official [documentation](https://docs.metalsoft.io/en/latest/content/developer_resources/extensions).

Supported VCF versions: 5.2.1 and 5.2.2.

## Prerequisites

- A MetalSoft environment with bare-metal hosts prepared for VCF deployment.
  - At least four hosts are required for a basic VCF deployment.
  - Each host must meet VMware VCF hardware requirements (see the [VMware hardware compatibility guides](https://compatibilityguide.broadcom.com/)).
  - Strongly recommended: Use hosts from the same manufacturer and model with identical CPU, memory, disk, and network configurations.
  - Each host must have a healthy hardware status with no errors.
  - All servers must be vSAN compliant; hardware and firmware (including HBA and BIOS) are configured for vSAN (see [vSAN Hardware Requirements](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-5-2-and-earlier/5-2/vcf-design-5-2/vcf-vsan-design.html#GUID-6074725F-F9BE-4464-87E1-524605DF797C-en)).
    - Also see: [Supported Storage Types in VMware Cloud Foundation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-5-2-and-earlier/5-2/vcf-design-5-2/vcf-shared-storage-design.html).
    - [vSAN Original Storage Architecture storage device requirements](https://techdocs.broadcom.com/us/en/vmware-cis/vsan/vsan/8-0/planning-and-deployment/requirements-for-creating-a-virtual-san-cluster/hardware-requirements-for-virtual-san.html)
    - [vSAN Express Storage Architecture storage device requirements](https://techdocs.broadcom.com/us/en/vmware-cis/vsan/vsan/8-0/planning-and-deployment/requirements-for-creating-a-virtual-san-cluster/hardware-requirements-for-virtual-san.html)
  - Each host must provide a minimum of two 10 Gbps network interfaces.
- OS templates for VMware ESXi 8.0U3g matching the target VCF version (see MetalSoft ESXi templates: <https://github.com/metalsoft-io/os-templates/tree/main/ESXi/8.0.3/esxi-8-cluster-node>).
  - VMware ESXi 8.0U3g-24280767 for VMware Cloud Foundation (VCF) 5.2.1.
  - VMware ESXi 8.0U3g-24859861 for VMware Cloud Foundation (VCF) 5.2.2.
- VMware Cloud Foundation installation media and licenses.
  - VMware-Cloud-Builder-5.2.1.0-24307856_OVF10.ova for VMware Cloud Foundation (VCF) 5.2.1.
  - VMware-Cloud-Builder-5.2.2.0-24936865_OVF10.ova for VMware Cloud Foundation (VCF) 5.2.2.
