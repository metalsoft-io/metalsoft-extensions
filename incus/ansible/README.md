# Incus

This repository contains the Ansible playbooks and roles for deploying an Incus cluster, a modern, secure, and powerful system container and virtual machine manager. The playbooks are designed to be modular and reusable, allowing for easy customization and extension.
The current implementation of the Ansible playbooks and roles provides the initial deployment of the Incus cluster on bare-metal servers, scale-up and scale-down of the cluster nodes, and upgrade of the Incus cluster nodes.

## Variables

These variables can be customized in the `extension.json` file under the `inputs` section to suit specific deployment requirements.

Key variables include:

```bash
cluster_enabled: Boolean to enable or disable the way Incus is deployed. Default is true.

branch_release: The release branch of Incus to deploy. Default is "stable".

cluster_node_dns_servers: List of DNS servers for the cluster nodes. Optional. This can be used to override the default DNS servers coming from the MetalSoft.

ui_installing: Boolean to enable or disable the installation of the Incus UI. Default is true.

storage_driver: The storage driver to use for Incus. Default is "dir".

core_https_port: The HTTPS port for the Incus core service. Default is 8443.

# https://linuxcontainers.org/incus/docs/main/howto/cluster_config_networks/#separate-rest-api-and-clustering-networks
separate_api_and_cluster_traffic: Boolean to enable or disable separation of API and cluster traffic. Default is false.

# https://linuxcontainers.org/incus/docs/main/image-handling/#auto-update
images_auto_update_interval: Interval for automatic image updates. Default is "6 hours".

cluster_member_upgrade_enabled: Boolean to enable or disable upgrade of cluster members. Default is false. Can be used to control when to upgrade cluster members.

cluster_member_force_remove_enabled: Boolean to enable or disable force removal of cluster members. Default is false. Useful in scenarios where a node is unresponsive.

vars_debugging_enabled: Boolean to enable or disable debugging output for Ansible playbooks. Default is false.
```
