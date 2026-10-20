# Nutanix Community Edition (lab)

> **This is a Proof of Concept** Community Edition (CE) is Nutanix's free, unsupported edition. It runs
> unlicensed, needs internet access, and supports 1, 3 or 4 nodes.

This directory contains a MetalSoft **application** extension and the Ansible playbooks. Together they install Nutanix CE 2.1 (AOS 6.8.1 + AHV 20230302) unattended on bare-metal servers and create a cluster. An **OS template** that goes with it, can be found in the `os-templates` github repository.

## How it works

```
MetalSoft deploy
 ├─ allocates N servers, a host IP per node, plus a Prism VIP, a data services IP and a 4-IP CVM range
 │  on the extension's management network (untagged / native VLAN)
 ├─ OS template "nutanix-ce-2-1-cluster-node", one ISO per node:
 │    stock CE ISO
 │    + /EFI/BOOT/grub.cfg: kernel line carries PHOENIX_IP/MASK/GATEWAY (= host IP) and
 │      AZ_CONF_URL=data:,<URL-encoded answer file> (disks, AOS/AHV download URLs with MD5s, the
 │      AHV bond uplinks, the post_phoenix hook)
 │    + /post_phoenix.sh: UEFI boot-entry fix, run by the hook (see "Boot order after install")
 │    → the CE installer runs unattended (its built-in "Arizona" mode), downloads the AOS package and the
 │      AHV ISO over HTTPS, installs AHV + the CVM, fixes the UEFI boot entry, reboots into AHV
 └─ extension onCreate/postDeploy → deploy.yaml (runs on the site controller):
      1. waits until AHV has finished first boot on every node: the ahv-*-cvm services are active and
         the CVM is running
      2. gives each CVM its IP from the CVM range: the host reaches its CVM over the internal
         192.168.5.254 link and writes the CVM's ifcfg-eth0 (skipped when the CVM already answers there)
      3. on the first CVM: cluster -s <cvm ips> ... create (RF1 for 1 node, RF2 for 3 or 4), unless a
         cluster already exists; sets the data services IP and the Prism admin password
      4. publishes the outputs (Prism URL, VIP, data services IP, CVM and host IPs)
```

Design choices:
- **No Foundation VM, no separate web server, no DHCP.** Everything per-node lives in the ISO the
  platform already builds for each instance.
- **The playbooks never touch the BMC.** MetalSoft does the virtual-media install as for any other OS
  template.
- **The CVM IP is set after install.** The OS template only knows the host's own IP, so the installer
  leaves the CVM on DHCP (link-local only), and the playbook assigns it from the extension's `cvm` range.
- **Re-runs are safe.** Every step checks the current state first: AHV ready, CVM IP already set,
  cluster already created, admin password already set.

## Files to host on repo.metalsoft.io

| # | File | Where to get it | Used by |
|---|---|---|---|
| 1 | `phoenix.x86_64-fnd_5.6.1_patch-aos_6.8.1_ga.iso` (7,123,425,280 bytes) | Officially from the Nutanix community portal after [registering for CE](https://www.nutanix.com/products/community-edition/register) (NEXT account), topic "Download Community Edition". The file itself is at `https://download.nutanix.com/ce/2024.08.19/phoenix.x86_64-fnd_5.6.1_patch-aos_6.8.1_ga.iso` | OS template (`build_source_image`) |
| 2 | `nutanix_installer_package.tar` (4,687,655,614 bytes) | Built from the ISO: concatenate `/images/svm/nutanix_installer_package.tar.p00` and `.p01` (commands below) | Installer download (AOS) |
| 3 | `AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso` (the double `.iso` is the real name) | Copied from the ISO: `/images/hypervisor/kvm/` | Installer download (AHV) |
| 4 | `nutanix-ce-v0.1.1.zip` | Built from `ansible/` (below) | Extension `AnsibleBundle` asset |
| 5 | `ee-nutanix-ce-0.1.0.tar.gz` | Built from `execution-environment.yml` (below) | Extension `OciImage` asset |

URLs these files are expected at (change them in `os-template/.../template.yaml`,
`os-template/.../grub.cfg` and `extension.json` if you host them elsewhere):

Extract files 2 and 3 from the ISO (`xorriso` works on Linux and macOS):

```bash
xorriso -osirrox on -indev phoenix.x86_64-fnd_5.6.1_patch-aos_6.8.1_ga.iso \
  -extract /images/svm svm -extract /images/hypervisor/kvm kvm
cat svm/nutanix_installer_package.tar.p00 svm/nutanix_installer_package.tar.p01 > nutanix_installer_package.tar
cp kvm/AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso .
md5sum phoenix.x86_64-fnd_5.6.1_patch-aos_6.8.1_ga.iso nutanix_installer_package.tar AHV-DVD-*.iso.iso
```

Expected MD5 sums, also embedded in `grub.cfg` so the installer verifies its downloads: ISO
`0e7c800b46986c84d4fcdae92e73dc53`, `nutanix_installer_package.tar` `c2cf84ceae79b9aef945bbb5386f790f`,
AHV ISO `d83f73ac1f444ddba3825d335daf908a`.

**Licence:** CE binaries are Nutanix property under the CE EULA. Keep the repo path internal or
access-controlled, and check the EULA before making these files reachable outside MetalSoft labs.

## Prerequisites

**MetalSoft:**
- Controller `v7.5.0` or later, with the ansible-runner capability enabled on the site.
- **Extension site config saved** on the site, because the extension declares `configVars`.
- **The network profile.** `profileLabel` in `extension.json` must name a logical network profile at the
  site. The repo has `simple-vlan-network`. The profile needs:
  - **untagged (native VLAN)** on the server ports; the CE installer cannot tag the host or CVM network;
  - **not 192.168.5.0/24**, which Nutanix uses internally;
  - room for 2 IPs per node (see "Known limitations"), a 4-address CVM range, the Prism VIP and the data
    services IP: 12 addresses for 3 nodes. A `/29` profile is too small;
  - **outbound internet** from the subnet: CE needs it for cluster creation and the first Prism login,
    and the installer downloads files 2 and 3 from repo.metalsoft.io.
- Plain switch ports with no LAG. The extension uses active-backup, which is also AHV's default bond.
- Optional: a DNS provisioning extension (PowerDNS / Infoblox) to create
  `prism.<instance>.<site zone>`. Without one, use the `cluster_vip` output.

**Servers (CE 2.1 requirements):**
- **CPU and memory:** x86_64 with VT-x / AMD-V, at least 4 cores, at least 32 GB RAM (64 GB
  recommended). The installer also needs about 12 GB of RAM to stage the downloads; 8 GB servers fail.
- **Disks:** 3 per node by default (see "Disk layout").
  - AHV boot: at least 32 GB.
  - CVM boot: 1 or 2 SSDs, at least 200 GB.
  - Data: at least 200 GB each.
- **Disks must be presented raw**: AHCI or an HBA / IT-mode controller, no RAID volumes. HPE Smart Array
  must be in HBA mode.
- **Firmware:** UEFI boot, Secure Boot off, BIOS clock correct (a wrong clock breaks cluster create).
- **NIC:** at least 1 GbE, with a driver AHV supports.

### Disk layout

The OS template uses `sda` for AHV, `sdb` for the CVM boot disk and `sdc` for data. That matches a
server with three disks on one controller, like the R440s on us06. For another layout, set custom
variables **on the server instance group** (MetalSoft passes these to the OS template; the extension's
own instance-array custom variables only reach Ansible):

| Custom variable | Example | Meaning |
|---|---|---|
| `ce_hyp_boot_disk` | `sda` | AHV boot disk |
| `ce_cvm_boot_disks` | `nvme0n1` | CVM boot SSD(s), comma-separated, 1 or 2 |
| `ce_cvm_data_disks` | `sdb,sdc` | CVM data disks, comma-separated |

The values are kernel device names as the installer sees them. To find them, boot any Linux live ISO on
one server and run `lsblk -d -o NAME,SIZE,ROTA,MODEL`, with the virtual CD attached, because virtual
media can shift `sdX` names. All nodes in a deployment share one layout.

## Register

```bash
# 1. OS template (local path = this directory's os-template/ folder)
metalcloud-cli os-template create-from-repo Nutanix/CE-2.1/cluster-node \
  --repo-url /path/to/metalsoft-extensions/nutanix-ce/os-template

# 2. Bundle and execution environment
cd ansible && zip -r ../nutanix-ce-v0.1.1.zip . -x '*.DS_Store' && cd ..
unzip -l nutanix-ce-v0.1.1.zip | head          # deploy.yaml and roles/ at the archive root
ansible-builder build -f execution-environment.yml -t ee-nutanix-ce:0.1.0 \
  --container-runtime docker --extra-build-cli-args="--platform=linux/amd64"
docker save ee-nutanix-ce:0.1.0 | gzip > ee-nutanix-ce-0.1.0.tar.gz
# upload both to repo.metalsoft.io (paths above); push the image as registry.metalsoft.dev/ee/ee-nutanix-ce:0.1.0 (Harbor project "ee")

# 3. Extension (stays a draft until activated)
metalcloud-cli extension create "Nutanix Community Edition" application \
  "LAB: Nutanix CE cluster on bare metal" --definition-source extension.json
metalcloud-cli extension activate <id>
```

Then save the extension's site config on the target site.

The UBI10 execution environment needs a real x86_64 build host; Docker's amd64 emulation on Apple
Silicon fails with "CPU does not support x86-64-v3". The 7.5.1 CLI cannot parse controller versions like
`release-v7.5`; add `-x` (`--allow_develop`) to skip that check.

## Configuration

**Site config (`configVars`):**

| Variable | Default | Description |
|---|---|---|
| `DNSResolvers` | `""` | Comma-separated DNS servers for the cluster. Empty uses the site resolvers from the record set. |
| `NTPServers` | `""` | Comma-separated NTP servers. Empty uses the site NTP servers, else `pool.ntp.org`. |

**Per-deployment inputs:**

| Input | Default | Description |
|---|---|---|
| `node_server_type` | – | Server type (at least 32 GB RAM). |
| `node_count` | `3` | 1, 3 or 4. Set at creation only. |
| `node_os_template` | – | `nutanix-ce-2-1-cluster-node`. |
| `prism_admin_password` | – | Prism `admin` password: 8–32 characters, and must not contain `nutanix`, `ntnx` or `password`. The playbook sets it on every run, overwriting a password changed in Prism. |

**Outputs:** `prism_element_url`, `cluster_name` (the extension instance name), `cluster_vip`,
`data_services_ip`, `cvm_ips`, `ahv_host_ips`.

## After the deploy

1. Open `prism_element_url`, or `https://<cluster_vip>:9440`.
2. Log in as `admin` with `prism_admin_password`. If the playbook warned that it could not set the
   password, log in with `nutanix/4u` and change it.
3. **Sign in with a NEXT (My Nutanix) account that has the Community Edition role.** It's required on
   the first login and has no API, so it stays manual. A plain NEXT account is rejected with "does not
   have the required Community Edition role". Get the role by registering for CE with the same email at
   https://www.nutanix.com/products/community-edition/register, then wait for the confirmation email.

AHV `root` and CVM `nutanix` keep the CE default password `nutanix/4u`. This is lab only.

## Tests (offline)

```bash
cd tests && ansible-playbook -i inventory.yaml render-spec.yaml              # plan, IP math, outputs
cd ../ansible && ansible-playbook -i ../tests/inventory.yaml --syntax-check deploy.yaml
# OS template: render grub.cfg with nunjucks (as the platform does), then parse it like the installer
npm install --prefix /tmp/njk nunjucks@3.2.4
NODE_PATH=/tmp/njk/node_modules node ../tests/os-template/render-grub.js \
  ../os-template/Nutanix/CE-2.1/cluster-node/grub.cfg ../tests/os-template/fixtures/os-install-context.json > /tmp/grub.cfg
python3 ../tests/os-template/check_cmdline.py /tmp/grub.cfg 10.20.30.41
bash -n ../os-template/Nutanix/CE-2.1/cluster-node/post_phoenix.sh
```

`check_cmdline.py` reuses the installer's own kernel-argument parser (phoenix `sysUtil.parse_cmd_line`),
loads the answer file through `urlopen` and checks the fields the installer requires. The kernel
command line must stay under the 2048-byte x86 limit; it is about 1,850 bytes now, so there is little
room left.

## Known limitations

1. **CE gaps the extension works around.** These were all found on hardware:
   - the installer requires `hypervisor_iso_url` / `svm_installer_url` as `{url, md5sum}` objects;
   - CE's `ce_validate()` needs the CVM IP fields present as `""`;
   - AHV's legacy first-boot script (Python 2) always fails, so readiness comes from the `ahv-*-cvm`
     services;
   - AHV has only Python 3.6, so playbook tasks on AHV hosts are `raw`, and CVM tasks use the CVM's
     `/usr/bin/python3` (3.9);
   - after `cluster create`, the host's installer key no longer gets into the CVM.
2. **Two IPs per node.** Each NIC on the management network gets its own address. Only the
   default-gateway one is used (AHV bonds both NICs under it). A host-side bond (`server-only-bond`) might
   fix this but hasn't been tried.
3. **No scale or delete.** CE only supports 1, 3 or 4 nodes, so `node_count` is set at creation only, and
   MetalSoft wipes the servers on delete.
4. **CE 2.1 ships AOS 6.8.1 / AHV 20230302.** Upgrades are manual, through LCM in Prism.
5. **Each node downloads about 6.2 GB from repo.metalsoft.io.** Use a site-local mirror for large or slow
   sites (change the URLs in `grub.cfg`).
6. **Unverified on CE, so failures are warnings, not errors:** the data services IP command and the
   admin password change. Both worked on us06.

### Boot order after install

The installer only creates a UEFI boot entry for AHV on hardware it recognises, not in CE mode, and
MetalSoft keeps the virtual CD attached until SSH answers. Without a fix, the server boots the ISO again
and reinstalls in a loop. Each loop pass also leaves a stale "Nutanix AHV" entry behind; on one R440, 20
of them pushed the valid entry behind "Virtual Optical Drive".

`post_phoenix.sh` (in the ISO, run by the answer file's `post_phoenix` hook right before the installer
reboots) handles this on any hardware. It finds the AHV disk by its boot loader, deletes every "Nutanix
AHV" entry, creates a new one first in the boot order and sets `BootNext` to it. It does nothing on
non-UEFI servers.

If a node still loops, pick the local disk in the one-time boot menu (F11 on Dell) once the install
finishes. Stale entries from older installs (any OS) can be cleared:
- **From any Linux on the server:**
  ```bash
  cur=$(efibootmgr | sed -n 's/^BootCurrent: //p')
  efibootmgr -v | sed -n 's/^Boot\([0-9A-F]\{4\}\)\*\{0,1\} \(.*\)HD([0-9]*,GPT,\([0-9A-Fa-f-]*\),.*/\1|\2|\3/p' |
  while IFS='|' read -r n label guid; do
    [ "$n" = "$cur" ] && continue
    [ -e "/dev/disk/by-partuuid/$(echo "$guid" | tr A-Z a-z)" ] && continue
    echo "deleting stale Boot$n: $label"; efibootmgr -q -b "$n" -B
  done
  ```
- **On Dell:** F11 → One-Shot UEFI Boot Menu → Delete Boot Option, then select the "Unavailable"
  entries ([Dell KB 000396285](https://www.dell.com/support/kbdoc/en-us/000396285/poweredge-pxe-boot-failed)).
  That KB also describes a 14G–17G BIOS bug around "Unavailable" entries, with a BIOS update as the fix.

## Troubleshooting

| Where | What |
|---|---|
| Server console during install | The installer runs in a `screen` session. A Python traceback means an answer-file problem; a fresh "Copying squashfs.img" after an install means the boot loop above. |
| AHV host (`root` / `nutanix/4u`) | `systemctl status ahv-define-cvm ahv-install-cvm ahv-configure-cvm ahv-status-cvm`, `virsh list --all`. `ahv_first_boot.service` failing with `python: No such file` is expected. |
| CVM (`nutanix` / `nutanix/4u`) | `cluster status`, `ncli cluster info`, logs in `~/data/logs/` (`genesis.out`). From the host before the CVM has its IP: `ssh -i /root/firstboot/ssh_keys/nutanix nutanix@192.168.5.254`. |
| Site controller | Each extension run is a container from the EE image. `docker logs <container>`, and `/opt/metalsoft/ansible-jobs/<uuid>/artifacts/*/` (stdout, `job_events/`). |
