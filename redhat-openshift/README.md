# RedHat OpenShift

This directory contains the MetalSoft extension definition (application kind) and the Ansible playbooks used to deploy and manage RedHat OpenShift on bare-metal infrastructure, using the [agent-based installer](https://docs.redhat.com/en/documentation/openshift_container_platform/4.22/html/installing_an_on-premise_cluster_with_the_agent-based_installer/index).

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
| `cluster_network` / `service_network` | `10.128.0.0/14` / `172.30.0.0/16` | Change only if these CIDRs overlap with existing networks in your environment. |
| `control_plane_nodes` | `3` | Number of control-plane nodes. `setOnly` — it cannot be changed after creation. Set to `1` (with `compute_nodes: 0`) for a single-node cluster. |
| `compute_nodes` | `0` | Initial number of workers. This is the input operators change later to scale the cluster (see Scaling below). |

### DNS records

The VIP allocations declare the cluster DNS records using placeholders resolved by the platform: `{{CLUSTER_NAME}}` (the extension instance name) and `{{default_zone_name}}` (the site's default DNS zone). The records created are `api.<cluster>.<zone>` (with PTR), `api-int.<cluster>.<zone>`, and `*.apps.<cluster>.<zone>`. The site's default zone must be authoritative — the playbooks build all cluster FQDNs from `extensionInstanceRecordSet.baseDomain`, so the URLs only work if the records the platform creates actually resolve.

**ATTENTION**: a DNS provisioning extension is required to exist in Metalsoft, so that OpenSHift needed records are created and resolvable by the nodes. Examples can be found in this repo for powerdns and infoblox

### Site config vars

Admin/site-level settings live in `configVars` and are set **once per site** by an operator (Extension Site Config), not per deployment. The extension must be enabled and its site config saved on the target site **before the first deploy**. Values reach the playbooks as `configVars.<label>`.

| Config var | Default in this repo | What to change |
| --- | --- | --- |
| `DNSResolvers` | `1.1.1.1` | The DNS resolvers written into the cluster's install configuration. Set it to your site's internal resolvers (comma-separated string accepted) — the playbooks prefer it over the recordSet resolvers, which can be stale or public. **These resolvers are set on all OCP nodes and MUST be capable to resolve the created records.** |
| `pull_secret` | `REDACTED` | Set to a valid Red Hat pull secret (from [console.redhat.com](https://console.redhat.com/openshift/downloads)), pasted either as the raw JSON or base64-encoded — the playbooks accept both. For public-registry installs it must contain a `quay.io` auth entry — the deploy playbook validates this up front. Default can be left `REDACTED` so as not to share sensitive information. |
| `use_private_registry` | `false` | Set to `true` if your environment installs from a private mirror instead of the official Red Hat registries (air-gapped setups). Make sure to set the `pull_secret` accordingly, with credentials for your private registry. |
| `mirror_registry` | `registry.metalsoft.dev/ocp4/openshift4` | Point at your own mirror registry (host + namespace path). Only used when `use_private_registry` is `true`. The release images must be mirrored there first — see "Mirroring the release images to a private registry" below. |
| `ocp_version` | `4.22.13` | The OpenShift version to install. Must match a version your execution environment image was built for (see below). You will need a particular Execution Environment built for the particular version. |
| `mtu` | `1500` | Match the MTU of the underlying network. |

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
zip -r ../redhat-openshift-v1.3.1.zip . -x '*.DS_Store' -x '*.zip' -x 'README.md'
unzip -l ../redhat-openshift-v1.3.1.zip   # deploy.yaml, scale.yaml, roles/ must be at top level
```

Then upload the zip to an **HTTP(S) repository server reachable by the global MetalSoft controller** (the controller downloads it from there — there is no bundle-upload CLI command) and set that URL (max 128 characters) as the `url` of the `openshift-ansible-bundle` asset. The convention used here is:

```
https://repo.metalsoft.io/.extensions_ms/redhat-openshift/redhat-openshift-v<version>.zip
```

Bump the version in the filename on every change — re-uploading under the same name risks serving a cached/stale bundle, which makes fixes appear to "not take".

## Execution environment

The lifecycle tasks run inside a container image (an ansible-runner **execution environment**) on the site controller. Every task in `extension.json` references the `ee-redhat-openshift` asset, so the playbooks run in this purpose-built image rather than the site controller's default EE.

The image is defined by the `execution-environment-<version>.yml` files in this directory and built with [`ansible-builder`](https://ansible.readthedocs.io/projects/builder/). Besides the Ansible collections and Python deps, it bakes in everything the playbooks shell out to — notably the **`openshift-install`, `oc` and `kubectl` binaries pinned to a specific OCP version** (the `OCP_VERSION` build arg), plus `jq`, `curl`, `nmstate`, and `rsync` (required by `oc adm node-image create` during scale-out to copy the generated node ISO out of the node-joiner pod — without it, `oc` falls back to a tar-based copy that fails against 4.22's stricter tools image). This is why there is one EE definition per supported OpenShift version (`4.17.15`, `4.19.0`, `4.22.10`, `4.22.13`): **the EE image version must match the `ocp_version` site config var** of the instances it serves.

Important: the yml file itself is **not** read at runtime — only the built image matters. 
-
Build, then upload:


```bash
ansible-builder build -f execution-environment-4-22-13.yml -t registry.metalsoft.dev/ee-ocd-4-22:4-22.13
docker save registry.metalsoft.dev/ee-ocd-4-22:4-22.13 | gzip > ee-ocd-4-22-13_v1.0.0.tar.gz
```

The image must be `linux/amd64` — when building on Apple Silicon / ARM, add `--container-runtime docker --extra-build-cli-args "--platform=linux/amd64"` and verify with `docker image inspect registry.metalsoft.dev/ee-ocd-4-22:4-22.13 --format '{{.Architecture}}'`.

**Treat EE tags as immutable — use a NEW tag (and a new tarball filename) for every rebuild**, even a rebuild for the same OCP version. The site controller agent caches EE images by tag with no digest check: if the tag already exists in its local Docker daemon the pull is skipped, and a stale tarball cached under `/opt/metalsoft/ansible-archives` can re-instate the old image even after a `docker rmi`. Reusing a tag makes EE fixes silently "not take".

Upload the resulting tarball to the HTTP repo server and set its URL as the `ee-redhat-openshift` asset's `url`. The image must end up in a **container registry reachable by the site controller** (load the tarball there with `docker load -i ee-ocd-4-22-13_v1.0.0.tar.gz` and push it), and the asset's `repositoryRegistry` / `namespaceRegistry` / `tagRegistry` fields must match that registry location.

## Mirroring the release images to a private registry

For air-gapped installs (`use_private_registry: true`), the OpenShift release images must be duplicated into the registry named by the `mirror_registry` config var **before deploying**. Run this on a machine that can reach both quay.io and the mirror registry, with `oc`, `skopeo` and `jq` installed.

### Step 1 — build the auth file (`auth-mirror.json`)

The auth file must contain **both** ends: the Red Hat pull secret (auths for quay.io,
registry.redhat.io, …) to *read* the release, and a **push-capable** credential for the
mirror registry to *write* it. `oc -a` / skopeo `--authfile` use ONLY this file — an
existing `docker login` on the machine is never consulted.

```bash
OCP_VERSION=4.22.13                                       # must match the ocp_version config var
MIRROR_REGISTRY=registry.metalsoft.dev/ocp4/openshift4    # must match the mirror_registry config var

# 1. Download the Red Hat pull secret from
#    https://console.redhat.com/openshift/downloads ("Pull secret") → pull-secret.json

# 2a. With podman — just log in on top of it:
podman login --authfile pull-secret.json "${MIRROR_REGISTRY%%/*}"
cp pull-secret.json auth-mirror.json

# 2b. With docker (docker login has no --authfile) — merge the entry yourself.
#     NOTE the `tr -d '\n'`: GNU coreutils base64 (default on macOS with homebrew)
#     line-wraps at 76 chars, which silently corrupts the auth entry — the registry
#     then treats you as ANONYMOUS (Harbor issues a token with empty actions).
AUTH=$(printf '%s:%s' '<user>' '<password>' | base64 | tr -d '\n')
jq --arg a "$AUTH" '.auths["'"${MIRROR_REGISTRY%%/*}"'"] = {auth: $a}' pull-secret.json > auth-mirror.json
chmod 600 auth-mirror.json
```

The account must hold a push-capable role on the mirror project (Harbor: **Developer or
above**, or a robot account). A valid login *without* project membership fails every
upload with `unauthorized ... action: push`.

### Step 2 — verify the credential before moving 20+ GiB

```bash
jq '{auths: (.auths | keys)}' auth-mirror.json    # both quay.io and the mirror host must be listed

# Harbor push-scope probe: decodes the token Harbor would issue for a push
AUTH=$(jq -r '.auths["'"${MIRROR_REGISTRY%%/*}"'"].auth' auth-mirror.json)
curl -sk -H "Authorization: Basic $AUTH" \
  "https://${MIRROR_REGISTRY%%/*}/service/token?service=harbor-registry&scope=repository:${MIRROR_REGISTRY#*/}:pull,push" \
| jq -r .token | cut -d. -f2 | tr '_-' '/+' \
| python3 -c "import sys,base64,json; s=sys.stdin.read().strip(); s+='='*(-len(s)%4); d=json.loads(base64.b64decode(s)); print('subject:', d.get('sub'), '| granted:', d.get('access'))"
```

Expected: `subject: <your user>` and `actions` containing `pull` and `push`.
Failure signatures: `subject: None` = the credential was rejected (stale password or the
base64-wrap corruption above — Harbor still returns HTTP 200 with an *anonymous* token, so
a 200 proves nothing); a valid subject with `actions: []` = missing project role.

### Step 3 — mirror the release

```bash
oc adm release mirror \
  --from=quay.io/openshift-release-dev/ocp-release:${OCP_VERSION}-x86_64 \
  --to=${MIRROR_REGISTRY} \
  --to-release-image=${MIRROR_REGISTRY}:${OCP_VERSION} \
  -a auth-mirror.json
```

Recent `oc` versions (4.22+) print two deprecation warnings when running this — both are expected and harmless here:

- `Command "mirror" is deprecated ... Use oc-mirror instead` — `oc adm release mirror` keeps working throughout 4.x (removal is announced for 6.0). Don't switch this extension to `oc-mirror`: its v2 mode mirrors into a different multi-repository layout and generates `ImageDigestMirrorSet` manifests, which does not match what the playbooks depend on (a single mirror repository, the `:<ocp_version>` release tag, and the `imageContentSources` entries they template into `install-config.yaml`). Moving to `oc-mirror` would require reworking the bundle first.
- `Flag --print-mirror-instructions's value 'icsp' has been deprecated` — this only affects the sample instructions the command prints at the end; the extension ignores them and templates its own `imageContentSources`, so no action is needed.

Three details the playbooks depend on:

- `--to-release-image=${MIRROR_REGISTRY}:${OCP_VERSION}` is required: the deploy playbook sets `OPENSHIFT_INSTALL_RELEASE_IMAGE_OVERRIDE=<mirror_registry>:<ocp_version>`, so the release image must exist under exactly that tag (without the `-x86_64` suffix the source tag carries).
- Everything is mirrored into the **single** `mirror_registry` repository — this matches the `imageContentSources` the playbooks write into `install-config.yaml`, which map both `quay.io/openshift-release-dev/ocp-release` and `quay.io/openshift-release-dev/ocp-v4.0-art-dev` to it.
- The deploy playbook preflights the mirror by looking up the release image **digest** (taken from the `openshift-install` binary baked into the EE) in the mirror's `/v2/` API, using the `pull_secret` credentials — so the mirrored content must come from the same release the EE was built for, and the site's `pull_secret` config var must include an auth entry for the mirror registry host. If the digest is missing, the deploy fails early with the exact `oc adm release mirror` command to re-sync.

When bumping to a new OpenShift version, re-run the mirror command with the new `OCP_VERSION` — existing tags/blobs are left in place, so multiple versions can coexist in the same mirror repository.

### Sigstore signatures (required for OCP 4.22+)

Since OpenShift 4.22 the default `openshift` cluster image policy **enforces sigstore
signature verification** on the release image repositories. Nodes look up the signature
as a `sha256-<digest>.sig` tag in the same repository they pull the image from — i.e. in
your mirror — and reject the image if it is missing, failing first-boot with
`Source image rejected: A signature was required, but no signature exists`
(masters then time out in the `Configuring` stage).

`oc adm release mirror` does **not** copy these signatures. After mirroring (step 3 above,
same `auth-mirror.json`), copy them with skopeo (they are tiny — this takes minutes):

```bash
# 1. the release image's own signature
REL=$(oc adm release info -a auth-mirror.json quay.io/openshift-release-dev/ocp-release:${OCP_VERSION}-x86_64 -o jsonpath='{.digest}')
skopeo copy --src-authfile auth-mirror.json --dest-authfile auth-mirror.json \
  docker://quay.io/openshift-release-dev/ocp-release:${REL/sha256:/sha256-}.sig \
  docker://${MIRROR_REGISTRY}:${REL/sha256:/sha256-}.sig

# 2. every component image's signature
oc adm release info -a auth-mirror.json quay.io/openshift-release-dev/ocp-release:${OCP_VERSION}-x86_64 \
  -o jsonpath='{range .references.spec.tags[*]}{.from.name}{"\n"}{end}' \
| awk -F@ '{print $2}' | sort -u | while read d; do
  TAG="${d/sha256:/sha256-}.sig"
  skopeo copy --src-authfile auth-mirror.json --dest-authfile auth-mirror.json \
    docker://quay.io/openshift-release-dev/ocp-v4.0-art-dev:${TAG} \
    docker://${MIRROR_REGISTRY}:${TAG} || echo "MISSING SIG: $d"
done

# spot-check one signature landed in the mirror:
skopeo inspect --authfile auth-mirror.json docker://${MIRROR_REGISTRY}:${REL/sha256:/sha256-}.sig | head -3
```

Caveat on the loop's `MISSING SIG` lines: they only mean *that iteration's skopeo copy
failed* — read the skopeo error above each one. `credentials can't be empty` or
`authentication required` = your auth setup is broken and **nothing was checked**;
only a source-side `manifest unknown` means quay genuinely has no signature for that
digest. Delete `auth-mirror.json` (and `pull-secret.json`) when done — they hold live
credentials.

Alternatively, mirror with `oc-mirror` v2, which copies sigstore signatures by default —
but note its different repository layout does not match this extension's
`imageContentSources`/release-tag contract without rework (see the deprecation note above).

The deploy playbook preflights this: for `ocp_version >= 4.22` with `use_private_registry`
it checks that the signature manifests for the release image and the
machine-config-operator image exist in the mirror, and fails immediately with
re-sync instructions if they are absent.

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
