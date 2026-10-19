# VMware vCenter Server 9

Application extension that installs ESXi 9 on one or more bare-metal servers through a MetalSoft OS template,
deploys a vCenter Server Appliance (vCSA) 9 onto the first host with `vcsa-deploy`, and (optionally) creates a
datacenter and cluster in the new vCenter with every host in it. Changing the `esxi_host_count` input of the
extension instance and deploying adds or removes hosts (see **Scaling**).

| Path | Purpose |
| --- | --- |
| `extension.json` | Extension definition registered on the controller |
| `ansible/` | Ansible bundle (`deploy.yaml` onCreate; `scale-in.yaml` onEdit preDeploy, `scale-out.yaml` onEdit postDeploy), zipped with playbooks at the root |
| `execution-environment.yml` | `ansible-builder` definition of the EE image |
| `tests/` | Offline tests of the `vcsa-deploy` install spec and of the scale logic (no infrastructure needed) |
| `tools/set-asset-urls.py` | Rewrites the bundle / EE URLs in `extension.json` for another mirror |

## Versions

| Component | Version / build |
| --- | --- |
| ESXi (OS template `esxi-9-25370933-standard`) | 9.1.0.0-25370933 |
| vCenter Server Appliance (`VMware-VCSA-all-9.1.0.0.25370922.iso`) | 9.1.0.0-25370922 |
| `vcsa-deploy` | 2.13.0.25234746 |

vCenter must be the same patch level as the ESXi host or newer. To use another vCSA build, serve its ISO and
point the `vcsa_iso_url` site config at it. Moving the ESXi template to a newer patch requires a vCSA at least
that new.

## Files and where they come from

Everything is plain HTTP(S) without authentication. The bundle and the EE image default to repo.metalsoft.io; the
vCSA ISO has no default: download it from VMware under your own entitlement and serve it yourself.

| File | Default URL | Set by |
| --- | --- | --- |
| Ansible bundle | `https://repo.metalsoft.io/.extensions_ms/vsphere-vcenter9/vsphere-vcenter9-v1.3.0.zip` | `assets[]` url, at registration |
| EE image tarball | `https://repo.metalsoft.io/.extensions_ms/ee/ee-vsphere-vcenter9.1.0.1.tar.gz` | `assets[]` url, at registration |
| vCSA installer ISO, `VMware-VCSA-all-9.1.0.0.25370922.iso` (12.8 GB) | none: your own server | site config `vcsa_iso_url` (mandatory) |

The platform requires literal URLs in `assets[]` (`definition.assets.0.url must be a URL address` for a
`{{configVars...}}` value), so the bundle and EE URLs are chosen when the extension is registered:

```bash
tools/set-asset-urls.py --bundle-url https://mirror.example/vsphere-vcenter9-v1.3.0.zip \
  --ee-url https://mirror.example/ee-vsphere-vcenter9.1.0.1.tar.gz > extension.mirror.json
```

The global controller fetches the bundle and the site controller the EE tarball and the ISO (the ISO from inside
the EE), so each URL must be reachable from there. URLs are limited to 128 characters.

## Deployment flow

1. MetalSoft provisions the `esxi_host_count` servers with the ESXi OS template and allocates the vCenter IP and
   DNS records.
   The management connection is redundant with `server-only-bond`: both NICs become `vSwitch0` uplinks
   (active/standby) under one management IP, and the switch ports are plain trunks. An LACP port-channel
   (`link-aggregation` / `distributed-link-aggregation`) is avoided because a standard vSwitch has no LACP and the
   MCLAG fallback can strand the host. Before this setting (1.0.1) the connection had
   `mode` without an implementation, so the host got one IP per NIC.
2. **ESXi preparation** (`esxi` role, every host): DNS, NTP, and the `VM Network` port group on the management VLAN.
   Steps 3-7 run against the **vCenter host**: the lowest-numbered instance (`vcsa_host`).
3. **Validation**: platform allocations present, vCenter password policy, and a forward +
   reverse DNS round-trip for the vCenter FQDN (vCenter firstboot fails without it).
4. **Probe**: if vCenter already answers, skip to step 8. If the VM exists but vCenter does not answer (an
   interrupted run), wait up to 30 minutes for firstboot, then fail asking the operator to delete the VM.
5. **Datastore**: the `datastore_name` input, or the accessible datastore with the most free space.
6. **Installer**: download the ISO from `vcsa_iso_url` (~12.8 GB), extract `vcsa-cli-installer` and `vcsa/`
   with `iso_extract.py` (pycdlib — containers cannot loop-mount), delete the ISO.
7. **Install**: merge our values into the ISO's own `embedded_vCSA_on_ESXi.json` (so `__version` and new keys
   track the installer), `vcsa-deploy install --verify-template-only`, then the real install (~30-60 min).
8. **Inventory** (optional): datacenter, cluster, every host added to the cluster by its management IP.
9. **Outputs**: `vcenter_url`, `vcenter_fqdn`, `vcenter_ip`, `vcenter_sso_username`.

A retried deployment re-runs the whole playbook; every step is idempotent or probe-guarded.

## Scaling

Change `esxi_host_count` on the extension instance (`PATCH /extension-instances/{id}/config` with
`{"inputVariables": [{"label": "esxi_host_count", "value": N}]}`, or the UI) and deploy the infrastructure.

- **Scale-out** (`scale-out.yaml`, onEdit postDeploy): MetalSoft installs the new hosts; the playbook prepares
  every host (DNS, NTP, VM port group) and makes sure every host is in the cluster. It converges, so an edit
  that changes nothing else, or a retry, is a no-op.
- **Scale-in** (`scale-in.yaml`, onEdit preDeploy, while the leaving hosts still exist): MetalSoft removes the
  **highest-numbered** instances. For each leaving host the playbook reads its VMs from the host itself
  (vCenter's view if the host does not answer) and **refuses** if it runs the vCenter VM or any powered-on VM;
  otherwise it puts the host in maintenance mode and removes it from vCenter. A refusal fails the deploy before
  MetalSoft wipes anything. Powered-off VMs on a leaving host are lost with its disks.
- vCenter stays on the lowest-numbered host, which scale-in never removes while `esxi_host_count` ≥ 1. If you move
  the vCenter VM to another host, scale-in refuses to remove that host.
- Hosts use their local datastores only; nothing moves VMs between hosts. Shared storage, HA and DRS are not
  configured.
- With `create_datacenter_cluster` off, new hosts are installed and prepared but not added to vCenter, and
  leaving hosts are only checked, not removed from vCenter.

## Prerequisites

- **Site config saved** for this extension on every target site, with `vcsa_iso_url` set (it is the only value
  without a default, so the save is refused without it). Until it is saved, deploys fail with "Extension … not
  enabled on site".
- **DNS provisioning extension** at the site (powerdns / infoblox) with an authoritative **reverse zone** —
  vCenter requires `vcenter.<instance>.<zone>` forward and reverse records. Set `DNSResolvers` to a resolver
  that serves them.
  The reverse zone of the management subnet must be answered by that resolver: the powerdns extension
  creates `<c>.<b>.<a>.in-addr.arpa` on the authoritative server, but a PowerDNS recursor in front of it only
  forwards the zones in its `forward-zones` list: add a line for the subnet's reverse zone, then
  `rec_control reload-zones`. A missing forward fails the DNS round-trip check. A reverse zone that already
  exists without an SOA record is refused by PowerDNS even though the PTRs are stored: add an SOA.
- **NTP reachable from the management subnet**: the hosts and the appliance use the site's `NTPServers`
  (fallback `pool.ntp.org`). vCSA stage 1 fails at "Install required RPMs" with `err_ntp_sync_failed` when they
  can't sync, for example a subnet without internet access and a public NTP server.
- **A logical network profile for management**, chosen per instance with `mgmt_network_profile` (e.g.
  `vcf-mgmt`). Each instance gets a new `vcenter-mgmt` network from it, tagged on the hosts; vCenter's IP comes
  from it too, so it needs an IPv4 subnet with a gateway, reachable from the site controller. An existing
  standalone logical network can't be chosen: extensions only create networks from
  profiles, and the platform has no input for an existing network.
- **ESXi 9 OS template** (`esxi-9-25370933-standard`, `templates/os-templates/ESXi/9.1/standard`): sets the management IP on any tagged or untagged network and regenerates the host certificate for its FQDN at firstboot. The VCF `esxi-9-25370933-cluster-node` template only configures networking on a `vcf-mgmt` network.
- **Site controller**: reachability to the ESXi management IP and the vCenter IP on 443, ~25 GB free for the
  EE's `vcsa_work_dir`, and an **x86-64-v3 CPU** (the EE is UBI 10, whose glibc refuses older CPUs — fails
  with `Fatal glibc error: CPU does not support x86-64-v3`).
- **Datastore**: `small` thin needs ~100 GB free to start (734 GB provisioned); thick needs the full size.

## Inputs

| Label | Default | Notes |
| --- | --- | --- |
| `server_type` | — | min 1 CPU socket / 32 GB RAM (`minCpu` counts sockets, not cores) |
| `os_template` | — | ESXi 9 template |
| `esxi_host_count` | `1` | 1-32; editable — the scale knob (vCenter `tiny` supports 10 hosts) |
| `mgmt_network_profile` | — | network profile **label** for the management network (e.g. `vcf-mgmt`); set-only; an unknown label is refused at create |
| `vcenter_admin_password` | — | appliance root and `administrator@<sso domain>`; 8-20 chars, upper, lower, digit, special |
| `sso_domain_name` | `vsphere.local` | set-only |
| `deployment_size` | `small` | `tiny`, `small`, `medium`, `large`, `xlarge`; set-only |
| `vcenter_vm_name` | `vcenter` | set-only |
| `datastore_name` | `""` | empty = largest accessible datastore; set-only |
| `thin_disk_mode` | `true` | |
| `enable_ssh` | `false` | SSH on the appliance |
| `create_datacenter_cluster` | `true` | |
| `datacenter_name` / `cluster_name` | `Datacenter` / `Cluster` | |

## Site config (configVars)

| Label | Default |
| --- | --- |
| `DNSResolvers` | `""` (falls back to record-set resolvers) |
| `vcsa_iso_url` | none (mandatory): URL of the vCSA ISO on your server |
| `vcsa_iso_sha256` | `""` (optional integrity check) |
| `vcsa_work_dir` | `/tmp/vcsa` |

## Testing

```bash
cd tests && ansible-playbook -i inventory.yaml -e @fixtures/sample-variables.json render-spec.yaml
ansible-playbook -i inventory-create.yaml -e @fixtures/scale-variables.json scale-spec.yaml
ansible-playbook -i inventory-edit.yaml -e @fixtures/scale-variables.json scale-spec.yaml
cd ../ansible && ansible-playbook -i ../tests/inventory-edit.yaml --syntax-check deploy.yaml scale-in.yaml scale-out.yaml
```

`tests/fixtures/embedded_vCSA_on_ESXi-9.1.0.0.json` is the template shipped in the 9.1.0.0 ISO; refresh it when
moving to a new vCSA build.

**EE smoke test** — run inside the built image with the real ISO (no ESXi needed). It runs the bundle's ISO
extraction, checks the OVA is not truncated at 4 GiB, runs the bundled `vcsa-deploy` and `ovftool`, and passes the
rendered spec through `vcsa-deploy install --verify-template-only`:

```bash
docker run --rm -e TERM=dumb -v $PWD:/work:ro -v /path/to/VMware-VCSA-all-9.1.0.0.25370922.iso:/iso/vcsa.iso:ro \
  -w /work/tests registry.metalsoft.dev:1.0.1 \
  ansible-playbook -i inventory.yaml -e @fixtures/sample-variables.json -e iso_file=/iso/vcsa.iso ee-smoke.yaml
```

What it caught while building 1.0.0, all invisible to the offline test: the `vcsa-deploy` wrapper needs `which`;
the bundled `ovftool` needs `libnsl.so.1` and `libcrypt.so.1` (`libnsl`, `libxcrypt-compat`); and the OVA (>4 GiB)
is stored as a multi-extent ISO 9660 file, which pycdlib's ISO 9660/Rock Ridge readers truncate — `iso_extract.py`
reads through the UDF view instead. 1.0.1 adds `iputils`: the installer's IP-in-use and DNS prechecks run
`ping`, found only by a real install against ESXi (the smoke test now runs `ping` too).

**Manual run against a deployed ESXi host** (no extension instance needed): on the site controller, load the
EE, put an `inventory.yaml` (group `esxi`, `ansible_host`/`ansible_user`/`ansible_password` of the instance) and an
`extravars.json` (`extensionInstanceVariables`, `configVars`, `extensionInstanceRecordSet` with a hand-picked
`vcenter` allocation, `context_json_file_path: /runner/work/context.json`) in a 0600 directory, and run
`docker run --network host -u 0 … ansible-playbook -i inventory.yaml -e @extravars.json deploy.yaml`. Without
forward/reverse DNS for the vCenter name, set the allocation's `fqdn` to its IP and add
`-e vcsa_skip_dns_check=true` (test-only; no input sets it) — vCenter then uses its IP as system name.

## Packaging

```bash
cd ansible && COPYFILE_DISABLE=1 zip -rX ../vsphere-vcenter9-v1.3.0.zip . -x '*.DS_Store' '._*' '*/._*'
ansible-builder create -f execution-environment.yml   # build the context, then on an x86-64-v3 host:
docker build -f context/Dockerfile -t ee-vsphere-vcenter9:<tag> context
docker save ee-vsphere-vcenter9:<tag> | gzip -n > ee-vsphere-vcenter9.<tag>.tar.gz
```

Bump `extensionVersion` and the bundle file name on every change, and the EE `tagRegistry` + tarball name on every
image rebuild.

**1.3.0** makes `vcsa_iso_url` mandatory: it no longer defaults to a MetalSoft-hosted ISO, and the playbook stops
before any download when it is empty. Keeps the 1.0.1 EE image.

**1.2.0** changes the definition only: the management network's profile is the `mgmt_network_profile` input
(`"profileLabel": "#/input/mgmt_network_profile"`) instead of the fixed `vcf-mgmt`. The playbooks are unchanged,
so it ships the v1.1.0 bundle and the 1.0.1 EE image.

**1.1.0** adds scaling (`esxi_host_count`, scale-in/scale-out playbooks; `outputs.yaml` is gone) and keeps the
1.0.1 EE image: the modules it uses (`vmware.vmware.esxi_maintenance_mode`, `esxi_host`, `cluster_info`,
`community.vmware.vmware_vm_info`) are in vmware.vmware 2.7.0 / community.vmware 6.1.0 there.

**1.0.2** changes the playbooks and definition only, and keeps the 1.0.1 EE image (7b84d5241d1a):
- the management connection uses `server-only-bond`;
- the vCSA ISO comes from `vcsa_iso_url` (plain HTTP(S)) instead of the
  basic-auth VMware depot. The `depot_*` and `vcsa_iso_path` site config values are gone.

**EE image name.** The controller names the image `repositoryRegistry:tagRegistry` (plus host/namespace when set)
and the site controller caches it under that name, in Docker and in `ansible-archives/`. The 1.0.1 asset puts the registry
host in `repositoryRegistry`, so the image runs as `registry.metalsoft.dev:1.0.1`, a name shared with every
extension that does the same with the same tag.
On the next image rebuild, follow the schema: `hostRegistry: registry.metalsoft.dev`,
`repositoryRegistry: ee-vsphere-vcenter9`, new `tagRegistry`.
