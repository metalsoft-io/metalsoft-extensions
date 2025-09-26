# Infoblox DNS Role (formerly PowerDNS)

This role manages DNS zones and records in an Infoblox grid using the `infoblox.nios_modules` collection. It was refactored from a PowerDNS HTTP API implementation to native Infoblox modules for idempotency and clarity.

## Features
- Create / delete forward zones
- Create / delete A, AAAA, CNAME, TXT records
- Auto-generate PTR records for A records when `ptr: enabled`
- Manage explicit PTR records
- Optional automatic reverse zone creation
- Zone deprovisioning when operation flag set

## Requirements
Install the Infoblox collection:

```bash
ansible-galaxy collection install -r collections/requirements.yml
```

Ensure the Infoblox WAPI endpoint is reachable from the Ansible control host.

## Variables
Defined in `defaults/main.yml`:

| Variable | Description | Default |
|----------|-------------|---------|
| infoblox_host | Infoblox grid host/IP | 127.0.0.1 |
| infoblox_username | API username | admin |
| infoblox_password | API password | infoblox |
| infoblox_validate_certs | Validate HTTPS certs | false |
| infoblox_wapi_version | WAPI version | 2.12 |
| infoblox_view | DNS view | default |
| default_ttl | Default record TTL | 3600 |
| create_reverse_zones | Auto create reverse zone for PTR | true |
| ptr_require_existing_zone | Fail if reverse zone missing | false |

`nios_provider` is constructed automatically from the above.

## Input Data Structure (dns_operation)
The role expects a structure with or convertible to:

```yaml
working_operation:
  zone: example.com
  nameservers: [ns1.example.com, ns2.example.com]
  soa_email: hostmaster@example.com
  records:
    - name: host1
      type: A
      status: active
      ttl: 300
      ptr: enabled
      records: [192.0.2.10]
    - name: host1
      type: AAAA
      status: active
      records: [2001:db8::10]
    - name: alias
      type: CNAME
      status: active
      records: [host1.example.com]
    - name: _test
      type: TXT
      status: active
      records: ["some text", "other"]
    - name: 10.2.0.192.in-addr.arpa.
      type: PTR
      status: deleting
      records: [host1.example.com]
  operation: dns_zone_provisioning|dns_zone_deprovisioning
```

The role contains transformation logic to adapt multiple upstream formats into `working_operation`.

## Behavior Notes
- Forward zone creation occurs only if there are active (non-PTR) records or PTR generation tasks.
- PTR records for A records with `ptr: enabled` are generated automatically.
- Reverse zones are created if `create_reverse_zones: true` and not found (best effort, idempotent) unless `ptr_require_existing_zone` is true.
- Zone deletion only happens when `working_operation.operation == dns_zone_deprovisioning`.
- IPv6 PTR (ip6.arpa) is not yet implemented (future enhancement).

## Example Playbook
```yaml
- hosts: localhost
  gather_facts: false
  vars:
    dns_operation: "{{ lookup('file', 'variables.json') | from_json }}"
    infoblox_host: grid.example.com
    infoblox_username: api-user
    infoblox_password: secret
  roles:
    - role: powerdns
```

## Limitations / Next Steps
- Add IPv6 reverse PTR support (ip6.arpa)
- Support bulk updates with `nios_record` for performance (current approach creates/deletes per value)
- Optional logging verbosity control

## License
Apache 2.0 (adjust if repository uses a different license)

## Maintainers
MetalSoft Extensions Team


## Running on MacOS X
on mac run with
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY="YES"