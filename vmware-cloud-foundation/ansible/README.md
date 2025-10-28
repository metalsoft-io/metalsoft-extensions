# VMware Cloud Foundation (VCF)

Ansible playbooks and roles for deploying and managing VMware Cloud Foundation (VCF) environments.

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
# Proxy Configuration Variables
# If your environment requires a proxy for Internet access, you can configure the following variables:
proxy_enabled: Boolean to enable or disable proxy settings.
proxy_host: The hostname of the proxy server.
proxy_port: The port number of the proxy server. Defaults to 3128.
proxy_username: The username for proxy authentication.
proxy_password: The password for proxy authentication.
proxy_transfer_protocol: The protocol used for proxy communication (HTTP or HTTPS). Defaults to HTTPS.
```

```yaml
# The following groups of variables are mutually exclusive

# Provide only the full URL to the VCF OVA file.
ova_url: The URL from which to download the VCF OVA file.

# Alternatively, provide the base URL of the repository containing the VCF OVA file.
# This group of variables will construct the ova_url automatically using the following pattern:
# repository_base_url + '/.vmware/vcf/' + vcf_version + '/' + ova_name
repository_base_url: The base URL of the repository containing the VCF OVA file.
vcf_version: The version of VCF to deploy. Defaults to '5.2.2'.
ova_name: The name of the VCF OVA file. Defaults to 'VMware-Cloud-Builder-5.2.2.0-24936865_OVF10.ova'.
```

```yaml
# Deployment architecture model.
# The models require different extension definitions.
deployment_architecture_model: Options include 'consolidated', 'standard'. Defaults to 'consolidated'.

# Deployment platform model.
# Only 'VCF' is currently supported.
deployment_platform: Options include 'VCF' or 'VCF_VXRAIL'. Defaults to 'VCF'.

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
```

```yaml
# Distributed vSphere switch version.
distributed_vsphere_switch_version: The version of the distributed vSphere switch to deploy. Defaults to '8.0.0'.

# NSX Manager size.
# One of: medium, large, xlarge.
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
# vCenter Cluster Name.
vcenter_cluster_name: The name of the vCenter Server cluster. Defaults to '<sddc_id>-cl1'.

# vCenter virtual machine size.
# One of: xlarge, large, medium, small, tiny.
vcenter_vm_size: The size of the vCenter Server VM. Defaults to 'small'.

# vCenter virtual machine storage size.
# One of: lstorage, xlstorage.
storage_size: The size of the vCenter Server VM storage. Defaults to 'lstorage'.

# The name of the VM folder for management VMs.
management_vm_folder_name: The name of the VM folder for management VMs. Defaults to 'm-fd-mgmt'.
# The name of the VM folder for networking VMs.
networking_vm_folder_name: The name of the VM folder for networking VMs. Defaults to 'm-fd-nsx'.

# List of Resource Pool Specifications.
management_resource_pool_name: The name of the resource pool for management VMs. Defaults to '<sddc_id>-cl1-rp-sddc-mgmt'.
networking_resource_pool_name: The name of the resource pool for networking VMs. Defaults to '<sddc_id>-cl1-rp-sddc-edge'.
compute_user_vm_resource_pool_name: The name of the resource pool for user VMs. Defaults to '<sddc_id>-cl1-rp-user-vm'.
compute_user_edge_resource_pool_name: The name of the resource pool for user edge VMs. Defaults to '<sddc_id>-cl1-rp-user-edge'.
```

```yaml
# vSAN architecture model.
vsan_esa_enabled: Boolean to specify if the vSAN ESA architecture is used. Defaults to false.
# vSAN deduplication and compression feature flag (single flag controls both features)
vsan_dedup_enabled: Boolean to specify if vSAN deduplication and compression is enabled. Defaults to false.
# vSAN datastore name.
vsan_datastore_name: The name of the vSAN datastore. Defaults to '<sddc_id>-cl1-ds1'.
```

```yaml
# Enable VCF Customer Experience Improvement Program (CEIP).
ceip_enabled: Boolean to specify if CEIP is enabled. Defaults to false.

# Enable Federal Information Processing Standards (FIPS) mode.
fips_enabled: Boolean to specify if FIPS mode is enabled. Defaults to false.

# Skip ESXi thumbprint validation (sshThumbprint and sslThumbprint).
# If false, sshThumbprint and sslThumbprint will be automatically collected from ESXi hosts.
skip_esx_thumbprint_validation: Whether to skip ESXi thumbprint validation. Defaults to false.
```

```yaml
# License key management.
# If license keys are not provided, the deployment will proceed without them.
license_esxi: License key for ESXi hosts.
license_vsan: License key for vSAN.
license_nsx: License key for NSX-T.
license_vcenter: License key for vCenter Server.

# If this variable is set to false, the deployment will fail if license keys are not provided.
deploy_without_license_keys: Boolean to specify if the deployment should proceed without license keys. Defaults to true.
```

```yaml
# Cloud Builder Appliance (CBA) configuration.
cba_admin_password: The password for the Cloud Builder Appliance (CBA) admin user.
cba_root_password: The password for the Cloud Builder Appliance (CBA) root user.

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
