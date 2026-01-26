# Server Validation

This workflow performs vendor-specific out-of-band (OOB) server health checks using iDRAC (Dell) or iLO Redfish (HP/HPE).

This workflow will execute on `serverRegister`.

## Playbook

Note: `main.yaml` dynamically retrieves the out-of-band (OOB) password at runtime from a configured secret store (for example Vault, Ansible Vault, or an external secrets manager). This avoids keeping plaintext OOB credentials in `variables.json`. The playbook will derive the OOB username from `variables.json` (if present) and then fetch the corresponding password securely before performing vendor-specific checks.

* `roles/dell_health_check` – Uses `dellemc.openmanage.idrac_gather_facts` to validate:
  * Serial number
  * Overall system health
  * Memory / Cooling / CPU / Storage rollup status
* `roles/hp_health_check` – Uses `community.general.redfish_info` to validate:
  * System health
  * Processor health
  * Memory health

If the vendor string (from `task_vars.server.vendor`) does not include `Dell`, `HP`, or `HPE`, the playbook skips vendor checks.

### Failure Conditions

The playbook fails when:

* Serial number (Dell) mismatches expected
* Any health rollup (Dell) not OK
* HP/HPE system / processor / memory health not OK
