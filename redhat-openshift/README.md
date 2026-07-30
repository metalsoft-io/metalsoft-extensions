# RedHat OpenShift

This directory contains the MetalSoft extension definition (application kind) and the Ansible playbooks used to deploy and manage RedHat OpenShift on bare-metal infrastructure, using the [agent-based installer](https://docs.redhat.com/en/documentation/openshift_container_platform/4.19/html/installing_an_on-premise_cluster_with_the_agent-based_installer/index).

For details on MetalSoft extensions, see the official [documentation](https://docs.metalsoft.io/en/latest/content/developer_resources/extensions).

## Repository layout

| Path | Purpose |
| --- | --- |
| `extension.json` | The extension definition registered on the MetalSoft controller |
| `ansible/` | The Ansible bundle (playbooks + `agent-based` role) packaged as a zip |
| `execution-environment-<version>.yml` | `ansible-builder` definitions for the execution environment image, one per supported OCP version |

## Adapting `extension.json` to your environment

The definition in this repository is a template — several values are environment-specific and **must** be changed before registering it on your controller:

### Network profile

`infrastructure.logicalNetworks[].profileLabel` is set to the placeholder `network-profile-name`. Replace it with the label of a logical network profile that an operator has already created at the target site — the profile is deployment-specific and the extension will fail to deploy if the label does not resolve. The same logical network (`openshift-network`) is attached untagged to both instance arrays (`cp` and `compute`) and carries the two cluster VIP allocations (`api-vip`, `ingress-vip`).

### Input default values

Set the input defaults so they reflect your environment instead of forcing every operator to override them at instance-create time:

| Input | Default in this repo | What to change |
| --- | --- | --- |
| `pull_secret` | `REDACTED` | Set to a valid Red Hat pull secret (from [console.redhat.com](https://console.redhat.com/openshift/downloads)). For public-registry installs it must contain a `quay.io` auth entry — the deploy playbook validates this up front. Default can be left `REDACTED` so as not so share sensitive information |
| `use_private_registry` | `false` | Set to `true` if your environment installs from a private mirror instead of the official Red Hat registries (air-gapped setups). Make sure to set the `pull_secret` acordingly, with credentials for your private registry |
| `mirror_registry` | `registry.metalsoft.dev/ocp4/openshift4` | Point at your own mirror registry (host + namespace path). Only used when `use_private_registry` is `true`. |
| `ocp_version` | `4.19.0` | The OpenShift version to install. Must match a version your execution environment image was built for (see below). You will need particular Execution Environment built for the particular version|
| `mtu` | `1500` | Match the MTU of the underlying network. |
| `cluster_network` / `service_network` | `10.128.0.0/14` / `172.30.0.0/16` | Change only if these CIDRs overlap with existing networks in your environment. |
| `control_plane_nodes` | `3` | Number of control-plane nodes. `setOnly` — it cannot be changed after creation. Set to `1` (with `compute_nodes: 0`) for a single-node cluster. |
| `compute_nodes` | `0` | Initial number of workers. This is the input operators change later to scale the cluster (see Scaling below). |

### DNS records

The VIP allocations declare the cluster DNS records using placeholders resolved by the platform: `{{CLUSTER_NAME}}` (the extension instance name) and `{{default_zone_name}}` (the site's default DNS zone). The records created are `api.<cluster>.<zone>` (with PTR), `api-int.<cluster>.<zone>`, and `*.apps.<cluster>.<zone>`. The site's default zone must be authoritative — the playbooks build all cluster FQDNs from `extensionInstanceRecordSet.baseDomain`, so the URLs only work if the records the platform creates actually resolve.

**ATTENTION**: a DNS provisioning extension is required to exist in Metalsoft, so that OpenSHift needed records are created and resolvable by the nodes. Examples can be found in this repo for powerdns and infoblox

### Site config vars

`configVars.DNSResolvers` (default `1.1.1.1`) is an operator-set, site-level value: the DNS resolvers written into the cluster's install configuration. Set it to your site's internal resolvers (comma-separated string accepted) — the playbooks prefer it over the recordSet resolvers, which can be stale or public. **These resolvers are set on the all OCP nodes and MUST be capable to resolve the created records**

### Asset URLs

Both entries in `assets[]` must point at artifacts **you** host (see the next two sections):

- `openshift-ansible-bundle` — the URL of the Ansible bundle zip.
- `ee-redhat-openshift` — the execution environment image reference (`repositoryRegistry`, `namespaceRegistry`, `tagRegistry`) and the URL of the image tarball.

### Registering the definition

Once adapted, register and publish with `metalcloud-cli`:

```bash
metalcloud-cli extension create "Red Hat OpenShift" application \
    "Red Hat OpenShift cluster" --definition-source extension.json
metalcloud-cli extension publish <id_or_label>
```

Extensions are created as drafts; only drafts can be updated in place. Once published, update with new version increment, or archive and recreate to change the definition.

## Building and hosting the Ansible bundle

The runtime does not read the `ansible/` directory from git — the playbooks are delivered as a **zip bundle** fetched from the URL declared in the `openshift-ansible-bundle` asset.

Two rules matter when creating the zip:

1. **Playbooks must sit at the archive root** (no wrapper directory) — the runner unzips the bundle into its project directory and runs the requested playbook by bare filename.
2. Never ship a file named `job.yml` — the runner renames the requested playbook to that reserved name.

Build it from inside the `ansible/` directory:

```bash
cd ansible
zip -r ../redhat-openshift-v1.0.1.zip . -x '*.DS_Store' -x '*.zip' -x 'README.md'
unzip -l ../redhat-openshift-v1.0.1.zip   # deploy.yaml, scale.yaml, roles/ must be at top level
```

Then upload the zip to an **HTTP(S) repository server reachable by the global MetalSoft controller** (the controller downloads it from there — there is no bundle-upload CLI command) and set that URL (max 128 characters) as the `url` of the `openshift-ansible-bundle` asset. The convention used here is:

```
https://repo.metalsoft.io/.extensions_ms/redhat-openshift/redhat-openshift-v<version>.zip
```

Bump the version in the filename on every change — re-uploading under the same name risks serving a cached/stale bundle, which makes fixes appear to "not take".

## Execution environment

The lifecycle tasks run inside a container image (an ansible-runner **execution environment**) on the site controller. Every task in `extension.json` references the `ee-redhat-openshift` asset, so the playbooks run in this purpose-built image rather than the site controller's default EE.

The image is defined by the `execution-environment-<version>.yml` files in this directory and built with [`ansible-builder`](https://ansible.readthedocs.io/projects/builder/). Besides the Ansible collections and Python deps, it bakes in everything the playbooks shell out to — notably the **`openshift-install`, `oc` and `kubectl` binaries pinned to a specific OCP version** (the `OCP_VERSION` build arg), plus `jq`, `curl`, and `nmstate`. This is why there is one EE definition per supported OpenShift version (`4.17.15`, `4.19.0`): **the EE image version must match the `ocp_version` input** of the instances it serves.

Important: the yml file itself is **not** read at runtime — only the built image matters. 
-
Build, then upload:


```bash
ansible-builder build -f execution-environment-4-19-0.yml -t registry.metalsoft.dev/ee-ocd-4-19:4-19
docker save registry.metalsoft.dev/ee-ocd-4-19:4-19 | gzip > ee-ocd-4-19_v1.0.0.tar.gz
```

Upload the resulting tarball to the HTTP repo server and set its URL as the `ee-redhat-openshift` asset's `url`. The image must end up in a **container registry reachable by the site controller** (load the tarball there with `docker load -i ee-ocd-4-19_v1.0.0.tar.gz` and push it), and the asset's `repositoryRegistry` / `namespaceRegistry` / `tagRegistry` fields must match that registry location.

## Outputs

The extension declares four outputs, populated by the playbooks once the installation completes and visible on the extension instance in the MetalSoft UI:

| Output | Content |
| --- | --- |
| `cluster_kubeconfig` | The admin kubeconfig for the cluster |
| `cluster_kubeadmin_password` | The initial `kubeadmin` password |
| `api_url` | `https://api.<cluster>.<zone>:6443` |
| `console_url` | `https://console-openshift-console.apps.<cluster>.<zone>` |

Mechanically, a playbook returns outputs by writing a `context.json` artifact whose top-level keys match the declared output labels; the platform stores them on the instance and re-injects them into later runs, which is how the scale playbooks recover the kubeconfig long after the deployment that generated it.

One platform behavior shapes the playbooks here: **stored outputs are replaced on every successful run**, and a run that writes no `context.json` wipes them. Every lifecycle playbook therefore ends by re-emitting the full outputs payload when it hasn't already written one (see `preserve-outputs.yaml`) — keep that pattern intact when modifying the bundle, or a no-op edit or scale-in run will silently erase the stored cluster credentials.

## Scaling (scale out / scale in)

Scaling is driven entirely by editing the **`compute_nodes`** input on the deployed extension instance — increase it to add workers, decrease it to remove them. `control_plane_nodes` is immutable (`setOnly`), and `scale.yaml` explicitly refuses any control-plane scale request.

When the operator saves the edit, the platform adjusts the infrastructure and runs the `onEdit` lifecycle. The same `scale.yaml` playbook is registered at both stages and self-selects what to do via the platform-generated inventory groups `compute_scale_out` / `compute_scale_in` (empty groups make the corresponding play a no-op):

**Scale in — `onEdit` / `preDeploy` (`scale.yaml`):** runs while the outgoing servers are still provisioned. For each host in `compute_scale_in` (serially), it follows the Red Hat node-removal procedure against the cluster API: `oc adm cordon` → `oc adm drain` → `oc delete node`. After the stage completes, the platform deprovisions and releases the servers. A node already absent from the cluster is treated as done, so retries are safe.

**Scale out — `onEdit` / `postDeploy` (`scale.yaml`, then `scale-monitor.yaml`):** once the new servers are provisioned, `scale.yaml` generates a day-2 node ISO with `oc adm node-image create` (which runs a node-joiner pod inside the existing cluster) and returns a `mount-and-boot` request via `context.json`, booting the new workers from that ISO. `scale-monitor.yaml` then watches the join: it approves the pending CSRs for the new nodes, polls until every host in `compute_scale_out` reports `Ready` (up to 60 minutes), ejects the mounted ISO, and re-emits the outputs.

Notes:

- The scale playbooks authenticate using the `cluster_kubeconfig` output persisted at install time — the initial deployment must have completed successfully before the cluster can be scaled.
- At `preDeploy` the scale-out hosts can already appear in inventory before the servers are provisioned (no IP allocation data yet); the scale-out play detects this and defers to the `postDeploy` run.
- An edit that changes no instance counts runs both stages as no-ops (the outputs-preservation play still runs, so nothing is lost).
