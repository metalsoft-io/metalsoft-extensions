## Server Validation Workflow

This workflow performs vendor-specific out-of-band (OOB) server health checks using iDRAC (Dell) or iLO Redfish (HP/HPE).

### Playbook

`server_validation_playbook.yaml` loads `variables.json`, derives OOB credentials, and dynamically includes one of:

* `roles/dell_health_check` – Uses `dellemc.openmanage.idrac_gather_facts` to validate:
  * Serial number
  * Overall system health
  * Memory / Cooling / CPU / Storage rollup status
* `roles/hp_health_check` – Uses `community.general.redfish_info` to validate:
  * System health
  * Processor health
  * Memory health

If the vendor string (from `task_vars.server.vendor`) does not include `Dell`, `HP`, or `HPE`, the playbook skips vendor checks.

### Required Collections

Install required collections:

```bash
ansible-galaxy collection install -r collections/requirements.yml
```

### Variables

`variables.json` must contain a `server` object with at least:

```json
{
  "server": {
    "managementAddress": "10.0.0.10",
    "username": "root",
    "serialNumber": "ABC1234",
    "vendor": "Dell Inc."
  }
}
```

Supply the OOB password via one of:

* Extra var: `-e oob_password='PlainPassword'`
* Environment variable: `OOB_PASSWORD=PlainPassword ansible-playbook ...`
* Vaulted var overriding `oob_password`

### Run

```bash
ansible-playbook server_validation_playbook.yaml -e oob_password='PlainPassword'
```

### Failure Conditions

The playbook fails when:

* Serial number (Dell) mismatches expected
* Any health rollup (Dell) not OK
* HP/HPE system / processor / memory health not OK

### Extending

Add new vendor roles under `roles/<vendor>_health_check/` and extend the conditional logic in the playbook.
# Simple ansible workflow example

This workflow will execute on `serverRegister` and will execute a given ssh command on a remote host.