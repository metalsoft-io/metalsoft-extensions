"""kubernetes-kubespray: planner and helpers (stdlib only; shared by the playbooks and tests/).

Filters
  k8s_plan(state, desired, view, stage)   -> plan dict (what this run does, or why it refuses)
  k8s_ranges(raw_ranges)                  -> [{"start", "end", "count"}] from any record-set range shape
  k8s_rfc1123(name)                       -> True when name is a valid lower-case DNS name
  k8s_version_tuple(version)              -> (major, minor, patch)
  k8s_overrides_check(value, bootstrapped) -> {"vars", "denied", "frozen_ignored", "errors"}
  k8s_cidr_overlaps(list_of_cidrs)        -> list of "a overlaps b"
  k8s_members(hosts, server_ids)          -> {host: {"server_instance_id": id}}
  k8s_net_errors(net)                     -> address-plan problems (CIDRs, VIP, pool, DNS)

The planner never touches the network; every fact it needs arrives in `view`.
Message ids (E-K8S-NNN) are stable: the README troubleshooting table refers to them.
"""

import ipaddress
import json
import re

# Inputs that must never change after create (the platform's setOnly is not relied on).
CREATE_ONLY = ("kube_proxy_mode", "pod_network_cidr", "service_network_cidr", "cluster_dns_domain")
ADDONS = ("metrics_server", "local_path_provisioner", "gateway_api_crds", "metallb")

# site_kubespray_overrides policy (plan "Tier A" = wrapper-owned, "Tier B" = create-only).
TIER_A_KEYS = frozenset("""
kube_version kube_version_min_required upgrade_cluster_setup ignore_assert_errors skip_confirmation
reset_confirmation reset_nodes allow_ungraceful_removal node serial kubespray_any_errors_fatal
upgrade_node_confirm upgrade_node_post_upgrade_confirm ip access_ip ip6 access_ip6 main_ip main_access_ip
etcd_member_name etcd_access_address etcd_address kube_override_hostname override_system_hostname
kube_network_plugin kube_network_plugin_multus loadbalancer_apiserver loadbalancer_apiserver_localhost
loadbalancer_apiserver_type loadbalancer_apiserver_port apiserver_loadbalancer_domain_name
supplementary_addresses_in_ssl_keys kube_apiserver_bind_address kube_apiserver_port kube_proxy_mode
kube_proxy_strict_arp kube_proxy_remove calico_nftable_mode upstream_dns_servers enable_nodelocaldns
kube_encrypt_secret_data auto_renew_certificates metrics_server_enabled local_path_provisioner_enabled
local_path_provisioner_is_default_storageclass gateway_api_enabled kube_external_ca_mode authorization_modes
kube_apiserver_use_authorization_config_file kube_apiserver_authorization_config_authorizers rbac_enabled
credentials_dir artifacts_dir download_run_once download_localhost download_force_cache download_cache_dir
download_keep_remote_cache kubeconfig_localhost kubectl_localhost kubeconfig_localhost_ansible_host
unsafe_show_logs system_upgrade system_upgrade_reboot etcd_retries etcd_deployment_type container_manager
etcd_backup_retention_count kubeadm_backup_retention_count kube_pods_subnet kube_service_addresses dns_domain
""".split())
TIER_A_PREFIXES = ("ansible_", "kube_vip_", "metallb_", "ntp_", "drain_", "cilium_")
TIER_B_KEYS = frozenset("""
kube_network_node_prefix kube_pods_subnet_ipv6 kube_service_addresses_ipv6 kube_network_node_prefix_ipv6
ipv4_stack ipv6_stack enable_dual_stack_networks calico_pool_blocksize calico_pool_cidr calico_pool_name
calico_ipip_mode calico_vxlan_mode calico_network_backend calico_datastore calico_vxlan_vni calico_vxlan_port
cluster_name dns_mode resolvconf_mode nodelocaldns_ip cert_management kube_encryption_algorithm
kube_encryption_resources kube_owner kube_cert_group kube_config_dir kube_cert_dir bin_dir etcd_data_dir
""".split())
OVERRIDES_MAX_BYTES = 64 * 1024
_KEY_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
_DNS_LABEL = r"[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?"
_RFC1123 = re.compile(r"^%s(\.%s)*$" % (_DNS_LABEL, _DNS_LABEL))

MESSAGES = {
    "E-K8S-001": "Create-only setting(s) changed after create: {keys}. Revert them; they cannot change on a running cluster.",
    "E-K8S-003": "control_plane_count must change by exactly 2 per edit (1<->3, 3<->5); requested {cp_from} -> {cp_to}.",
    "E-K8S-004": "control_plane_count must be odd (1, 3 or 5); got {cp_to}.",
    "E-K8S-005": "Control-plane nodes would be added ({joining}) and removed ({leaving}) in one edit. Replacing control-plane nodes is not supported; scale out first, then in.",
    "E-K8S-006": "{what} must be the only change in its edit. Also requested: {others}. Split the edit.",
    "E-K8S-007": "kube_version {to} is lower than the running {frm}. Downgrades are not supported.",
    "E-K8S-008": "kube_version {frm} -> {to} skips a minor version. Upgrade one minor at a time (next: {next}).",
    "E-K8S-009": "kube_version {to} is not offered by this extension version (offered: {offered}).",
    "E-K8S-013": "Add-on(s) {addons} cannot be switched off once installed (kubespray never uninstalls). Switch them back on.",
    "E-K8S-014": "{label} must never decrease (recorded {old}, requested {new}).",
    "E-K8S-016": "The first control-plane node {host} is not reachable over SSH; nothing can be changed safely. Bring it back and retry.",
    "E-K8S-017": "New node(s) {hosts} are not reachable over SSH; they cannot join. Retry once they are up.",
    "E-K8S-019": "etcd has no quorum ({healthy}/{members} healthy). Restore it before any change (see README: recovery).",
    "E-K8S-020": "Control-plane node(s) {hosts} that would stay are not reachable/healthy; scale-in refused.",
    "E-K8S-021": "Control-plane node {host} is expected to be initialised (state says so) but {why}. Refusing to run kubespray: it would create a second cluster.",
    "E-K8S-022": "Node(s) {hosts} belong to another cluster (cluster-id {ids} != {ours}). Re-image them or remove them from this instance.",
    "E-K8S-024": "Control-plane nodes run Kubernetes but no extension state was found. The state was lost or these nodes belong to another cluster; refusing to touch them.",
    "E-K8S-030": "Scale-in would leave no Ready, schedulable worker.",
    "E-K8S-032": "The cluster has not finished its first deployment; control-plane count cannot change until it does. Revert control_plane_count and retry.",
    "E-K8S-035": "A control-plane scale-in is in progress ({removed} already removed). Finish it (retry the same edit); it cannot be reverted.",
    "E-K8S-041": "Node name(s) {hosts} changed since create (matched by server instance id). Renaming nodes is not supported.",
}


def _msg(code, **kw):
    text = MESSAGES[code]
    try:
        text = text.format(**kw)
    except (KeyError, IndexError):
        pass
    return "%s: %s" % (code, text)


def k8s_version_tuple(version):
    parts = str(version).strip().lstrip("v").split(".")
    out = []
    for p in parts[:3]:
        m = re.match(r"^(\d+)", p)
        out.append(int(m.group(1)) if m else 0)
    while len(out) < 3:
        out.append(0)
    return tuple(out)


def k8s_rfc1123(name):
    name = str(name or "").strip().rstrip(".")
    return bool(name) and len(name) <= 253 and bool(_RFC1123.match(name))


def _first(d, keys, default=None):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return default


def k8s_ranges(raw):
    """Normalise record-set ipRanges entries of any known shape into start/end/count dicts."""
    out, seen = [], set()
    for r in raw or []:
        if not isinstance(r, dict):
            continue
        start = _first(r, ("startIp", "start", "rangeStartHuman", "ipStart", "firstIp"))
        end = _first(r, ("endIp", "end", "rangeEndHuman", "ipEnd", "lastIp"))
        if start and not end and r.get("ipCount"):
            try:
                end = str(ipaddress.ip_address(start) + int(r["ipCount"]) - 1)
            except ValueError:
                end = None
        if not start or not end:
            continue
        try:
            count = int(ipaddress.ip_address(end)) - int(ipaddress.ip_address(start)) + 1
        except ValueError:
            continue
        if (start, end) in seen:
            continue
        seen.add((start, end))
        out.append({"start": str(start), "end": str(end), "count": count})
    return sorted(out, key=lambda x: int(ipaddress.ip_address(x["start"])))


def k8s_cidr_overlaps(cidrs):
    nets = []
    for c in cidrs or []:
        if not c:
            continue
        try:
            nets.append((c, ipaddress.ip_network(str(c), strict=False)))
        except ValueError:
            continue
    out = []
    for i, (a, na) in enumerate(nets):
        for b, nb in nets[i + 1:]:
            if na.overlaps(nb):
                out.append("%s overlaps %s" % (a, b))
    return out


def k8s_net_errors(net):
    """Validate the address plan; `net` = {pod_cidr, service_cidr, vip, lb_ranges[{start,end}], dns[]}.

    Returns a list of human-readable problems (empty = ok). Never rewrites a value.
    """
    errs = []
    nets = {}
    for key, label, lo, hi in (("pod_cidr", "pod_network_cidr", 12, 20), ("service_cidr", "service_network_cidr", 12, 24)):
        val = str(net.get(key) or "")
        try:
            n = ipaddress.ip_network(val, strict=True)
            if n.version != 4 or not lo <= n.prefixlen <= hi:
                errs.append("%s %s must be an IPv4 network /%d../%d" % (label, val, lo, hi))
            nets[label] = n
        except ValueError as exc:
            errs.append("%s %r is not a valid network (%s)" % (label, val, exc))
    if len(nets) == 2 and nets["pod_network_cidr"].overlaps(nets["service_network_cidr"]):
        errs.append("pod_network_cidr overlaps service_network_cidr")
    addrs = []
    if net.get("vip"):
        addrs.append(("API VIP", net["vip"]))
    for r in net.get("lb_ranges") or []:
        addrs += [("LoadBalancer pool", r.get("start")), ("LoadBalancer pool", r.get("end"))]
    for what, a in addrs:
        try:
            ip = ipaddress.ip_address(str(a))
        except ValueError:
            errs.append("%s address %r is not valid" % (what, a))
            continue
        for label, n in nets.items():
            if ip in n:
                errs.append("%s %s lies inside %s %s" % (what, ip, label, n))
    dns = list(net.get("dns") or [])
    if len(dns) > 3:
        errs.append("site_dns_servers: at most 3 servers")
    for d in dns:
        try:
            if ipaddress.ip_address(str(d)).version != 4:
                raise ValueError
        except ValueError:
            errs.append("site_dns_servers: %r is not an IPv4 address" % d)
    return errs


def k8s_overrides_check(value, bootstrapped=False):
    """Parse + police site_kubespray_overrides. `value` is already decoded to a dict/str by Jinja."""
    res = {"vars": {}, "denied": [], "frozen_ignored": [], "errors": []}
    if value in (None, "", {}):
        return res
    if not isinstance(value, dict):
        res["errors"].append("site_kubespray_overrides must be a YAML/JSON mapping of kubespray variables")
        return res
    blob = json.dumps(value, sort_keys=True)
    if len(blob) > OVERRIDES_MAX_BYTES:
        res["errors"].append("site_kubespray_overrides is larger than 64 KiB")
    if "{{" in blob or "{%" in blob:
        res["errors"].append("site_kubespray_overrides must not contain Jinja templating ({{ or {%)")
    for key in sorted(value):
        if not _KEY_RE.match(str(key)):
            res["errors"].append("site_kubespray_overrides: invalid variable name %r" % key)
            continue
        if key in TIER_A_KEYS or key.startswith(TIER_A_PREFIXES):
            res["denied"].append(key)
            continue
        if key in TIER_B_KEYS and bootstrapped:
            res["frozen_ignored"].append(key)
            continue
        res["vars"][key] = value[key]
    if res["denied"]:
        res["errors"].append(
            "site_kubespray_overrides sets extension-managed variable(s) %s; use the extension inputs/site "
            "settings instead" % ", ".join(res["denied"]))
    return res


def k8s_members(hosts, server_ids):
    """{host: {"server_instance_id": id}} for the state's control_plane.members (rename guard)."""
    return {h: {"server_instance_id": (server_ids or {}).get(h)} for h in hosts or []}


def _sorted_hosts(hosts, server_ids):
    def key(h):
        sid = server_ids.get(h)
        nat = [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", h)]
        return (0, int(sid), nat) if isinstance(sid, int) or str(sid).isdigit() else (1, 0, nat)
    return sorted(hosts, key=key)


def k8s_plan(state, desired, view, stage):
    """Decide what this run does.

    state   : recorded cluster state ({} when none). Keys used: phase, kube_version, create_only,
              addons, converge_generation, admin_generation, control_plane.order, cluster_id,
              members{host:{server_instance_id}}, workers, operation
    desired : current inputs (cp_count, worker_count, kube_version, create_only{}, addons{},
              converge_generation, admin_generation, offered_versions[], site_config_sha)
    view    : inventory + reachability + API facts (cp_hosts, worker_hosts, cp_scale_in, cp_scale_out,
              worker_scale_in, worker_scale_out, up_hosts, server_ids{}, node_cluster_ids{},
              cp_initialised{} (host->bool), api_workers[] (or None), ready_schedulable_workers[])
    stage   : "pre" (onEdit preDeploy) or "post" (onCreate/onEdit postDeploy)
    """
    state = state or {}
    desired = desired or {}
    view = view or {}
    errors, warnings = [], []
    up = set(view.get("up_hosts") or [])
    sids = view.get("server_ids") or {}
    cp_hosts = list(view.get("cp_hosts") or [])
    w_hosts = list(view.get("worker_hosts") or [])
    cp_in = list(view.get("cp_scale_in") or [])
    w_in = list(view.get("worker_scale_in") or [])
    scale_out = set((view.get("cp_scale_out") or []) + (view.get("worker_scale_out") or []))
    plan = {
        "stage": stage, "mode": "", "action": "noop", "errors": errors, "warnings": warnings,
        "cp_order": [], "cp_joining": [], "cp_leaving": [], "cp_vanished": [], "cp_order_after": [],
        "w_joining": [], "w_leaving": [], "w_vanished": [], "w_excluded": [],
        "converge_reasons": [], "upgrade": None, "kube_version": desired.get("kube_version"),
    }
    ours = state.get("cluster_id")
    foreign = sorted(h for h, cid in (view.get("node_cluster_ids") or {}).items()
                     if cid and ours and cid != ours)
    if foreign:
        errors.append(_msg("E-K8S-022", hosts=", ".join(foreign),
                           ids=", ".join(sorted({view["node_cluster_ids"][h] for h in foreign})), ours=ours))

    phase = state.get("phase")
    initialised = view.get("cp_initialised") or {}

    # ---------------------------------------------------------------- no state: create
    if not phase:
        if any(initialised.get(h) for h in cp_hosts + cp_in):
            errors.append(_msg("E-K8S-024"))
            plan["mode"] = "foreign"
            return plan
        plan["mode"] = "create"
        order = _sorted_hosts(cp_hosts, sids)
        plan["cp_order"] = plan["cp_order_after"] = order
        if stage == "post":
            plan["action"] = "create"
            down_cp = [h for h in order if h not in up]
            if down_cp:
                errors.append(_msg("E-K8S-017", hosts=", ".join(down_cp)))
            if len(order) % 2 == 0:
                errors.append(_msg("E-K8S-004", cp_to=len(order)))
            w_up = [h for h in w_hosts if h in up]
            w_down = [h for h in w_hosts if h not in up]
            if w_down and w_up:
                warnings.append("Worker(s) %s unreachable at create; excluded, they join on a later edit." % ", ".join(w_down))
                plan["w_excluded"] = w_down
            elif w_down:
                errors.append(_msg("E-K8S-017", hosts=", ".join(w_down)))
            plan["w_joining"] = w_up
            plan["kube_version"] = desired.get("kube_version")
        return plan

    order = list((state.get("control_plane") or {}).get("order") or [])
    plan["cp_order"] = order
    rec_ver = state.get("kube_version") or desired.get("kube_version")
    plan["kube_version"] = rec_ver

    # rename guard: a recorded member whose server instance id now sits under another hostname
    members = (state.get("control_plane") or {}).get("members") or {}
    by_sid = {str(v.get("server_instance_id")): h for h, v in members.items() if v.get("server_instance_id")}
    renamed = sorted("%s->%s" % (by_sid[str(sid)], h) for h, sid in sids.items()
                     if str(sid) in by_sid and by_sid[str(sid)] != h)
    if renamed:
        errors.append(_msg("E-K8S-041", hosts=", ".join(renamed)))
        return plan

    # ---------------------------------------------------------------- deltas
    cp_leaving = [h for h in order if h in cp_in]
    cp_vanished = [h for h in order if h not in cp_hosts and h not in cp_in]
    cp_joining = _sorted_hosts([h for h in cp_hosts if h not in order], sids)
    api_workers = view.get("api_workers")
    registered = list(api_workers) if api_workers is not None else list(state.get("workers") or [])
    pending = list((state.get("pending") or {}).get("workers") or [])
    w_joining = [h for h in w_hosts if h not in registered or h in pending]
    w_leaving = list(w_in)
    w_vanished = [h for h in registered if h not in w_hosts and h not in w_in]
    plan.update(cp_joining=cp_joining, cp_leaving=cp_leaving, cp_vanished=cp_vanished,
                w_joining=w_joining, w_leaving=w_leaving, w_vanished=w_vanished)

    if phase == "bootstrapping":
        plan["mode"] = "resume"
        if cp_joining or cp_leaving or cp_vanished:
            errors.append(_msg("E-K8S-032"))
        plan["cp_order"] = plan["cp_order_after"] = order or _sorted_hosts(cp_hosts, sids)
        if stage == "post":
            plan["action"] = "resume-create"
            plan["kube_version"] = state.get("kube_version_target") or desired.get("kube_version")
            plan["w_joining"] = [h for h in w_hosts if h in up]
            plan["w_excluded"] = [h for h in w_hosts if h not in up]
        else:
            plan["action"] = "noop"
        return plan

    plan["mode"] = "edit"

    # create-only drift
    rec_co = state.get("create_only") or {}
    drift = [k for k in CREATE_ONLY if k in rec_co and str(rec_co[k]) != str((desired.get("create_only") or {}).get(k))]
    if drift:
        errors.append(_msg("E-K8S-001", keys=", ".join(drift)))

    # one-way inputs
    rec_add = state.get("addons") or {}
    want_add = desired.get("addons") or {}
    turned_off = [a for a in ADDONS if rec_add.get(a) and not want_add.get(a)]
    if turned_off:
        errors.append(_msg("E-K8S-013", addons=", ".join(turned_off)))
    for label, rec_key in (("converge_generation", "converge_generation"),
                           ("admin_credential_generation", "admin_generation_input")):
        old, new = state.get(rec_key), desired.get(rec_key if label == "converge_generation" else "admin_generation")
        if old is not None and new is not None and int(new) < int(old):
            errors.append(_msg("E-K8S-014", label=label, old=old, new=new))

    # converge reasons (combinable)
    reasons = []
    if int(desired.get("converge_generation") or 0) > int(state.get("converge_generation") or 0):
        reasons.append("converge_generation")
    newly_on = [a for a in ADDONS if want_add.get(a) and not rec_add.get(a)]
    if newly_on:
        reasons.append("addons:" + ",".join(newly_on))
    plan["converge_reasons"] = reasons
    if desired.get("site_config_sha") and state.get("site_config_sha") and \
            desired["site_config_sha"] != state["site_config_sha"] and "converge_generation" not in reasons:
        warnings.append("Site settings changed since the last converge; existing nodes keep the recorded "
                        "settings until converge_generation is raised.")

    # version delta
    to = desired.get("kube_version")
    upgrading = bool(to) and str(to) != str(rec_ver)
    if upgrading:
        offered = list(desired.get("offered_versions") or [])
        tf, tt = k8s_version_tuple(rec_ver), k8s_version_tuple(to)
        if offered and to not in offered:
            errors.append(_msg("E-K8S-009", to=to, offered=", ".join(offered)))
        elif tt < tf:
            errors.append(_msg("E-K8S-007", to=to, frm=rec_ver))
        elif tt[1] > tf[1] + 1 or tt[0] != tf[0]:
            nxt = [v for v in offered if k8s_version_tuple(v)[:2] == (tf[0], tf[1] + 1)]
            errors.append(_msg("E-K8S-008", frm=rec_ver, to=to, next=(nxt[0] if nxt else "n/a")))
        plan["upgrade"] = {"from": rec_ver, "to": to}

    # CP deltas
    if cp_joining and (cp_leaving or cp_vanished):
        errors.append(_msg("E-K8S-005", joining=", ".join(cp_joining), leaving=", ".join(cp_leaving + cp_vanished)))
    cp_from = len(order)
    cp_to = len([h for h in order if h not in cp_leaving and h not in cp_vanished]) + len(cp_joining)
    cp_change = cp_joining or cp_leaving or cp_vanished
    if cp_change and not cp_vanished:
        if cp_to % 2 == 0:
            errors.append(_msg("E-K8S-004", cp_to=cp_to))
        elif abs(cp_to - cp_from) != 2:
            errors.append(_msg("E-K8S-003", cp_from=cp_from, cp_to=cp_to))
    survivors = [h for h in order if h not in cp_leaving and h not in cp_vanished]
    plan["cp_order_after"] = survivors + cp_joining

    # journal: a CP scale-in that already removed members cannot be reverted
    op = state.get("operation") or {}
    if op.get("kind") == "cp-scale-in" and op.get("removed") and not cp_leaving:
        errors.append(_msg("E-K8S-035", removed=", ".join(op["removed"])))

    # exclusivity
    structural = {
        "control-plane scale-out": bool(cp_joining),
        "control-plane scale-in": bool(cp_leaving or cp_vanished),
        "kube_version upgrade": upgrading,
        "worker scale-out": bool(w_joining),
        "worker scale-in": bool(w_leaving),
        "converge": bool(reasons),
    }
    # CP scale-out may bring worker scale-out along: one cluster.yml run joins both
    combinable = {"control-plane scale-out": {"worker scale-out"}}
    for what in ("control-plane scale-out", "control-plane scale-in", "kube_version upgrade"):
        if structural[what]:
            others = [k for k, v in structural.items() if v and k != what and k not in combinable.get(what, ())]
            if others:
                errors.append(_msg("E-K8S-006", what=what.capitalize(), others=", ".join(others)))

    # reachability
    if order and order[0] not in cp_leaving and order[0] not in cp_vanished and order[0] not in up:
        if cp_change or upgrading or reasons or w_joining or w_leaving:
            errors.append(_msg("E-K8S-016", host=order[0]))
    surv_down = [h for h in survivors if h not in up]
    if (cp_leaving or cp_vanished) and surv_down:
        errors.append(_msg("E-K8S-020", hosts=", ".join(surv_down)))
    new_nodes = cp_joining + [h for h in w_joining if h not in registered]
    if stage == "post":
        down_new = [h for h in new_nodes if h not in up]
        if down_new:
            errors.append(_msg("E-K8S-017", hosts=", ".join(down_new)))
    w_down = [h for h in w_hosts if h in registered and h not in up]
    if w_down:
        warnings.append("Existing worker(s) %s unreachable; skipped this run." % ", ".join(w_down))
        plan["w_excluded"] = w_down
    if stage == "pre" and w_leaving:
        ready = [h for h in (view.get("ready_schedulable_workers") or []) if h not in w_leaving]
        if view.get("ready_schedulable_workers") is not None and not ready:
            errors.append(_msg("E-K8S-030"))

    # action
    if stage == "pre":
        if cp_leaving or cp_vanished:
            plan["action"] = "cp-scale-in"
        elif w_leaving:
            plan["action"] = "worker-scale-in"
    else:
        if cp_joining:
            plan["action"] = "cp-scale-out"
        elif upgrading:
            plan["action"] = "upgrade"
            plan["kube_version"] = to
        elif reasons:
            plan["action"] = "converge"
        elif [h for h in w_joining if h in up]:
            plan["action"] = "worker-scale-out"
        if plan["action"] in ("converge", "worker-scale-out", "cp-scale-out"):
            plan["w_joining"] = [h for h in w_joining if h in up]
    return plan


class FilterModule:
    def filters(self):
        return {
            "k8s_plan": k8s_plan,
            "k8s_ranges": k8s_ranges,
            "k8s_rfc1123": k8s_rfc1123,
            "k8s_version_tuple": k8s_version_tuple,
            "k8s_overrides_check": k8s_overrides_check,
            "k8s_cidr_overlaps": k8s_cidr_overlaps,
            "k8s_members": k8s_members,
            "k8s_net_errors": k8s_net_errors,
        }
