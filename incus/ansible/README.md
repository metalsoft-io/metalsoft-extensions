# Incus

This directory contains the Ansible playbooks and roles for deploying an Incus cluster in conjunction with the MetalSoft extension defined in this directory.
The playbooks are designed to be modular and reusable, allowing for easy customization and extension.
The current implementation provides the initial deployment of the Incus cluster on bare-metal servers, scale-out and scale-in of the cluster nodes, upgrade of the cluster nodes, and publishing of the extension outputs.

## Playbooks

- `deploy.yaml` (onCreate postDeploy): installs Incus on all nodes, bootstraps the first server, joins the remaining nodes serially, publishes outputs.
- `scale.yaml` (onEdit preDeploy + postDeploy): plays self-select via the platform-generated `incus_scale_out` / `incus_scale_in` groups — scale-in is drained/removed at preDeploy while still reachable, scale-out is installed/joined at postDeploy. Always re-publishes outputs (even on a no-op run — a successful run that writes no context.json would wipe the stored outputs).
- `upgrade.yaml` (onEdit postDeploy, before scale): serially upgrades surviving members when `cluster_member_upgrade_enabled` is set. Always re-publishes outputs.

## Variables

Site-level settings arrive from the Extension Site Config as `configVars.<label>`; per-deployment settings arrive as `extensionInstanceVariables.<label>`. All consumption goes through `roles/incus/defaults/main.yaml`, which resolves configVars first and keeps a legacy `extensionInstanceVariables` fallback so the bundle also works against instances deployed from the pre-configVars definition.

Site config (`configVars`): `DNSResolvers`, `branch_release`, `images_auto_update_interval`, `core_https_port`, `separate_api_and_cluster_traffic`, `cluster_member_upgrade_enabled`, `cluster_member_force_remove_enabled`, `vars_debugging_enabled`.

Per-deployment inputs: `cluster_server_type`, `cluster_instance_count`, `cluster_node_os_template`, `cluster_enabled`, `install_ui`, `storage_driver`.

See the top-level [README](../README.md) for the full variable tables, outputs, packaging and registration steps.

## Outputs

`roles/incus/tasks/emit-outputs.yaml` writes the declared extension outputs to the runner's `artifacts/<ident>/context.json`. The platform REPLACES the stored outputs with every successful run's context.json, so every playbook ends with a `Publish extension outputs` play on localhost that re-emits the full payload when the run hasn't already written one.

## Tests

```bash
cd ../tests && ansible-playbook -i inventory.yaml render-spec.yaml
```
