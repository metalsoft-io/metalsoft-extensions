# Infoblox Host Records Only Playbook

A minimal Ansible implementation that manages ONLY Infoblox host records (and optional PTR records) from MetalSoft-style variable input files.

## Key Features
- Consumes the existing `variables.json` formats (see `example-variable-json/`).
- Normalizes data into a simple `host_records` list: `[ { host_name, ipv4_list, ipv6_list, state, ttl } ]`.
- Backward compatible single-value `ipv4` / `ipv6` keys (first element of the list) remain populated for legacy tooling.
- Creates/updates/deletes Infoblox host records via `nios_host_record` (multi-IP aware).
- Optional IPv4 and IPv6 PTR creation (enabled via `create_ptr` / `create_ipv6_ptr`) with per-address looping.
- Supports deletion workflow using record status `deleting`.
- Pure host-record focus (no standalone A/AAAA/PTR management).
- **IMPORTANT: Zone management has been removed. All required DNS zones must be created manually in Infoblox before creating host records.**
- **IMPORTANT: Fallback and compat modes have been removed. Only native Infoblox host record module is used.**
- Requires WAPI version 2.13 or higher for full functionality.

## Variables
Provide these (env, inventory, or `-e`):

| Name | Required | Description |
|------|----------|-------------|
| infoblox_hostname | yes | Infoblox grid member or VIP |
| infoblox_username | yes | API username |
| infoblox_password | yes | API password |
| infoblox_wapi_version | no | Default `2.13` (required minimum) |
| infoblox_dns_view | no | DNS view for lookups (default `default`) |
| create_ptr | no | Create PTR for each IPv4 (default true) |
| create_ipv6_ptr | no | Create PTR for each IPv6 (default false) |
| delete_only | no | Skip create when true; still perform deletions |
| force_state | no | Force all records to given state (present/absent) |
| host_records_domain | no | Domain used when synthesizing from IP-only input |
| auto_load_variables_file | no | When true (default) auto `include_vars: variables.json` if file exists |
| include_wildcard_host_records | no | Include wildcard A records (names starting with *.) when deriving from clusterDNSRecordSet/serverInstanceDNSRecordSet (default false) |
| ttl (per item) | n/a | Carried from source A record when available |
| zone_name (per item) | n/a | Captured from source record `zoneName` when provided |

## Input Detection Logic
1. If `host_records` already defined, it's used directly. Provide `ipv4_list` / `ipv6_list` for multiple addresses.
2. Else if `serverInstanceDNSRecordSet.records` present: each A record becomes a host record; all A record `records[]` collected into `ipv4_list`; status `deleting` -> state=absent.
2b. Else if `clusterDNSRecordSet.records` present: same derivation behavior as serverInstanceDNSRecordSet (wildcard names skipped unless `include_wildcard_host_records=true`).
2c. Source A record `ttl` and `zoneName` are carried into each derived host record (used for zone creation if enabled).
3. Else if `serverInstanceRecordSet` structures present and `host_records_domain` set: all `instanceIpv4Ips` aggregated into one host (first IPv4 forms host name) and likewise for IPv6.
4. Backward single `ipv4` / `ipv6` convenience fields are set to the first element of their respective lists.

## Example Run
If a `variables.json` file is in the same directory as the playbook it will be auto-loaded (can disable with `-e auto_load_variables_file=false`).

```bash
ansible-galaxy collection install -r collections/requirements.yml
ansible-playbook host_records_playbook.yml \
  -e @example-variable-json/variables-with-ip.json \
  -e infoblox_hostname=10.0.0.2 \
  -e infoblox_username=api \
  -e infoblox_password=secret
```

Deletion example (records marked deleting):
```bash
ansible-playbook host_records_playbook.yml \
  -e @example-variable-json/variables-delete-3.json \
  -e infoblox_hostname=10.0.0.2 -e infoblox_username=api -e infoblox_password=secret
```

IPv6 + multi-IP host record:
```bash
ansible-playbook host_records_playbook.yml \
  -e @example-variable-json/variables-ipv6-create.json \
  -e infoblox_hostname=10.0.0.2 -e infoblox_username=api -e infoblox_password=secret \
  -e host_records_domain=example.com
```

## Notes
- **CRITICAL: All required DNS zones must be created manually in Infoblox before running this playbook. This role no longer creates zones automatically.**
- Reverse zones must already exist for PTR creation.
- For bulk customizations, predefine `host_records` before role include to bypass normalization.
- Provide `ipv4_list` / `ipv6_list` directly for exact control; omit single-value keys if supplying lists (they will be inferred).
- Tested logically with provided JSON schemas; adjust `infoblox_wapi_version` if running newer grid.
- Requires WAPI version 2.13 or higher. Fallback and compat modes have been removed for simplicity.


## to create the zip file

zip infoblox-hosts.zip -r collections library roles host_records_playbook.yml 


## License
MIT (adjust as needed)
