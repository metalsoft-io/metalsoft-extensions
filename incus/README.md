# Incus

This directory contains the MetalSoft extension definition (application kind) and the Ansible playbooks used to deploy and manage [Incus](https://linuxcontainers.org/incus/docs/main/) on bare-metal infrastructure.

For details on MetalSoft extensions, see the official [documentation](https://docs.metalsoft.io/developer_resources/extensions/).

## Prerequisites

- A MetalSoft environment with bare-metal hosts prepared for Incus deployment.
  - At least one host is required for a basic Incus deployment.
  - Each host must have a healthy hardware status with no errors.
  - Each host must provide a minimum of two network interfaces.
- OS templates for Incus (see MetalSoft Ubuntu templates: <https://github.com/metalsoft-io/os-templates/tree/main/Ubuntu/24.04>).

## Configuration

The configuration is primarily driven by the `extension.json` file, which defines various parameters for the deployment.

Key variables that define the MetalSoft infrastructure are:

```yaml
cluster_server_type: Represents the server type for the Incus cluster.
cluster_instance_count: Number of nodes in the Incus cluster (default and minimum: 1).
cluster_node_os_template: OS template name for Incus cluster nodes.
```

Details about the input variables for the Incus deployment can be found in the [Ansible README](ansible/README.md).
