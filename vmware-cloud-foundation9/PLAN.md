# VCF 9.0.1 Adaptation Plan — `vmware-cloud-foundation9` extension

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adapt the MetalSoft VCF 5.2.2 extension (this folder is an exact copy of it) to deploy VMware Cloud Foundation **9.0.1** using the **VCF Installer** appliance and the offline depot mirror at `https://vmware-depot.metalsoft.dev`.

**Architecture:** Same extension shape (extension.json + Ansible bundle: `esxi` role prepares hosts, `vcf` role drives REST APIs from `management[0]`, all calls `delegate_to: localhost`). The Cloud Builder appliance is replaced by the VCF Installer appliance (same OVA as SDDC Manager), which **does not embed binaries** — two new phases are inserted between appliance deploy and bring-up: offline-depot configuration and binary download. The bring-up spec (`POST /v1/sddcs`) is rewritten to the 9.0 schema, auth switches from Basic to Bearer tokens, and licensing disappears entirely (90-day eval, licensed post-deploy via VCF Operations).

**Tech stack:** Ansible (uri/vmware_deploy_ovf), Jinja2 spec templates, MetalSoft extension framework (schemaVersion 1.1), VCF Installer API 9.0, SDDC Manager API 9.x.

---

## Verified facts this plan is built on

All verified against primary sources (Broadcom techdocs / developer.broadcom.com 9.0 API + OpenAPI `vmware/vcf-api-specs@9.0.0.0`, William Lam's working automation, plus a live audit of the depot mirror) by an adversarial fact-check pass:

| # | Fact |
|---|---|
| F1 | VCF Installer = `VCF-SDDC-Manager-Appliance-9.x.ova`. No "mode" OVA property — it always boots as installer. **The 9.0.1 BOM mandates VCF Installer 9.0.2.0 build 25151285** to deploy 9.0.1 components. Mirror has it: `/PROD/COMP/SDDC_MANAGER_VCF/VCF-SDDC-Manager-Appliance-9.0.2.0.25151285.ova` (2,183,516,160 B). |
| F2 | Installer OVF properties: `vami.hostname`, `vami.ip0.SDDC-Manager`, `vami.netmask0.SDDC-Manager`, `vami.gateway.SDDC-Manager`, `vami.DNS.SDDC-Manager`, `vami.domain.SDDC-Manager`, `vami.searchpath.SDDC-Manager`, `guestinfo.ntp`, `ROOT_PASSWORD`, `LOCAL_USER_PASSWORD` (admin@local, min 15 chars). Network: `Network 1`. 4 vCPU / 16 GB RAM / 914 GB thin. No FIPS/CEIP property. |
| F3 | Auth: `POST /v1/tokens` `{username:"admin@local",password}` → `accessToken` used as `Authorization: Bearer` (Cloud Builder used Basic). UI readiness: poll `GET /vcf-installer-ui/login` until 200 (~10–15 min). |
| F4 | Offline depot: `PUT /v1/system/settings/depot` `{offlineAccount:{username,password}, depotConfiguration:{isOfflineDepot:true, hostname, port}}` (202) → `PATCH /v1/system/settings/depot/depot-sync-info` → poll `GET` same URL until `syncStatus=="SYNCED"`. Basic auth on all of `/PROD` is fine (incl. `PROD/vsan/hcl` — fetched with offlineAccount creds; only `umds-patch-store` must be unauthenticated, and that's post-install LCM, not bring-up). |
| F5 | Binary downloads: `GET /v1/releases/VCF/release-components?releaseVersion=9.0.1.0&automatedInstall=true&imageType=INSTALL` → bundle ids → `PATCH /v1/bundles/{id}` `{bundleDownloadSpec:{downloadNow:true}}` → poll `GET /v1/bundles/download-status?releaseVersion=9.0.1.0&imageType=INSTALL`; on FAILED: `DELETE /v1/bundles/{id}` + re-PATCH. Must complete before bring-up. |
| F6 | Bring-up endpoints unchanged in name: `POST /v1/sddcs/validations`, `GET /v1/sddcs/validations/{id}`, `POST /v1/sddcs` (202 → SddcTask), `GET /v1/sddcs/{id}` (status: `IN_PROGRESS\|COMPLETED_WITH_SUCCESS\|COMPLETED_WITH_FAILURE\|ROLLBACK_SUCCESS`), retry = `PATCH /v1/sddcs/{id}`. |
| F7 | 9.0 SddcSpec: schema-required = `sddcId, vcenterSpec, networkSpecs, dnsSpec`. **Removed:** `taskName, fipsEnabled, esxLicense, deployWithoutLicenseKeys, pscSpecs, dvSwitchVersion, proxySpec, vxManagerSpec, excludedComponents`, top-level `vsanSpec`, all license fields anywhere. **New:** `version, vcfInstanceName, workflowType(VCF\|VCF_EXTEND\|VVF), datastoreSpec, vcfOperationsSpec, vcfOperationsFleetManagementSpec, vcfOperationsCollectorSpec, vcfAutomationSpec`. |
| F8 | 9.0 `hostSpecs` = only `hostname` (short name, required), `credentials`, `sshThumbprint`, `sslThumbprint`. `association`/`ipAddressPrivate`/`vSwitch` removed — host IPs resolved via DNS from `hostname` + `dnsSpec.subdomain`. |
| F9 | 9.0 `nsxtSpec`: required `nsxtManagers[{hostname}]` + `vipFqdn`; `vip` (IP) and `nsxtLicense` removed; new `skipNsxOverlayOverManagementNetwork` (set `true` to keep our dedicated TEP VLAN/pool). `dvsSpecs.vmnicsToUplinks` now required; `niocSpecs` gone. vSAN moved to `datastoreSpec.vsanSpec{datastoreName, vsanDedup, esaConfig.enabled, failuresToTolerate}` (FTT moved from clusterSpec; `hclFile` gone). `clusterSpec` keeps `datacenterName, clusterName, clusterEvcMode, resourcePoolSpecs` (no `clusterImageEnabled`/`vmFolders`). SSO absorbed into `vcenterSpec` (`ssoDomain`, `adminUserSsoUsername`, `adminUserSsoPassword`); `rootVcenterPassword` 15–20 chars. `dnsSpec` = `{subdomain, nameservers[≤2]}`. |
| F10 | Functionally mandatory appliances for `workflowType: VCF`: vCenter, NSX (1 or 3 nodes + VIP), SDDC Manager, VCF Operations, Ops fleet management, Ops collector → **min 7 FQDNs/IPs**. VCF Automation is the only deferrable one (needs FQDN + `ipPool` 2–4 IPs + `internalClusterCidr` ∈ {198.18.0.0/15, 240.0.0.0/15, 250.0.0.0/15}). No vidbSpec/licenseServerSpec in 9.0.x. |
| F11 | ESX hosts must be **pre-installed with the exact BOM build: ESX 9.0.1.0-24957456**. Installer does not image/upgrade hosts. Min 3 hosts with vSAN (was 4), ≥10 GbE NICs enforced, **self-signed cert must be regenerated after hostname is set** (CN check at validation), only 1 NIC on vSwitch0 pre-bring-up, lowercase FQDNs. |
| F12 | **Depot mirror blocker:** `VMware-VMvisor-Installer-9.0.1.0.24957456.x86_64.iso` is 404 in `/PROD/COMP/ESX_HOST/` (catalog expects it, 663,089,152 B, sha256 `84c341e242410b4fe8b5341aa00063db0e9b2cedbcf5d332eef241c0bfffb826`). Everything else in the core 9.0.1 BOM is present and byte-exact. vSAN HCL `all.json` is dated 2026-01-20 → **>90 days stale** (matters only for vSAN ESA). |
| F13 | MetalSoft platform: no ESXi 9 OS template exists in `metalsoft-io/os-templates` (newest: `esxi-8-cluster-node`, 8.0U3b-24280767). `dependencies.osTemplates`/`controllerVersion` are informational only; the hard check is template-label resolution at instance create. `executionTimeout` has **no enforced max**. `playbook` ≤32 chars, asset URL ≤128 chars. The extension's `execution-environment.yml` is NOT consumed at runtime — the site controller uses its configured EE image (override possible via OciImage asset on v1 agent). `ipAllocations` "max 3" is swagger-doc-only (no validator) — current 7 work, more are fine. |
| F14 | Licensing: zero license fields in 9.0 spec; deploys in 90-day eval; licensed afterwards through VCF Operations. Delete all license plumbing. |
| F15 | Timing: bring-up ≈3 h on physical (13 mgmt VMs) + binary downloads (LAN mirror ~30 min–2 h). Recommend `executionTimeout` 28800–43200 s. |
| F16 | VCF Automation deployment **fails with `.local` domains** — DNS zone must be routable/real. |

---

## Phase A — Environment prerequisites (outside this repo)

### Task A1: Complete the depot mirror for 9.0.1

**Where:** the server behind `https://vmware-depot.metalsoft.dev` (nginx autoindex, basic auth `vmware-depot`).

- [ ] **A1.1** Obtain `VMware-VMvisor-Installer-9.0.1.0.24957456.x86_64.iso` (Broadcom support portal entitlement, or `vcf-download-tool binaries download --depot-download-token-file=<token> -d /depot --vcf-version=9.0.1.0 --automated-install --type=INSTALL` and copy the delta). Place it at `/PROD/COMP/ESX_HOST/VMware-VMvisor-Installer-9.0.1.0.24957456.x86_64.iso`.
- [ ] **A1.2** Verify:
```bash
curl -sI -u 'vmware-depot:<pass>' https://vmware-depot.metalsoft.dev/PROD/COMP/ESX_HOST/VMware-VMvisor-Installer-9.0.1.0.24957456.x86_64.iso
# Expect: HTTP 200, Content-Length: 663089152
curl -s -u 'vmware-depot:<pass>' https://vmware-depot.metalsoft.dev/PROD/COMP/ESX_HOST/VMware-VMvisor-Installer-9.0.1.0.24957456.x86_64.iso | shasum -a 256
# Expect: 84c341e242410b4fe8b5341aa00063db0e9b2cedbcf5d332eef241c0bfffb826
```
- [ ] **A1.3** (Only if vSAN **ESA** will be used) Refresh the HCL DB: download `https://vvs.broadcom.com/service/vsan/all.json` → `/PROD/vsan/hcl/all.json` and update `lastupdatedtime.json` (must be <90 days old at deploy time). Alternative lab bypass: `vsan.esa.sddc.managed.disk.claim=true` in `/etc/vmware/vcf/domainmanager/application-prod.properties` on the installer.
- [ ] **A1.4** (Optional, recommended) Add other missing 9.0.1 artifacts: `vcf-download-tool-9.0.1.0.24962179.tar.gz`, `VCF-SDDC-Manager-Appliance-Upgrade-9.0.1.0.24962180.tar`, `VMware-vCenter-Server-Appliance-9.0.1.0.24957454_OVF10.ova`; whole-component dirs absent from the mirror: VRNI, VSAN_FILE_SERVICES, HCX, DLVM (only needed if those features are used).

### Task A2: Build the ESXi 9.0.1 OS template (`esxi-9-24957456-cluster-node`)

**Where:** `metalsoft-io/os-templates` repo + `repo.metalsoft.io`. Model on `ESXi/8.0.3/esxi-8-cluster-node` (template.yaml + templated `BOOT.CFG`, `KS.CFG`, install ISO as `build_source_image`).

- [ ] **A2.1** Upload the same ESX 9.0.1 ISO (from A1.1) to `https://repo.metalsoft.io/.vmware/VMware-VMvisor-Installer-9.0.1.0.24957456.x86_64.iso`.
- [ ] **A2.2** Create `ESXi/9.0.1/esxi-9-cluster-node/` from the 8.0.3 template:
  - `template.yaml`: name "VCF9 Cluster Node", label `esxi-9-24957456-cluster-node`, version `9.0.1`, build `24957456`, bootmode `uefi`, tags `esxi-9-0-1-24957456`, `vcf-cluster-node`; ISO asset → the 9.0.1 ISO URL.
  - `BOOT.CFG`: regenerate from the 9.0.1 ISO's `/EFI/BOOT/BOOT.CFG` (the `modules=` list differs from 8.x; keep `kernelopt=ks=cdrom:/KS.CFG` and the `build=9.0.1-0.x.24957456` line as found on the ISO).
  - `KS.CFG`: reuse the 8.x kickstart (network from `logicalNetworkName == 'vcf-mgmt'`, rootpw, vSwitch0 MTU 9000, DNS/NTP, SSH enable) **plus a cert-regeneration block in `%firstboot` after the FQDN is set** (fixes F11's CN validation failure):
```
# after esxcli system hostname set --fqdn=... :
/sbin/generate-certificates
/etc/init.d/hostd restart
/etc/init.d/vpxa restart
```
- [ ] **A2.3** Build/register the template (`metalcloud-cli` build flow), deploy one test server with it.
- [ ] **A2.4** Verify on the test server:
```bash
ssh root@<host> vmware -vl        # Expect: VMware ESXi 9.0.1 build-24957456
echo | openssl s_client -connect <host>:443 2>/dev/null | openssl x509 -noout -subject
# Expect: CN = <host fqdn>, not localhost.localdomain
```

---

## Phase B — Ansible bundle + extension.json rewrite

All paths relative to `/Users/mboeru/Work/git/metalsoft-extensions/vmware-cloud-foundation9`. Each task ends with a commit. Run `ansible-playbook --syntax-check ansible/deploy.yaml ansible/scale.yaml` (from `ansible/`, with `ansible.cfg` there) plus the render harness after every task.

### Task B1: Spec render harness (write the failing test first)

**Files:**
- Create: `tests/fixtures/sample-variables.json`
- Create: `tests/inventory.yaml`
- Create: `tests/render-spec.yaml`

- [ ] **B1.1** Create `tests/fixtures/sample-variables.json` — a minimal copy of a real `variables.json` (grab one from a previous 5.2.2 run at `/opt/metalsoft/ansible-jobs/<task_uuid>/ansible/env/extravars` on a site controller, or synthesize): `extensionInstanceVariables` (all inputs incl. the new ones from B3), `extensionInstanceRecordSet` with `extensionInstanceId`, `baseDomain`, `ntpServers`, `dnsResolvers`, `serverInstanceGroups[0]` (label `management`, `logicalNetworks` for `vcf-mgmt`/`vcf-vsan`/`vcf-vmotion`/`vcf-nsx` with subnets, `ipAllocations` carrying the role tags incl. the new `vcf-installer`/`vcf-operations`/`ops-fleet-management`/`ops-collector`/`vcf-automation` roles + `automation-ip-pool` ipRange, each with `ip`/`fqdn`/`gateway`/`netmask`), and 4 `serverInstances` with `logicalNetworks[].uplinks` MACs.
- [ ] **B1.2** Create `tests/inventory.yaml` — `groups`/`hostvars` are reserved magic variables and cannot be faked via play vars, so the harness uses a real static inventory (host short names must sit under the fixture's `baseDomain`):
```yaml
all:
  children:
    management:
      hosts:
        esx01.vcf.example.com: &esx { ansible_host: 10.0.10.11, ansible_user: root, ansible_password: "EsxPassw0rd!123", esxi_ssh_thumbprint: "", esxi_ssl_thumbprint: "" }
        esx02.vcf.example.com: { <<: *esx, ansible_host: 10.0.10.12 }
        esx03.vcf.example.com: { <<: *esx, ansible_host: 10.0.10.13 }
        esx04.vcf.example.com: { <<: *esx, ansible_host: 10.0.10.14 }
```
Then create `tests/render-spec.yaml`:
```yaml
---
- name: Render VCF 9 SDDC spec from fixture
  hosts: localhost
  gather_facts: false
  vars_files:
    - fixtures/sample-variables.json
  vars:
    # the harness fakes the facts that vmnics-to-uplinks normally discovers via vCenter APIs
    uplink1_vmnic_name: vmnic0
    uplink2_vmnic_name: vmnic1
  tasks:
    - name: Load globals defaults
      ansible.builtin.include_vars: { dir: ../ansible/roles/globals/defaults }
    - name: Load vcf role defaults
      ansible.builtin.include_vars: { dir: ../ansible/roles/vcf/defaults }
    - name: Build SDDC spec facts
      ansible.builtin.include_tasks: ../ansible/roles/vcf/tasks/build-sddc-spec.yaml
    - name: Render spec
      ansible.builtin.set_fact:
        sddc_spec: "{{ lookup('template', '../ansible/roles/vcf/templates/management-workload-domain.yaml.j2') | from_yaml }}"
    - name: Write rendered spec
      ansible.builtin.copy: { content: "{{ sddc_spec | to_nice_json }}", dest: /tmp/sddc-spec-9.json }
    - name: Assert 9.0 spec shape
      ansible.builtin.assert:
        that:
          - sddc_spec.version == '9.0.1.0'
          - sddc_spec.workflowType == 'VCF'
          - sddc_spec.vcfOperationsSpec.nodes | length >= 1
          - sddc_spec.vcfOperationsFleetManagementSpec.hostname | length > 0
          - sddc_spec.vcfOperationsCollectorSpec.hostname | length > 0
          - sddc_spec.datastoreSpec.vsanSpec.datastoreName | length > 0
          - sddc_spec.hostSpecs[0].hostname is not search('\.')   # short names only
          - "'ipAddressPrivate' not in sddc_spec.hostSpecs[0]"
          - "'pscSpecs' not in sddc_spec"
          - "'esxLicense' not in sddc_spec"
          - "'taskName' not in sddc_spec"
          - sddc_spec.nsxtSpec.vipFqdn | length > 0
          - "'vip' not in sddc_spec.nsxtSpec"
          - sddc_spec.dvsSpecs[0].vmnicsToUplinks | length == 2
          - sddc_spec.dnsSpec.nameservers | length >= 1
```
*Note: the fixture's host short names must resolve relative to `dnsSpec.subdomain` — keep fixture hosts as `esx0N.<subdomain>`.*
- [ ] **B1.3** Run it — must FAIL now (template is still 5.2-shaped):
```bash
cd tests && ansible-playbook -i inventory.yaml render-spec.yaml
# Expect: assert failure (taskName present, vcfOperationsSpec missing, ...)
```
- [ ] **B1.4** Commit: `git add tests/ && git commit -m "test: add VCF9 SDDC spec render harness (red)"`

### Task B2: Globals — versions, depot, installer vars; delete licensing

**Files:**
- Modify: `ansible/roles/globals/defaults/main.yaml`

- [ ] **B2.1** Replace the version/OVA block (lines 22–41) with:
```yaml
repository_base_url: "{{ extensionInstanceVariables.repository_base_url | default(extensionInstanceRecordSet.repositoryBaseUrl | default('')) }}"
vcf_version: "{{ extensionInstanceVariables.vcf_version | default('9.0.1.0') }}"
vcf_release_sku: "{{ extensionInstanceVariables.vcf_release_sku | default('VCF') }}"
# VCF Installer 9.0.2.0 is required by Broadcom to deploy 9.0.1 components (9.0.1 BOM)
ova_name: "{{ extensionInstanceVariables.ova_name | default('VCF-SDDC-Manager-Appliance-9.0.2.0.25151285.ova') }}"
derived_ova_url: >-
  {{ (repository_base_url | default(''))
     | ternary(repository_base_url + '/.vmware/vcf/' + vcf_version + '/' + ova_name, '')
  }}
raw_ova_url: "{{ extensionInstanceVariables.ova_url | default('') }}"
effective_ova_url: >-
  {{ (raw_ova_url | trim | length > 0) | ternary(raw_ova_url | trim, derived_ova_url) }}
ova_url: "{{ effective_ova_url }}"

# Offline depot (VCF Installer pulls all product binaries from here)
depot:
  hostname: "{{ extensionInstanceVariables.depot_hostname | default('vmware-depot.metalsoft.dev') }}"
  port: "{{ extensionInstanceVariables.depot_port | default(443) | int }}"
  username: "{{ extensionInstanceVariables.depot_username | default('vmware-depot') }}"
  password: "{{ extensionInstanceVariables.depot_password | default('') }}"
```
- [ ] **B2.2** In the `vcf:` dict: delete `aria_suite_enabled`, `fips_enabled` (no longer in spec), `license:` map, `deploy_without_license_keys`, `task_name`, `dv_switch_version`; keep `architecture`, `platform` (now feeds `workflowType`), `ceip_enabled`, `distinct_vlan_id_vm_mgmt_and_esxi_mgmt`, `skip_esx_thumbprint_validation`, `validation_debug`; add:
```yaml
  skip_gateway_ping_validation: "{{ extensionInstanceVariables.skip_gateway_ping_validation | default(false) | bool }}"
  deploy_automation: "{{ extensionInstanceVariables.deploy_vcf_automation | default(false) | bool }}"
  instance_name: "{{ extensionInstanceVariables.vcf_instance_name | default(extension_instance_id ~ '-vcf') }}"
```
- [ ] **B2.3** Delete the license helper block (`all_license_keys_set`, `any_license_key_set`, `partial_license_keys_set`, `licenses_required`, lines 64–88) and the `proxy_enabled`/`proxy_spec` block (proxySpec removed from 9.0 SddcSpec).
- [ ] **B2.4** Run harness (still red, but must not error on undefined `depot`/`vcf` keys) + `ansible-playbook --syntax-check`. Commit: `refactor: globals for VCF9 (depot config, drop licensing/proxy/CB vars)`.

### Task B3: extension.json — inputs, IP allocations, timeouts

**Files:**
- Modify: `extension.json`

- [ ] **B3.1** Header/identity: `name` → `"VMware Cloud Foundation 9 (VCF)"`, `label` → `"vcf9"`, `extensionVersion` → `"2.0.0"`, `dependencies.osTemplates` → `["esxi-9-24957456-cluster-node"]`.
- [ ] **B3.2** Inputs — change defaults: `vcf_version` → `"9.0.1.0"`; `ova_name` → `"VCF-SDDC-Manager-Appliance-9.0.2.0.25151285.ova"`; `mgmt_domain_instance_count.options.minValue` → `3` (keep default 4).
- [ ] **B3.3** Inputs — rename (new extension, clean names): `cba_admin_password` → `installer_admin_password`, `cba_root_password` → `installer_root_password` (defaults stay ≥15 chars — both current defaults are exactly 15).
- [ ] **B3.4** Inputs — add (all `ExtensionInputString` unless noted; passwords `isPassword: true` with ≥15-char defaults):
```json
{"label":"depot_hostname","name":"depot_hostname","inputType":"ExtensionInputString","defaultValue":"vmware-depot.metalsoft.dev","options":{}},
{"label":"depot_port","name":"depot_port","inputType":"ExtensionInputInteger","defaultValue":443,"options":{}},
{"label":"depot_username","name":"depot_username","inputType":"ExtensionInputString","defaultValue":"vmware-depot","options":{}},
{"label":"depot_password","name":"depot_password","inputType":"ExtensionInputString","isPassword":true,"options":{}},
{"label":"vcf_ops_admin_password","name":"vcf_ops_admin_password","inputType":"ExtensionInputString","isPassword":true,"defaultValue":"oP5#kT2!bQ9wX4z","options":{}},
{"label":"vcf_ops_root_password","name":"vcf_ops_root_password","inputType":"ExtensionInputString","isPassword":true,"defaultValue":"rO7$mY3?cD1vN6e","options":{}},
{"label":"ops_fleet_mgmt_root_password","name":"ops_fleet_mgmt_root_password","inputType":"ExtensionInputString","isPassword":true,"defaultValue":"fM2^hU8!aS5qW9r","options":{}},
{"label":"ops_fleet_mgmt_admin_password","name":"ops_fleet_mgmt_admin_password","inputType":"ExtensionInputString","isPassword":true,"defaultValue":"fA4&jI6?dG3xZ7t","options":{}},
{"label":"ops_collector_root_password","name":"ops_collector_root_password","inputType":"ExtensionInputString","isPassword":true,"defaultValue":"cR9#nE1!bH4yV2u","options":{}},
{"label":"vcf_ops_appliance_size","name":"vcf_ops_appliance_size","inputType":"ExtensionInputString","defaultValue":"small","options":{}},
{"label":"deploy_vcf_automation","name":"deploy_vcf_automation","inputType":"ExtensionInputBoolean","defaultValue":false,"options":{}},
{"label":"vcf_automation_admin_password","name":"vcf_automation_admin_password","inputType":"ExtensionInputString","isPassword":true,"defaultValue":"aU3$pL7?eK2wQ8s","options":{}},
{"label":"vcf_automation_internal_cluster_cidr","name":"vcf_automation_internal_cluster_cidr","inputType":"ExtensionInputString","defaultValue":"198.18.0.0/15","options":{}},
{"label":"skip_gateway_ping_validation","name":"skip_gateway_ping_validation","inputType":"ExtensionInputBoolean","defaultValue":false,"options":{}}
```
*(Generate fresh password defaults; the ones above are placeholders — 15 chars, upper+lower+digit+special, avoid `&`/quotes that complicate JSON/YAML.)*
- [ ] **B3.5** Inputs — delete: `vcenter_vm_size` stays (`tiny..xlarge` all valid in 9), `nsx_manager_size` stays (`medium` valid; `small` no longer exists — note in README), `deployment_architecture_model` stays hidden (only feeds resource-pool naming now), `ova_url`/`repository_base_url` stay.
- [ ] **B3.6** `infrastructure.logicalNetworks[vcf-mgmt].ipAllocations`: rename role `cloud-builder` → `vcf-installer` with DNS record `installer.{{default_zone_name}}`; add four allocations:
```json
{"tags":{"role":"vcf-operations"},"ipVersion":"ipv4","dnsRecords":[{"name":"ops1.{{default_zone_name}}","recordType":"A","generatePtrRecord":true,"ttl":3600}]},
{"tags":{"role":"ops-fleet-management"},"ipVersion":"ipv4","dnsRecords":[{"name":"opsfm1.{{default_zone_name}}","recordType":"A","generatePtrRecord":true,"ttl":3600}]},
{"tags":{"role":"ops-collector"},"ipVersion":"ipv4","dnsRecords":[{"name":"opscp1.{{default_zone_name}}","recordType":"A","generatePtrRecord":true,"ttl":3600}]},
{"tags":{"role":"vcf-automation"},"ipVersion":"ipv4","dnsRecords":[{"name":"auto1.{{default_zone_name}}","recordType":"A","generatePtrRecord":true,"ttl":3600}]}
```
and on the same network an `ipRanges` entry: `{"tags":{"role":"automation-ip-pool"},"ipVersion":"ipv4","ipCount":2}`.
- [ ] **B3.7** Timeouts: `onCreate.postDeploy.tasks[0].options.executionTimeout` → `28800` (downloads + ~3 h bring-up; no platform max); `onEdit` both stages → `7200`.
- [ ] **B3.8** `assets[0]`: `url` → `https://repo.metalsoft.io/.extensions_ms/vmware-cloud-foundation9/vmware-cloud-foundation9-v2.0.0.zip` (94 chars < 128 ✓).
- [ ] **B3.9** Validate JSON: `python3 -m json.tool extension.json > /dev/null`. Commit: `feat: extension.json for VCF 9.0.1 (installer, ops appliances, depot inputs)`.

### Task B4: Installer appliance deploy (replaces deploy-cba.yaml)

**Files:**
- Create: `ansible/roles/vcf/tasks/deploy-vcf-installer.yaml`
- Delete: `ansible/roles/vcf/tasks/deploy-cba.yaml`, `ansible/roles/vcf/tasks/verify-cloud-builder.yaml`, `ansible/roles/vcf/tasks/cba-checks/` (the installer has no ntpd/photon-shell checks worth keeping; DNS sanity is covered by bring-up validation)
- Modify: `ansible/roles/vcf/tasks/sddc-spec/management-services.yaml` (rename `cba` fact → `installer`, role tag `vcf-installer`)

- [ ] **B4.1** In `management-services.yaml`: change the allocation lookup to `selectattr('tags.role', 'equalto', 'vcf-installer')`, rename the fact `cba:` → `installer:`, source passwords from `extensionInstanceVariables.installer_admin_password` / `installer_root_password`, keep datastore/disk/retry knobs (rename `cba_*` extensionInstanceVariables to `installer_*`). Drop `admin_username` (always `admin@local` in 9). Add `deploy_task_api_retries: 1440` / `deploy_task_api_retries_delay: 30` (12 h bring-up budget).
- [ ] **B4.2** Create `deploy-vcf-installer.yaml`:
```yaml
---
- name: Set ESXi facts for localhost
  set_fact:
    target_esxi_hostname: "{{ ansible_host }}"
    target_esxi_username: "{{ ansible_user | default('root') }}"
    target_esxi_password: "{{ ansible_password }}"
  delegate_to: localhost

- name: Instantiate VCF Installer appliance
  vmware_deploy_ovf:
    hostname: "{{ target_esxi_hostname }}"
    username: "{{ target_esxi_username }}"
    password: "{{ target_esxi_password }}"
    name: "{{ installer.hostname }}"
    wait_for_ip_address: true
    validate_certs: "{{ installer.validate_certs }}"
    power_on: true
    allow_duplicates: false
    datastore: "{{ installer.datastore }}"
    disk_provisioning: "{{ installer.disk_provisioning }}"
    inject_ovf_env: true
    url: "{{ ova_url }}"
    networks:
      "Network 1": "VM Network"
    properties:
      vami.hostname: "{{ installer.hostname_fqdn }}"
      vami.ip0.SDDC-Manager: "{{ installer.ipv4_address }}"
      vami.netmask0.SDDC-Manager: "{{ installer.ipv4_netmask }}"
      vami.gateway.SDDC-Manager: "{{ installer.ipv4_gateway }}"
      vami.DNS.SDDC-Manager: "{{ installer.ipv4_dns }}"
      vami.domain.SDDC-Manager: "{{ domain }}"
      vami.searchpath.SDDC-Manager: "{{ dns_searchpath }}"
      guestinfo.ntp: "{{ ntp_servers | join(',') }}"
      ROOT_PASSWORD: "{{ installer.root_password }}"
      LOCAL_USER_PASSWORD: "{{ installer.admin_password }}"
  delegate_to: localhost

- name: Wait for VCF Installer UI/API readiness
  ansible.builtin.uri:
    url: "https://{{ installer.ipv4_address }}/vcf-installer-ui/login"
    method: GET
    status_code: 200
    validate_certs: "{{ installer.validate_certs }}"
  retries: "{{ installer.initialize_api_retries }}"
  delay: "{{ installer.initialize_api_retries_delay }}"
  register: installer_ready_result
  until: installer_ready_result is succeeded
  delegate_to: localhost
```
- [ ] **B4.3** Syntax check + commit: `feat: deploy VCF Installer appliance (replaces Cloud Builder)`.

### Task B5: Installer token + depot config + binary download (new phases)

**Files:**
- Create: `ansible/roles/vcf/tasks/installer/get-installer-token.yaml`
- Create: `ansible/roles/vcf/tasks/installer/configure-depot.yaml`
- Create: `ansible/roles/vcf/tasks/installer/download-binaries.yaml`

- [ ] **B5.1** `get-installer-token.yaml`:
```yaml
---
- name: VCF Installer API | Obtain access token
  ansible.builtin.uri:
    url: "https://{{ installer.ipv4_address }}/v1/tokens"
    method: POST
    headers: { Content-Type: "application/json", Accept: "application/json" }
    body_format: json
    body: { username: "admin@local", password: "{{ installer.admin_password }}" }
    status_code: [200, 201]
    validate_certs: "{{ installer.validate_certs }}"
  register: installer_token_response
  retries: 5
  delay: 10
  until: installer_token_response is succeeded
  delegate_to: localhost

- name: Set installer auth headers
  set_fact:
    installer_auth_headers:
      Accept: "application/json"
      Content-Type: "application/json"
      Authorization: "Bearer {{ installer_token_response.json.accessToken }}"
```
- [ ] **B5.2** `configure-depot.yaml`:
```yaml
---
- ansible.builtin.include_tasks: get-installer-token.yaml

- name: Configure offline depot
  ansible.builtin.uri:
    url: "https://{{ installer.ipv4_address }}/v1/system/settings/depot"
    method: PUT
    headers: "{{ installer_auth_headers }}"
    body_format: json
    body:
      offlineAccount:
        username: "{{ depot.username }}"
        password: "{{ depot.password }}"
      depotConfiguration:
        isOfflineDepot: true
        hostname: "{{ depot.hostname }}"
        port: "{{ depot.port | int }}"
    status_code: [200, 202]
    validate_certs: "{{ installer.validate_certs }}"
  delegate_to: localhost

- name: Trigger depot sync
  ansible.builtin.uri:
    url: "https://{{ installer.ipv4_address }}/v1/system/settings/depot/depot-sync-info"
    method: PATCH
    headers: "{{ installer_auth_headers }}"
    status_code: [200, 202]
    validate_certs: "{{ installer.validate_certs }}"
  delegate_to: localhost

- name: Wait for depot sync to complete
  ansible.builtin.uri:
    url: "https://{{ installer.ipv4_address }}/v1/system/settings/depot/depot-sync-info"
    method: GET
    headers: "{{ installer_auth_headers }}"
    status_code: [200]
    validate_certs: "{{ installer.validate_certs }}"
  register: depot_sync_result
  retries: 90
  delay: 10
  until: depot_sync_result.json.syncStatus | default('') == 'SYNCED'
  delegate_to: localhost
```
- [ ] **B5.3** `download-binaries.yaml` (token refreshed per phase because bundle downloads can outlive the token TTL):
```yaml
---
- ansible.builtin.include_tasks: get-installer-token.yaml

- name: Get release components for {{ vcf_version }}
  ansible.builtin.uri:
    url: "https://{{ installer.ipv4_address }}/v1/releases/{{ vcf_release_sku }}/release-components?releaseVersion={{ vcf_version }}&automatedInstall=true&imageType=INSTALL"
    method: GET
    headers: "{{ installer_auth_headers }}"
    status_code: [200]
    validate_certs: "{{ installer.validate_certs }}"
  register: release_components_result
  delegate_to: localhost

# NOTE: verify the exact JSON path on the live installer (GET /v1/api-doc);
# William Lam's 9.0 script reads elements[].versions[].artifacts.bundles[].id
- name: Extract bundle ids
  set_fact:
    vcf_bundle_ids: >-
      {{ release_components_result.json | json_query('elements[].versions[].artifacts.bundles[].id') | unique }}

- name: Assert bundles were found
  ansible.builtin.assert:
    that: vcf_bundle_ids | length > 0
    fail_msg: "No INSTALL bundles found for {{ vcf_version }} — check depot content/sync"

- name: Request bundle downloads
  ansible.builtin.uri:
    url: "https://{{ installer.ipv4_address }}/v1/bundles/{{ item }}"
    method: PATCH
    headers: "{{ installer_auth_headers }}"
    body_format: json
    body: { bundleDownloadSpec: { downloadNow: true } }
    status_code: [200, 202, 400]   # 400 = BUNDLE_DOWNLOAD_ALREADY_DOWNLOADED is fine
    validate_certs: "{{ installer.validate_certs }}"
  loop: "{{ vcf_bundle_ids }}"
  delegate_to: localhost

- name: Wait for all bundle downloads (outer loop re-authenticates)
  ansible.builtin.include_tasks: wait-binary-downloads.yaml
  loop: "{{ range(0, 24) | list }}"   # 24 x ~10 min = 4 h budget
  loop_control: { loop_var: download_wait_cycle }
  when: not (vcf_binaries_ready | default(false))
```
plus `wait-binary-downloads.yaml`:
```yaml
---
- ansible.builtin.include_tasks: get-installer-token.yaml

- name: Poll bundle download status
  ansible.builtin.uri:
    url: "https://{{ installer.ipv4_address }}/v1/bundles/download-status?releaseVersion={{ vcf_version }}&imageType=INSTALL"
    method: GET
    headers: "{{ installer_auth_headers }}"
    status_code: [200]
    validate_certs: "{{ installer.validate_certs }}"
  register: bundle_status_result
  retries: 20
  delay: 30
  until: >-
    (bundle_status_result.json.elements | default([])
     | selectattr('downloadStatus', 'in', ['SCHEDULED', 'INPROGRESS', 'VALIDATING'])
     | list | length) == 0
  failed_when: false
  delegate_to: localhost

- name: Fail fast on FAILED bundles
  ansible.builtin.fail:
    msg: "Bundle download failed: {{ bundle_status_result.json.elements | selectattr('downloadStatus', 'equalto', 'FAILED') | list }}"
  when: bundle_status_result.json.elements | default([]) | selectattr('downloadStatus', 'equalto', 'FAILED') | list | length > 0

- name: Mark binaries ready when nothing is pending
  set_fact:
    vcf_binaries_ready: >-
      {{ (bundle_status_result.json.elements | default([])
          | selectattr('downloadStatus', 'in', ['SCHEDULED', 'INPROGRESS', 'VALIDATING'])
          | list | length) == 0 }}
```
- [ ] **B5.4** Wire into `ansible/roles/vcf/tasks/main.yaml` (new order):
```yaml
---
- name: Import vmnics-to-uplinks.yaml
  ansible.builtin.import_tasks: vmnics-to-uplinks.yaml
- name: Build SDDC specification
  ansible.builtin.import_tasks: build-sddc-spec.yaml
- name: Validate SDDC specification
  ansible.builtin.import_tasks: validate-sddc-spec.yaml
- name: Deploy VCF Installer appliance
  ansible.builtin.import_tasks: deploy-vcf-installer.yaml
- name: Configure offline depot
  ansible.builtin.import_tasks: installer/configure-depot.yaml
- name: Download release binaries
  ansible.builtin.import_tasks: installer/download-binaries.yaml
- name: Deploy management workload domain
  ansible.builtin.import_tasks: deploy-mgmt-workload-domain.yaml
```
- [ ] **B5.5** Syntax check + commit: `feat: installer token/depot/binary-download phases`.

### Task B6: Rewrite the SDDC spec build (9.0 shape)

**Files:**
- Modify: `ansible/roles/vcf/templates/management-workload-domain.yaml.j2` (full rewrite)
- Modify: `ansible/roles/vcf/templates/macros.yaml.j2` (host spec + network spec macros)
- Modify: `ansible/roles/vcf/templates/nsx-spec.yaml.j2`, `cluster-spec.yaml.j2`
- Create: `ansible/roles/vcf/templates/datastore-spec.yaml.j2`, `vcf-operations-specs.yaml.j2`, `vcf-automation-spec.yaml.j2`
- Delete: `ansible/roles/vcf/templates/vsan-spec.yaml.j2`
- Create: `ansible/roles/vcf/tasks/sddc-spec/vcf-operations-specs.yaml`
- Modify: `ansible/roles/vcf/tasks/sddc-spec/storage-specs.yaml`, `compute-specs.yaml`, `vcenter-specs.yaml`, `nsx-specs.yaml`, `build-sddc-spec.yaml`
- Modify: `ansible/roles/vcf/defaults/main.yaml` (add `datacenter_name`)

- [ ] **B6.1** `management-workload-domain.yaml.j2` — full replacement:
```jinja
workflowType: "{{ vcf.platform | default('VCF') }}"
version: "{{ vcf_version }}"
sddcId: "{{ sddc_id }}"
vcfInstanceName: "{{ vcf.instance_name }}"
ceipEnabled: {{ vcf.ceip_enabled | bool }}
skipEsxThumbprintValidation: {{ vcf.skip_esx_thumbprint_validation | bool }}
skipGatewayPingValidation: {{ vcf.skip_gateway_ping_validation | bool }}

{% if management_pool_name is defined %}
managementPoolName: "{{ management_pool_name }}"
{% endif %}

ntpServers: {{ ntp_servers }}

dnsSpec:
  subdomain: "{{ subdomain }}"
  nameservers:
  - "{{ dns_servers[0] }}"
{% if dns_servers[1] is defined and dns_servers[1] %}
  - "{{ dns_servers[1] }}"
{% endif %}

sddcManagerSpec:
  hostname: "{{ sddc_manager_spec.hostname }}"
  rootPassword: "{{ sddc_manager_spec.root_user_credentials.password }}"
  sshPassword: "{{ sddc_manager_spec.second_user_credentials.password }}"
  localUserPassword: "{{ sddc_manager_spec.local_user_password }}"
  useExistingDeployment: false

vcenterSpec:
  vcenterHostname: "{{ vcenter_spec.vcenter_hostname }}"
  rootVcenterPassword: "{{ vcenter_spec.root_password }}"
  ssoDomain: "{{ psc_specs.sso_domain_name }}"
  adminUserSsoPassword: "{{ psc_specs.sso_admin_password }}"
  vmSize: "{{ vcenter_spec.vm_size }}"
  storageSize: ""
  useExistingDeployment: false

{% include 'network-specs.yaml.j2' %}

{% include 'nsx-spec.yaml.j2' %}

{% include 'datastore-spec.yaml.j2' %}

{% include 'dvs-specs.yaml.j2' %}

{% include 'cluster-spec.yaml.j2' %}

{% include 'host-specs.yaml.j2' %}

{% include 'vcf-operations-specs.yaml.j2' %}
{% if vcf.deploy_automation | bool %}

{% include 'vcf-automation-spec.yaml.j2' %}
{% endif %}
```
(Removed vs 5.2: `taskName`, `fipsEnabled`, `deployWithoutLicenseKeys`, `esxLicense`, `proxySpec`, `dvSwitchVersion`, `pscSpecs`, `vcenterSpec.vcenterIp/licenseFile`, `sddcManagerSpec.ipAddress/secondUserCredentials-as-object`.)
- [ ] **B6.2** `macros.yaml.j2` — `render_host_spec` (9.0: short hostname, no association/ip/vSwitch):
```jinja
{% macro render_host_spec(host, hostvars, subdomain, skip_thumbprints) %}
- hostname: "{{ host | regex_replace('\\.' ~ (subdomain | regex_escape) ~ '$', '') }}"
  credentials:
    username: "{{ hostvars[host].ansible_user }}"
    password: "{{ hostvars[host].ansible_password }}"
{% if not (skip_thumbprints | bool) %}
  sshThumbprint: "{{ hostvars[host].esxi_ssh_thumbprint | default('') }}"
  sslThumbprint: "{{ hostvars[host].esxi_ssl_thumbprint | default('') }}"
{% endif %}
{% endmacro %}
```
and update `host-specs.yaml.j2` accordingly:
```jinja
{% from 'macros.yaml.j2' import render_host_spec %}

hostSpecs:
{% for host in groups['management'] %}
{{ render_host_spec(host, hostvars, subdomain, vcf.skip_esx_thumbprint_validation | default(false)) | indent(2, True) }}
{% endfor %}
```
`render_network_spec`: cast ints (`vlanId: {{ network.vlan_id | int }}`, `mtu: {{ network.mtu | int }}`); keep `subnet`/`gateway`/`includeIpAddressRanges`/`portGroupKey`/`teamingPolicy`/`activeUplinks`/`standbyUplinks` (all still valid in 9.0).
- [ ] **B6.3** `nsx-spec.yaml.j2` — 9.0 shape (managers list = hostname only; drop `vip`, `nsxtLicense`; add overlay flag):
```jinja
nsxtSpec:
  nsxtManagerSize: "{{ nsx_spec.nsxt_manager_size }}"
  nsxtManagers:
  - hostname: "{{ nsx_spec.nsxt_manager_a.hostname }}"
  - hostname: "{{ nsx_spec.nsxt_manager_b.hostname }}"
  - hostname: "{{ nsx_spec.nsxt_manager_c.hostname }}"
  vipFqdn: "{{ nsx_spec.nsxt_manager_vip.hostname }}"
  rootNsxtManagerPassword: "{{ nsx_spec.nsxt_manager_root_password }}"
  nsxtAdminPassword: "{{ nsx_spec.nsxt_manager_admin_password }}"
  nsxtAuditPassword: "{{ nsx_spec.nsxt_manager_audit_password }}"
  transportVlanId: {{ nsx_spec.tep_transport_vlan_id | int }}
  skipNsxOverlayOverManagementNetwork: true
  ipAddressPoolSpec:
    name: "{{ nsx_spec.nsxt_host_overlay_tep_ip_pool.name }}"
    description: "{{ nsx_spec.nsxt_host_overlay_tep_ip_pool.description }}"
    subnets:
    - ipAddressPoolRanges:
      - start: "{{ nsx_spec.nsxt_host_overlay_tep_ip_pool.subnet_ip_rage.start }}"
        end: "{{ nsx_spec.nsxt_host_overlay_tep_ip_pool.subnet_ip_rage.end }}"
      cidr: "{{ nsx_spec.nsxt_host_overlay_tep_ip_pool.subnet_ip_rage.cidr }}"
      gateway: "{{ nsx_spec.nsxt_host_overlay_tep_ip_pool.subnet_ip_rage.gateway }}"
  useExistingDeployment: false
```
- [ ] **B6.4** New `datastore-spec.yaml.j2` (replaces vsan-spec.yaml.j2):
```jinja
datastoreSpec:
  vsanSpec:
    datastoreName: "{{ vsan_spec.datastore_name }}"
{% if not (vsan_spec.esa_config | bool) %}
    vsanDedup: {{ vsan_spec.vsan_dedup | bool }}
{% endif %}
    esaConfig:
      enabled: {{ vsan_spec.esa_config | bool }}
    failuresToTolerate: {{ vsan_spec.failures_to_tolerate | int }}
```
and in `sddc-spec/storage-specs.yaml` drop `hcl_file`/`license_file`, add `failures_to_tolerate: "{{ extensionInstanceVariables.vsan_failures_to_tolerate | default(1) }}"`.
- [ ] **B6.5** `cluster-spec.yaml.j2` — add `datacenterName`, drop `clusterImageEnabled`/`vmFolders`:
```jinja
{% from 'macros.yaml.j2' import render_resource_pool %}
clusterSpec:
  datacenterName: "{{ cluster_spec.datacenter_name }}"
  clusterName: "{{ cluster_spec.name }}"
  clusterEvcMode: "{{ cluster_spec.evc_mode }}"
  resourcePoolSpecs:
{% for resource_pool in cluster_spec.resource_pool_specs_consolidated %}
{{ render_resource_pool(resource_pool) | indent(2, True) }}
{% endfor %}
```
In `sddc-spec/compute-specs.yaml`: add `datacenter_name: "{{ extensionInstanceVariables.vcenter_datacenter_name | default(sddc_id ~ '-dc1') }}"`, change `evc_mode` default `'n/a'` → `''`, remove `image_enabled`/`vm_folders`. Add `datacenter_name` default also to `ansible/roles/vcf/defaults/main.yaml` if referenced elsewhere.
- [ ] **B6.6** New `ansible/roles/vcf/tasks/sddc-spec/vcf-operations-specs.yaml`:
```yaml
---
- name: Build | Extract IP allocations for VCF Operations components
  set_fact:
    vcf_ops_config: "{{ management_ip_allocations | selectattr('tags.role', 'equalto', 'vcf-operations') | first | default({}) }}"
    ops_fleet_mgmt_config: "{{ management_ip_allocations | selectattr('tags.role', 'equalto', 'ops-fleet-management') | first | default({}) }}"
    ops_collector_config: "{{ management_ip_allocations | selectattr('tags.role', 'equalto', 'ops-collector') | first | default({}) }}"
    vcf_automation_config: "{{ management_ip_allocations | selectattr('tags.role', 'equalto', 'vcf-automation') | first | default({}) }}"

- name: Build | VCF Operations specs
  set_fact:
    vcf_ops_spec:
      node1_hostname: "{{ vcf_ops_config.fqdn | default('') | split('.') | first }}"
      root_password: "{{ extensionInstanceVariables.vcf_ops_root_password | default('VMw@re1!VMw@re1!') }}"
      admin_password: "{{ extensionInstanceVariables.vcf_ops_admin_password | default('VMw@re1!VMw@re1!') }}"
      appliance_size: "{{ extensionInstanceVariables.vcf_ops_appliance_size | default('small') }}"
    ops_fleet_mgmt_spec:
      hostname: "{{ ops_fleet_mgmt_config.fqdn | default('') | split('.') | first }}"
      root_password: "{{ extensionInstanceVariables.ops_fleet_mgmt_root_password | default('VMw@re1!VMw@re1!') }}"
      admin_password: "{{ extensionInstanceVariables.ops_fleet_mgmt_admin_password | default('VMw@re1!VMw@re1!') }}"
    ops_collector_spec:
      hostname: "{{ ops_collector_config.fqdn | default('') | split('.') | first }}"
      root_password: "{{ extensionInstanceVariables.ops_collector_root_password | default('VMw@re1!VMw@re1!') }}"
    vcf_automation_spec:
      hostname: "{{ vcf_automation_config.fqdn | default('') | split('.') | first }}"
      admin_password: "{{ extensionInstanceVariables.vcf_automation_admin_password | default('VMw@re1!VMw@re1!') }}"
      internal_cluster_cidr: "{{ extensionInstanceVariables.vcf_automation_internal_cluster_cidr | default('198.18.0.0/15') }}"
      node_prefix: "{{ sddc_id }}-auto"
      ip_pool: >-
        {{ (vm_management_selected_network | json_query("subnets[].ipRanges[?tags.role=='automation-ip-pool'][]") | first | default({}))
           | ternary([ (vm_management_selected_network | json_query("subnets[].ipRanges[?tags.role=='automation-ip-pool'][]") | first).startIp,
                       (vm_management_selected_network | json_query("subnets[].ipRanges[?tags.role=='automation-ip-pool'][]") | first).endIp ], []) }}
```
Register it in `build-sddc-spec.yaml` after `vcenter-specs.yaml`.
- [ ] **B6.7** New `vcf-operations-specs.yaml.j2`:
```jinja
vcfOperationsSpec:
  nodes:
  - hostname: "{{ vcf_ops_spec.node1_hostname }}"
    rootUserPassword: "{{ vcf_ops_spec.root_password }}"
    type: "master"
  adminUserPassword: "{{ vcf_ops_spec.admin_password }}"
  applianceSize: "{{ vcf_ops_spec.appliance_size }}"
  useExistingDeployment: false

vcfOperationsFleetManagementSpec:
  hostname: "{{ ops_fleet_mgmt_spec.hostname }}"
  rootUserPassword: "{{ ops_fleet_mgmt_spec.root_password }}"
  adminUserPassword: "{{ ops_fleet_mgmt_spec.admin_password }}"
  useExistingDeployment: false

vcfOperationsCollectorSpec:
  hostname: "{{ ops_collector_spec.hostname }}"
  rootUserPassword: "{{ ops_collector_spec.root_password }}"
  applianceSize: "small"
  useExistingDeployment: false
```
and `vcf-automation-spec.yaml.j2`:
```jinja
vcfAutomationSpec:
  hostname: "{{ vcf_automation_spec.hostname }}"
  adminUserPassword: "{{ vcf_automation_spec.admin_password }}"
  internalClusterCidr: "{{ vcf_automation_spec.internal_cluster_cidr }}"
  nodePrefix: "{{ vcf_automation_spec.node_prefix }}"
  ipPool: {{ vcf_automation_spec.ip_pool | to_json }}
```
- [ ] **B6.8** Remove license rendering from `vcenter-specs.yaml`/`nsx-specs.yaml` facts (`license_file`, `nsxt_license` keys).
- [ ] **B6.9** Run the harness — must now PASS:
```bash
cd tests && ansible-playbook -i inventory.yaml render-spec.yaml
# Expect: all asserts OK; inspect /tmp/sddc-spec-9.json manually once against F7–F10
```
- [ ] **B6.10** Commit: `feat: VCF 9.0 SDDC bring-up spec (datastoreSpec, ops specs, 9.0 host/nsx/cluster shapes)`.

### Task B7: Bring-up task — Bearer auth + 9.0 polling

**Files:**
- Modify: `ansible/roles/vcf/tasks/deploy-mgmt-workload-domain.yaml`

- [ ] **B7.1** At the top, add `- ansible.builtin.include_tasks: installer/get-installer-token.yaml` (validation block) and again before the deploy block (bring-up runs hours — refresh).
- [ ] **B7.2** Global mechanical changes throughout the file: URL host stays `https://{{ installer.ipv4_address }}` (rename `cba.` → `installer.`); **delete** `user:`, `password:`, `force_basic_auth:` from every `uri` task and add `headers: "{{ installer_auth_headers }}"`; keep all retry/poll/rescue logic and the `BRINGUP_ALREADY_EXISTS` recovery path (verify the 9.0 errorCode name during E2E — flagged in Unresolved Questions).
- [ ] **B7.3** Polling budgets: validation poll stays `validation_api_retries` (raise default to 360 × 10 s in `management-services.yaml`); deploy poll uses the new 1440 × 30 s (12 h). Accept `ROLLBACK_SUCCESS` as a failure state in `failed_when` (new in 9.0):
```yaml
failed_when: cba_api_get_deploy_task_mgmt_workload_result.json.status in ['COMPLETED_WITH_FAILURE', 'ROLLBACK_SUCCESS']
```
(rename registered var prefixes `cba_api_*` → `installer_api_*` while at it).
- [ ] **B7.4** Syntax check + commit: `feat: bring-up via VCF Installer API (bearer auth, 9.0 task states)`.

### Task B8: Validations cleanup

**Files:**
- Modify: `ansible/roles/vcf/tasks/validate-sddc-spec.yaml`
- Delete: `ansible/roles/vcf/tasks/validations/validate-licenses.yaml`
- Rename: `validations/validate-cba.yaml` → `validations/validate-installer.yaml`
- Modify: `validations/validate-basic.yaml`, `validations/validate-infrastructure.yaml`, `validations/validate-networks.yaml`

- [ ] **B8.1** `validate-sddc-spec.yaml`: drop the license import; rename cba import to `validate-installer.yaml`; add a new import `validations/validate-depot.yaml`.
- [ ] **B8.2** `validate-installer.yaml`: keep network-params/ova_url/datastore prechecks (rename `cba` → `installer` vars); update the role-tag references.
- [ ] **B8.3** New `validations/validate-depot.yaml` — fail fast before deploying anything:
```yaml
---
- name: Validate | Depot credentials provided
  ansible.builtin.assert:
    that: depot.password | length > 0
    fail_msg: "depot_password input is required for VCF 9 (offline depot)"

- name: Validate | Depot catalog reachable with credentials
  ansible.builtin.uri:
    url: "https://{{ depot.hostname }}:{{ depot.port }}/PROD/metadata/productVersionCatalog/v1/productVersionCatalog.json"
    method: HEAD
    url_username: "{{ depot.username }}"
    url_password: "{{ depot.password }}"
    force_basic_auth: true
    status_code: [200]
    validate_certs: false
  delegate_to: localhost

- name: Validate | ESX ISO for target release present in depot (the known mirror gap)
  ansible.builtin.uri:
    url: "https://{{ depot.hostname }}:{{ depot.port }}/PROD/COMP/ESX_HOST/VMware-VMvisor-Installer-{{ vcf_version | regex_replace('\\.0$', '') }}.0.24957456.x86_64.iso"
    method: HEAD
    url_username: "{{ depot.username }}"
    url_password: "{{ depot.password }}"
    force_basic_auth: true
    status_code: [200]
    validate_certs: false
  delegate_to: localhost
  when: vcf_version is match('^9\.0\.1')
```
- [ ] **B8.4** `validate-basic.yaml`: add a guard for the F16 `.local` problem:
```yaml
- name: Validate | DNS zone is not .local (breaks VCF 9 services platform)
  ansible.builtin.assert:
    that: not (domain | lower).endswith('.local')
    fail_msg: "VCF 9 deployment fails with .local domains — use a routable DNS zone"
  when: vcf.deploy_automation | bool
```
Remove `repository_base_url`-required logic only if `ova_url` empty stays (unchanged semantics).
- [ ] **B8.5** Remove `licenses_required`-conditional blocks from `validate-networks.yaml`/`validate-infrastructure.yaml` if present. Syntax check + harness + commit: `refactor: 9.0 validations (depot check, drop licensing, .local guard)`.

### Task B9: esxi role — 9.x host prep

**Files:**
- Modify: `ansible/roles/esxi/tasks/main.yaml`
- Create: `ansible/roles/esxi/tasks/verify-certificate.yaml`
- Modify: `ansible/roles/esxi/files/get-ssh-fingerprint.sh`

- [ ] **B9.1** New `verify-certificate.yaml` (cert regeneration itself lives in the OS template firstboot — Task A2; this verifies it):
```yaml
---
- name: Fetch ESXi SSL certificate subject CN
  ansible.builtin.command:
    argv: ["/bin/sh", "-c", "echo | openssl s_client -connect {{ esxi_hostname }}:443 2>/dev/null | openssl x509 -noout -subject"]
  register: esxi_cert_subject
  changed_when: false
  delegate_to: localhost

- name: Assert certificate CN matches host FQDN
  ansible.builtin.assert:
    that: inventory_hostname | lower in esxi_cert_subject.stdout | lower
    fail_msg: >-
      ESXi cert CN mismatch on {{ inventory_hostname }} ({{ esxi_cert_subject.stdout }}).
      VCF 9 validation will fail — regenerate with /sbin/generate-certificates on the host
      (should be done by the OS template firstboot).
```
Import it in `main.yaml` before the thumbprint collection.
- [ ] **B9.2** `get-ssh-fingerprint.sh`: keep RSA as primary (9.0 hostSpec sshThumbprint is RSA SHA256) but make the keyscan resilient: `ssh-keyscan -T 5 -t rsa,ecdsa <host>` and select the rsa line if present, else first line (flagged in Unresolved Questions — verify ESX 9 still serves ssh-rsa host keys; if not, set `skip_esx_thumbprint_validation: true`).
- [ ] **B9.3** Syntax check + commit: `feat: esxi role 9.x prep (cert CN verification, keyscan hardening)`.

### Task B10: Scale flows against SDDC Manager 9.x

The SDDC Manager v1 endpoints used by `scale.yaml` (`/v1/tokens`, `/v1/hosts`, `/v1/hosts/validations`, `/v1/clusters`, `/v1/clusters/{id}/validations`, `PATCH /v1/clusters/{id}`, `/v1/tasks/{id}`) all still exist in SDDC Manager 9.x. Changes are incremental, not structural:

**Files:**
- Modify: `ansible/roles/vcf/tasks/sddc-manager/add-hosts-to-cluster.yaml`
- Modify: `ansible/roles/vcf/templates/host-commission-spec.json.j2`, `clusters/cluster-expand.json.j2`, `clusters/cluster-compact.json.j2` (inspect against live API)

- [ ] **B10.1** Remove the vLCM "personality/transition" branch in `add-hosts-to-cluster.yaml` (9.x management clusters are always image-based; the `cluster_transition_state_required` + `GET /v1/personalities` logic — which also contains a latent bug reading personalities from the cluster response — is dead code in 9).
- [ ] **B10.2** Against a deployed 9.0.1 SDDC Manager, diff the commission/expand spec templates with the live API docs (`https://<sddc-manager>/v1/api-doc` or developer.broadcom.com SDDC Manager 9.0): check `HostCommissionSpec` fields (`storageType` — must be `VSAN_ESA` when ESA cluster; `networkPoolId/Name`) and `ClusterUpdateSpec`/expansion spec host fields (`vmNics`, `vdsName` default `m-cl1-vds1` must match the dvsName built in `dvs-specs.yaml.j2` — they already agree). Adjust templates as found.
- [ ] **B10.3** Note: host commission in 9.0.0 enforces the vSAN ESA HCL check (KB-documented bypass exists in 9.0.1: `vsan.esa.sddc.managed.disk.claim=true`). With OSA (our default) no HCL concern.
- [ ] **B10.4** Syntax check + commit: `fix: scale flows for SDDC Manager 9.x (drop vLCM transition, verify specs)`.

### Task B11: Docs

**Files:**
- Modify: `README.md`, `ansible/README.md`

- [ ] **B11.1** Rewrite `README.md`: supported version 9.0.1; prerequisites — min 3 hosts (4 recommended), 10 GbE NICs, ESX 9.0.1.0-24957456 template `esxi-9-24957456-cluster-node`, offline depot URL + required content (incl. ESX ISO + fresh HCL for ESA), the VCF Installer 9.0.2.0 OVA note (F1), no license keys (90-day eval, license via VCF Operations afterwards), new appliance footprint (7 VMs min) and the new IP/DNS records, routable (non-`.local`) DNS zone requirement, NSX `small` size no longer exists.
- [ ] **B11.2** `ansible/README.md`: document all new/renamed inputs (`installer_*`, `depot_*`, `vcf_ops_*`, `ops_fleet_mgmt_*`, `ops_collector_*`, `deploy_vcf_automation`, `vcf_automation_*`, `vsan_failures_to_tolerate`, `skip_gateway_ping_validation`) and removed ones (licenses, proxy, aria, `cba_*`).
- [ ] **B11.3** Commit: `docs: VCF 9.0.1 requirements and inputs`.

### Task B12: Packaging + execution environment

- [ ] **B12.1** Build the EE image from the (already 9.0-pinned) `execution-environment.yml` and publish it where the site controller can pull it:
```bash
pip install ansible-builder && ansible-builder build -f execution-environment.yml -t registry.metalsoft.dev/sc/sc-ansible-playbook-runner:vcf9 --container-runtime docker
```
**Important:** the platform does NOT read this file at runtime — the site controller's configured `AnsibleRunnerExecutionEnv` image is used. Either update the site config to this image or add an `OciImage` asset to extension.json (per-task EE override, v1 agent only). Confirm which agent version runs in the target site.
- [ ] **B12.2** Build the bundle zip (content = the `ansible/` directory at archive root, same layout as v1.0.6):
```bash
cd ansible && zip -r ../vmware-cloud-foundation9-v2.0.0.zip . -x '*.DS_Store' && cd ..
```
- [ ] **B12.3** Upload to `https://repo.metalsoft.io/.extensions_ms/vmware-cloud-foundation9/vmware-cloud-foundation9-v2.0.0.zip` (must be reachable by the **global** controller), register/update the extension:
```bash
metalcloud-cli extension create --definition extension.json   # or: extension edit + publish
```
- [ ] **B12.4** Commit remaining artifacts: `chore: v2.0.0 bundle packaging`.

### Task B13: End-to-end validation

- [ ] **B13.1** Dry-run the spec path standalone: `cd tests && ansible-playbook -i inventory.yaml render-spec.yaml` green; eyeball `/tmp/sddc-spec-9.json` once more against William Lam's working `vcf90-two-node.json` shape.
- [ ] **B13.2** Deploy the extension on 4 servers with the `esxi-9-24957456-cluster-node` template. Watch phases: ESXi prep → installer OVA (~15 min) → depot sync (minutes) → binary downloads (~30 min–2 h from LAN mirror) → `POST /v1/sddcs/validations` (fix data errors here — cheap) → bring-up (~3 h). Progress also visible at `https://installer.<zone>/vcf-installer-ui/portal/progress-viewer`.
- [ ] **B13.3** On validation failures, iterate on the spec; the installer UI's "export JSON spec" of a manually-completed wizard is the fastest way to diff a known-good spec against ours.
- [ ] **B13.4** Test `onEdit` scale-out (+1 host: commission + cluster expand) and scale-in (−1 host: compact + decommission) against the resulting SDDC Manager 9.0.1.
- [ ] **B13.5** Confirm 90-day eval state and document the post-deploy licensing step (VCF Operations → Business Services) in README.

---

## Decisions baked into this plan (changeable)

- **vSAN OSA by default** (`vsan_esa_enabled=false` stays) — avoids the stale-HCL blocker (F12/A1.3); ESA remains an input.
- **VCF Automation off by default** (`deploy_vcf_automation=false`) — saves 1 FQDN + 2 IPs + the `.local` constraint; spec block included only when enabled.
- **3 NSX managers + VIP kept** (production posture; 9.0 allows 1 for labs).
- **Dedicated TEP VLAN kept** (`skipNsxOverlayOverManagementNetwork: true`) — preserves the existing `vcf-nsx` logical network design.
- **Installer OVA pulled from `repository_base_url + /.vmware/vcf/9.0.1.0/<ova>`** (same convention as 5.2.2) — ops must place the 9.0.2.0 OVA there (it can be copied from the depot mirror); alternatively set the `ova_url` input directly.
- **Input renames (`cba_*` → `installer_*`)** — this is a new extension (`label: vcf9`), no backwards-compat burden.

## Unresolved questions

1. **ESX 9.0.1 ISO acquisition** — who has the Broadcom entitlement/download token to fetch `VMware-VMvisor-Installer-9.0.1.0.24957456.x86_64.iso` (needed twice: depot `/PROD/COMP/ESX_HOST/` and `repo.metalsoft.io/.vmware/` for the OS template)?
2. **First host's local datastore capacity** — installer appliance is 914 GB thin + downloads ~70 GB of binaries onto it. Is `datastore1` on the management hosts large enough (recommend ≥150 GB free real capacity), or should `installer_datastore` point elsewhere?
3. **Host FQDN scheme** — 9.0 resolves hosts as `<short-hostname>.<dnsSpec.subdomain>`. MetalSoft host inventory names are `subdomainPermanent`. Is the instance FQDN always `<short>.<baseDomain>` in the target site (i.e., `subdomain` strip in the host-spec macro is safe)? If instances live in a different zone than `baseDomain`, the macro needs adjusting.
4. **DNS zone** — is the target zone routable (not `.local`)? Hard requirement if Automation is enabled; recommended regardless (F16).
5. **`vcfOperationsCollectorSpec` size key** — API docs say `applianceSize`, Lam's working 9.0 file uses `applicationSize` (ignored→default `small`). We use `applianceSize`+`small`; verify once against the live installer's `GET /v1/api-doc`.
6. **`BRINGUP_ALREADY_EXISTS` errorCode** — does the 9.0 installer return the same code on duplicate `POST /v1/sddcs` (retry-recovery path in B7.2)? Verify during E2E.
7. **ESX 9 SSH host keys** — does ESXi 9.0.1 still serve an `ssh-rsa` host key for the `sshThumbprint`? If not: `skip_esx_thumbprint_validation=true` or switch thumbprint type (B9.2).
8. **Token TTL** — installer `/v1/tokens` access-token lifetime is undocumented; plan re-authenticates per phase + per download-wait cycle. Confirm no 401s during the long bring-up poll (else add 401-triggered refresh in B7).
9. **EE image rollout** — which agent (v1/v2) runs in the target site, and is the per-task `OciImage` EE override available, or must the site-wide `AnsibleRunnerExecutionEnv` be updated (B12.1)?
10. **repo.metalsoft.io upload process** — what's the actual mechanism/credentials to publish the bundle zip and the OVA/ISO artifacts (B12.3 / A2.1)?
11. **Scale-spec field drift** — `HostCommissionSpec`/cluster-expand specs against SDDC Manager 9.0.1 (B10.2) need live verification; not fully derivable from public docs.
