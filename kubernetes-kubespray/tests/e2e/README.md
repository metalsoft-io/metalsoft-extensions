# Live E2E

One cluster at a time when the site's network profile gives every infrastructure the same VLAN. Delete-deploy
the previous test infrastructure first.

## Driving it (REST API)

```bash
export METALCLOUD_ENDPOINT=https://<controller> METALCLOUD_API_KEY=<key>
MC=/path/to/metalcloud-ai-agent-plugin/scripts/mc-api.sh
```

1. **Create the infrastructure:** `POST /infrastructures {"siteId":1,"label":"k8stestN"}`.
2. **Add the extension instance:** `POST /infrastructures/<id>/extension-instances {"label":"k8sN","extensionId":<ext>,"inputVariables":[...all inputs...]}`.
3. **Deploy:** `POST /infrastructures/<id>/actions/deploy` with `{"allowDataLoss":false,"shutdownOptions":{…}}`.
   - If every stage after `validate` is `skipped`, read `GET /job-groups/<group>` → `cancelReason`. Usually the VLAN is still held by another infrastructure, or by an orphaned logical network.
   - Never delete an extension instance from an infrastructure; delete the infrastructure.
4. **Edit:** `PATCH /extension-instances/<id>/config` with If-Match `<config.revision>`, sending all inputs **except the setOnly ones**, then deploy.
5. **Logs:**
   - A successful task keeps no stdout in the API.
   - A failed one has it in `GET /jobs/<id>/exceptions`.
   - Failed tasks are auto-retried by the platform; stop that with `POST /jobs/<id>/actions/skip`.
6. **Outputs:** `GET /extension-instances/<id>` → `outputVariables` (`admin_kubeconfig` is masked).
7. **Console:** iDRAC Redfish screenshot (`DellLCService.ExportServerScreenShot`), with the BMC credentials from `GET /servers/<id>/credentials`, never printed.

## Matrix

| ID | Edit | Pass |
|---|---|---|
| E1 | create 1 CP + 1 worker (defaults) | Task green. Outputs complete: api_url, version 1.36.4, nodes, lb range, cluster_status ready |
| E4 | `drain_timeout_minutes` 10→11 only | onEdit runs; outputs re-emitted unchanged (same admin cert expiry) |
| E5 | `worker_count` 1→2 | `scale.yml`; worker_nodes lists both |
| E6 | `worker_count` 2→1 | preDeploy drains + `remove_node.yml`; worker_nodes shows the survivor |
| C1 | `control_plane_count` 1→3 | CP join + refresh; control_plane_nodes = 3 |
| C7 | `control_plane_count` 1→3 and `worker_count` +1 in one edit | one `cluster.yml` joins the CPs and the worker, then the CP refresh; state committed; all in the outputs |
| C3 | `control_plane_count` 3→1 | etcd member removal at preDeploy; control_plane_nodes = 1; cluster_id unchanged |
| U4 | `converge_generation` 0→1 | full `cluster.yml`; outputs unchanged |
| U2 | `kube_version` 1.36.4→1.35.8 | refused at preDeploy (E-K8S-007), nothing changes |
| I1 | `admin_credential_generation` 1→2 | admin_credential shows g2 |
| E2 | create 3 CP + 2 workers at 1.35.8 | Task green; 3 CP + 2 worker names in the outputs, cluster_status ready |
| U1 | `kube_version` 1.35.8→1.36.4 | etcd snapshot first; outputs show 1.36.4, same cluster_id and admin credential |
| E3 | create with the site's DNS workflow disabled | api_url and admin kubeconfig use the VIP; api_fqdn empty |
| E11 | leader crash (kubelet + kube-vip stopped, VIP deleted) | `/readyz` via the VIP back within 10 s; lease on another CP |
| E12 | SIGKILL the speaker announcing a LoadBalancer IP | another speaker announces it within 15 s |
| E13 | delete `metalsoft-admin-g<N>` binding, then a no-op edit | old kubeconfig 403; outputs show g<N+1>; old binding not recreated |
| E7 | `worker_count` −1 with the leaving worker powered off (PATCH first, read the leaver from `config.deployType = delete`, power it off, then deploy) | no drain wait on the dead node; worker_nodes shows the survivors |
| C2 | `control_plane_count` 3→5, then 5→3 | etcd 5/5 then 3/3 healthy; every apiserver `--etcd-servers` matches the members |
| C5 | `control_plane_count` −2 with one leaving CP powered off | dead member removed first; quorum kept; `/readyz` via the VIP 200 |

The API VIP / MetalLB IPs are on the node network, which is usually not routed to the workstation.
Client-side checks (kubectl through the VIP, LoadBalancer HTTP) run from the site controller (or any
host on the node network); nodes are reached from there as `ubuntu` with the instance's initial password
(`GET /server-instances/<id>/credentials`, never printed).
For E3, disable the DNS workflow for the site (`DELETE /extensions/<pdns>/siteConfig/<site>`) only for the
create, and re-enable it right after (`POST /extensions/<pdns>/siteConfig/<site> '[]'`).
