# VMware Cloud Foundation 9 (VCF)

Ansible playbooks and roles for deploying and managing VMware Cloud Foundation (VCF) 9 environments via the VCF Installer appliance (the Cloud Builder appliance used by VCF 5.x no longer exists in 9.x).

## Playbook flow

`deploy.yaml` (initial deployment) runs three plays (plus the trailing outputs play):

1. **`esxi` role** (all hosts, workload hosts included): set firewall → enable SSH → set DNS → set NTP → configure the 'VM Network' portgroup → verify the ESXi certificate CN matches the host FQDN → collect SSH/SSL thumbprints.
2. **`vcf` role** (first management host): `vmnics-to-uplinks` → `build-sddc-spec` → `validate-sddc-spec` (basic / infrastructure / networks / allocations / depot / installer) → `deploy-vcf-installer` (OVA pulled from the depot with basic auth) → `installer/configure-depot` (configure + sync the offline depot) → `installer/download-binaries` (release binaries for `vcf_version`) → `deploy-mgmt-workload-domain` (spec validation + bring-up via the installer API).
3. **VI workload domain** (`roles/vcf/tasks/wld/deploy-vi-workload-domain.yaml`, no-op when the `workload` array is empty): SDDC Manager auth → existing-domain pre-check (ACTIVE → skip, failed/in-flight → resume via `PATCH /v1/tasks/{id}`) → workload vmnic discovery → network pool (`/v1/network-pools`) → host commissioning (`/v1/hosts`) → vLCM cluster image lookup (`/v1/personalities`) → domain spec validation (`/v1/domains/validations`) → `POST /v1/domains` → long task wait (re-auth each cycle).

`scale.yaml` (lifecycle operations) targets the `management_scale_out` / `management_scale_in` / `workload_scale_out` / `workload_scale_in` host groups (the ESXi nodes being added or removed); all SDDC Manager API calls are made from the controller via `delegate_to: localhost`.

- **Management scale-out**: prepare the new ESXi hosts (`esxi` role), build/validate the spec, commission the hosts, and expand the cluster.
- **Management scale-in**: build the spec, determine the host ID, compact the cluster, and decommission the host.
- **Workload scale-out** (`wld/scale-out.yaml`): when no workload domain exists yet (0→N edit), the full domain-creation flow from `deploy.yaml` play 3 runs; otherwise the new hosts are commissioned into the workload network pool and added to the workload cluster.
- **Workload scale-in**: when the target count is 0, `wld/delete-domain.yaml` deletes the ENTIRE workload domain (markForDeletion → `DELETE /v1/domains/{id}` → decommission hosts → delete the network pool); otherwise each outgoing host is removed from the workload cluster and decommissioned (same `scale-in.yaml` as management).

### Offline spec render test

The SDDC bring-up spec, the workload domain creation spec, and the outputs payload can be rendered offline against a fixture (no infrastructure required):

```sh
cd tests && ansible-playbook -i inventory.yaml render-spec.yaml            # mgmt + 3-host workload domain
cd tests && ansible-playbook -i inventory-wld0.yaml render-spec-wld0.yaml  # mgmt only (workload count 0)
```

## Variables

These variables can be customized in the `extension.json` file under the `inputs` section to suit specific deployment requirements.

Key variables include:

```yaml
# The values for these variables are provided by Metalsoft site and global configuration.
# They can be overridden by adding them to the extensionInstanceVariables section of extension.json.
ntp_servers: List of NTP servers for time synchronization.
domain: The primary domain for the VCF environment.
subdomain: The subdomain for the VCF environment.
dns_servers: List of DNS servers for name resolution.
dns_searchpath: The DNS search path for the environment.
```

```yaml
# Offline depot configuration.
# The VCF Installer embeds no product binaries: everything is pulled from this
# HTTPS basic-auth mirror, which must serve /PROD (productVersionCatalog metadata
# and COMP binaries, including the ESX 9.0.1 ISO).
depot_hostname: Hostname of the offline depot mirror. Defaults to 'vmware-depot.metalsoft.dev'.
depot_port: HTTPS port of the depot. Defaults to 443.
depot_username: Basic-auth username for the depot. Defaults to 'vmware-depot'.
depot_password: Basic-auth password for the depot. Required (validated before deployment).
depot_validate_certs: Whether to validate the depot TLS certificate. Defaults to false (internal mirrors typically run self-signed certificates).
depot_esx_iso_name: Name of the ESX ISO whose presence is verified in the depot. Defaults to 'VMware-VMvisor-Installer-9.0.1.0.24957456.x86_64.iso'.
```

```yaml
# VCF version and installer OVA.
vcf_version: The version of VCF to deploy. Defaults to '9.0.1.0'.
# Per the Broadcom 9.0.1 BOM, the VCF Installer 9.0.2.0 build 25151285 appliance is
# required to deploy 9.0.1 components — the version difference is intentional.
ova_name: The name of the VCF Installer OVA file (same OVA as SDDC Manager). Defaults to 'VCF-SDDC-Manager-Appliance-9.0.2.0.25151285.ova'.
# Optional override for the OVA download URL. When empty, the URL is derived from the depot:
# https://<depot_hostname>:<depot_port>/PROD/COMP/SDDC_MANAGER_VCF/<ova_name>
ova_url: Optional full URL from which to download the VCF Installer OVA.
vcf_release_sku: SKU used by the installer release-components API ('VCF' or 'VVF'). Defaults to 'VCF'.
```

```yaml
# Deployment architecture model.
# The models require different extension definitions.
deployment_architecture_model: Options include 'consolidated', 'standard'. Defaults to 'consolidated'.

# Deployment platform (the spec "workflowType").
deployment_platform: Options include 'VCF', 'VCF_EXTEND' or 'VVF'. Defaults to 'VCF'.

# Separate VLAN for management VMs and ESXi management VMK interfaces.
# Requires additional configuration in the extension definition.
distinct_vlan_id_vm_mgmt_and_esxi_mgmt: Whether separate VLANs are used for VM management and ESXi management networks. Defaults to false.
```

```yaml
# SDDC ID for the Management Cluster
# Can contain only letters, numbers and the following symbols: '-'
sddc_id: A client-provided string that identifies an SDDC by name or instance. Used for the management domain name. Defaults to pattern '<extension_instance_id>-m'.
# Name for the network pool to be created and associated with the Management Cluster
management_pool_name: The name of the management network pool. Defaults to '<sddc_id>-np1'.
# Name of the VCF instance (new in 9.x).
vcf_instance_name: The VCF instance name. Defaults to pattern '<extension_instance_id>-vcf'.
```

```yaml
# NSX Manager size.
# One of: medium, large, xlarge ('small' no longer exists in 9.x).
nsx_manager_size: The size of the NSX Manager deployment. Defaults to 'medium'.

# Name of the Distributed Portgroup to be created.
vm_management_portgroup_name: The name of the VM management portgroup. Defaults to '<sddc_id>-cl1-vds1-vm-mgmt'.
esxi_management_portgroup_name: The name of the ESXi management portgroup. Defaults to '<sddc_id>-cl1-vds1-esxi-mgmt'.
vmotion_portgroup_name: The name of the vMotion portgroup. Defaults to '<sddc_id>-cl1-vds1-vmotion'.
vsan_portgroup_name: The name of the vSAN portgroup. Defaults to '<sddc_id>-cl1-vds1-vsan'.

# Name of the IP address pool
nsx_host_overlay_ip_pool_name: The name of the NSX host overlay IP address pool. Defaults to '<sddc_id>-cl1-tep1'.
```

```yaml
# vCenter Datacenter Name.
vcenter_datacenter_name: The name of the vCenter Server datacenter. Defaults to '<sddc_id>-dc1'.

# vCenter Cluster Name.
vcenter_cluster_name: The name of the vCenter Server cluster. Defaults to '<sddc_id>-cl1'.

# vCenter virtual machine size.
# One of: xlarge, large, medium, small, tiny.
vcenter_vm_size: The size of the vCenter Server VM. Defaults to 'small'.

# SSO domain name.
psc_sso_domain_name: The SSO domain name. Defaults to 'vsphere.local'.

# List of Resource Pool Specifications.
management_resource_pool_name: The name of the resource pool for management VMs. Defaults to '<sddc_id>-cl1-rp-sddc-mgmt'.
networking_resource_pool_name: The name of the resource pool for networking VMs. Defaults to '<sddc_id>-cl1-rp-sddc-edge'.
compute_user_vm_resource_pool_name: The name of the resource pool for user VMs. Defaults to '<sddc_id>-cl1-rp-user-vm'.
compute_user_edge_resource_pool_name: The name of the resource pool for user edge VMs. Defaults to '<sddc_id>-cl1-rp-user-edge'.
```

```yaml
# vSAN architecture model.
vsan_esa_enabled: Boolean to specify if the vSAN ESA architecture is used. Defaults to false (OSA). When enabled, the depot's vSAN HCL file (/PROD/vsan/hcl) must be less than 90 days old.
# vSAN deduplication and compression feature flag (single flag controls both features)
vsan_dedup_enabled: Boolean to specify if vSAN deduplication and compression is enabled. Defaults to false.
# vSAN datastore name.
vsan_datastore_name: The name of the vSAN datastore. Defaults to '<sddc_id>-cl1-ds1'.
# vSAN failures to tolerate (0-3).
vsan_failures_to_tolerate: Number of host failures the vSAN datastore can tolerate. Defaults to 1.
```

```yaml
# Enable VCF Customer Experience Improvement Program (CEIP).
ceip_enabled: Boolean to specify if CEIP is enabled. Defaults to false.

# Skip ESXi thumbprint validation (sshThumbprint and sslThumbprint).
# If false, sshThumbprint and sslThumbprint will be automatically collected from ESXi hosts
# and the ESXi certificate CN is verified against the host FQDN.
skip_esx_thumbprint_validation: Whether to skip ESXi thumbprint validation. Defaults to false.

# Skip the gateway ping validation during bring-up.
skip_gateway_ping_validation: Whether to skip gateway ping validation. Defaults to false.
```

```yaml
# NOTE: there are no license key inputs in 9.x. The deployment runs in 90-day
# evaluation mode; licensing is applied post-deploy in VCF Operations (Business Services).

# VCF Installer appliance configuration.
# Passwords must be at least 15 characters long.
installer_admin_password: The password for the VCF Installer admin user.
installer_root_password: The password for the VCF Installer root user.

# SDDC Manager configuration.
sddc_root_password: The password for the SDDC Manager root user.
sddc_local_admin_password: The password for the SDDC Manager local admin user.
sddc_second_user_password: The password for the SDDC Manager second user.

# NSX Manager configuration.
nsx_manager_root_password: The password for the NSX Manager root user.
nsx_manager_admin_password: The password for the NSX Manager admin user.
nsx_manager_audit_password: The password for the NSX Manager audit user.

# vCenter Server configuration.
vcenter_root_password: The password for the vCenter Server root user.
vcenter_sso_admin_password: The password for the vCenter Server SSO admin user (administrator@vsphere.local).

# VCF Operations configuration (new in 9.x).
vcf_ops_admin_password: The password for the VCF Operations admin user.
vcf_ops_root_password: The password for the VCF Operations root user.
vcf_ops_appliance_size: The size of the VCF Operations appliance. Defaults to 'small'.

# VCF Operations fleet management configuration (new in 9.x).
ops_fleet_mgmt_root_password: The password for the Operations fleet management root user.
ops_fleet_mgmt_admin_password: The password for the Operations fleet management admin user.

# VCF Operations collector configuration (new in 9.x).
ops_collector_root_password: The password for the Operations collector root user.

# VCF Automation configuration (optional, new in 9.x).
deploy_vcf_automation: Boolean to deploy VCF Automation. Defaults to false. Requires the 'vcf-automation' FQDN and the 2-IP 'automation-ip-pool' range on the vcf-mgmt network.
vcf_automation_admin_password: The password for the VCF Automation admin user.
vcf_automation_internal_cluster_cidr: Internal cluster CIDR for VCF Automation. Defaults to '198.18.0.0/15'.
```

```yaml
# VI workload domain (optional, driven by the 'workload' instance array / wld_domain_instance_count input).
# Naming mirrors the management domain with a -w / w- prefix; every name is overridable
# via extensionInstanceVariables like the management ones.
wld_id: Base identifier for workload domain resources. Defaults to '<extension_instance_id>-w'.
wld_domain_name: The workload domain name in SDDC Manager. Defaults to '<wld_id>'.
wld_pool_name: The workload host network pool name. Defaults to '<wld_id>-np1'.
wld_cluster_name: The workload cluster name. Defaults to '<wld_id>-cl1'.
wld_datacenter_name: The workload datacenter name. Defaults to '<wld_id>-dc1'.
wld_vds_name: The workload vSphere distributed switch name. Defaults to 'w-cl1-vds1' (mirrors the literal 'm-cl1-vds1').
wld_datastore_name: The workload vSAN datastore name. Defaults to '<wld_id>-cl1-ds1'.
wld_tep_pool_name: The workload NSX host overlay TEP pool name. Defaults to '<wld_id>-cl1-tep1'.
wld_cluster_image_name: vLCM cluster image (personality) name to use. Defaults to '' (first available personality on SDDC Manager).
wld_nsx_manager_count: NSX Manager nodes for the workload domain (1-3, configVar). Defaults to 3.
wld_vcenter_root_password: The password for the workload domain vCenter Server root user.
wld_nsx_manager_admin_password: The password for the workload domain NSX Manager admin user.
wld_nsx_manager_audit_password: The password for the workload domain NSX Manager audit user.
wld_sso_admin_password: The administrator password for the workload domain's isolated SSO domain. VCF 9 requires every VI domain to be an isolated SSO domain.
wld_sso_domain_name: The workload domain's isolated SSO domain name. Defaults to 'wld-<wld_domain_name>.sso.local' (must start with a letter, 3-63 chars of A-Za-z0-9-).
wld_domain_wait_cycles: Wait cycles (one poll each, re-authenticating) for domain creation. Defaults to 180.
wld_domain_delete_wait_cycles: Wait cycles for domain deletion. Defaults to 60.
wld_domain_poll_interval: Seconds between domain task polls. Defaults to 60.
```

```yaml
# VCF Installer deployment and API retry knobs.
installer_datastore: ESXi datastore for the installer appliance. Defaults to 'datastore1'.
installer_disk_provisioning: Disk provisioning mode for the installer appliance. Defaults to 'thin'.
installer_validate_certs: Whether to validate the installer TLS certificate. Defaults to 'no'.
installer_ova_checksum: Optional checksum ('sha256:<hex>') verified against the downloaded installer OVA.
installer_url_probe: Enable an optional reachability probe of the OVA URL during validation. Defaults to false.
installer_datastore_precheck: Verify the installer datastore exists and has free space before deployment. Defaults to true.
installer_initialize_api_retries: Retries while waiting for the installer UI/API to come up. Defaults to 180.
installer_initialize_api_retries_delay: Delay (seconds) between initialize retries. Defaults to 10.
installer_api_retries: Retries for regular installer API calls. Defaults to 5.
installer_api_retries_delay: Delay (seconds) between API retries. Defaults to 10.
installer_validation_api_retries: Retries while polling spec validation status. Defaults to 360.
installer_validation_api_retries_delay: Delay (seconds) between validation polls. Defaults to 10.
installer_depot_sync_retries: Retries while waiting for the depot sync to reach SYNCED. Defaults to 90.
installer_download_wait_cycles: Number of download-status polls to wait for binary downloads to complete (one poll + progress line per cycle). Defaults to 240 (~4h at the default poll interval).
installer_download_poll_interval: Seconds to pause between bundle download-status polls. Defaults to 60.
installer_download_token_reauth_every: Refresh the installer API token every N download poll cycles (the token expires during long downloads). Defaults to 10.
installer_bringup_wait_cycles: Wait cycles (~10 minutes each, re-authenticating) for bring-up completion. Defaults to 72.
```

```yaml
# Ansible debug tasks, very useful for troubleshooting.
validation_debug: Boolean to enable or disable the execution of debug tasks for validation and troubleshooting. Defaults to false.
# Print ESXi host facts
esxi_print_facts: Boolean to enable or disable printing ESXi host facts for debugging purposes. Defaults to validation_debug | default(false).
# Print ESXi host SSH thumbprints
esxi_print_ssh_thumbprints: Boolean to enable or disable printing ESXi host SSH thumbprints for debugging purposes. Defaults to validation_debug | default(false).
# Print ESXi host SSL thumbprints
esxi_print_ssl_thumbprints: Boolean to enable or disable printing ESXi host SSL thumbprints for debugging purposes. Defaults to validation_debug | default(false).
# Print vmnic to physical NIC mapping
debug_vmnic_mapping: Boolean to enable or disable debugging of vmnic to physical NIC mapping. Defaults to validation_debug | default(false).
```
