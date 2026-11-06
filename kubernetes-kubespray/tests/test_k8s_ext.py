"""Planner + helper tests (stdlib unittest). Run from kubernetes-kubespray/:

    python3 -I -m unittest discover -s tests -p 'test_*.py' -v
"""
import importlib.util
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "k8s_ext", os.path.join(_HERE, "..", "ansible", "filter_plugins", "k8s_ext.py"))
k8s_ext = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(k8s_ext)
plan = k8s_ext.k8s_plan

CP = ["cp1", "cp2", "cp3", "cp4", "cp5"]
W = ["w1", "w2", "w3"]
SIDS = {h: i for i, h in enumerate(CP + W + ["w4", "w5"], start=100)}
CO = {"kube_proxy_mode": "iptables", "pod_network_cidr": "10.233.64.0/18",
      "service_network_cidr": "10.233.0.0/18", "cluster_dns_domain": "cluster.local"}
ADD = {"metrics_server": True, "local_path_provisioner": True, "gateway_api_crds": False, "metallb": True}


def desired(**kw):
    d = {"cp_count": 1, "worker_count": 1, "kube_version": "1.36.4", "create_only": dict(CO),
         "addons": dict(ADD), "converge_generation": 0, "admin_generation": 1,
         "offered_versions": ["1.36.4", "1.35.8"]}
    d.update(kw)
    return d


def state(order=("cp1",), workers=("w1",), **kw):
    s = {"phase": "ready", "cluster_id": "k8s-abc", "kube_version": "1.36.4", "create_only": dict(CO),
         "addons": dict(ADD), "converge_generation": 0, "admin_generation_input": 1,
         "control_plane": {"order": list(order),
                           "members": {h: {"server_instance_id": SIDS[h]} for h in order}},
         "workers": list(workers)}
    s.update(kw)
    return s


def view(cp=("cp1",), w=("w1",), cp_in=(), w_in=(), cp_out=(), w_out=(), down=(), api_workers=None, **kw):
    all_hosts = list(cp) + list(w) + list(cp_in) + list(w_in)
    v = {"cp_hosts": list(cp), "worker_hosts": list(w), "cp_scale_in": list(cp_in),
         "worker_scale_in": list(w_in), "cp_scale_out": list(cp_out), "worker_scale_out": list(w_out),
         "up_hosts": [h for h in all_hosts if h not in down], "server_ids": {h: SIDS.get(h, 999) for h in all_hosts},
         "node_cluster_ids": {}, "cp_initialised": {}, "api_workers": api_workers}
    v.update(kw)
    return v


def codes(p):
    return sorted({e.split(":")[0] for e in p["errors"]})


class CreateTests(unittest.TestCase):
    def test_fresh_create(self):
        p = plan({}, desired(), view(cp=["cp2", "cp1", "cp3"], w=["w1", "w2"]), "post")
        self.assertEqual(p["action"], "create")
        self.assertEqual(p["cp_order"], ["cp1", "cp2", "cp3"])  # serverInstanceId order, not inventory order
        self.assertEqual(p["w_joining"], ["w1", "w2"])
        self.assertEqual(p["errors"], [])

    def test_create_unreachable_worker_excluded_when_one_left(self):
        p = plan({}, desired(), view(w=["w1", "w2"], down=["w2"]), "post")
        self.assertEqual(p["w_excluded"], ["w2"])
        self.assertEqual(p["errors"], [])

    def test_create_unreachable_cp_fails(self):
        p = plan({}, desired(), view(down=["cp1"]), "post")
        self.assertIn("E-K8S-017", codes(p))

    def test_state_lost(self):
        p = plan({}, desired(), view(cp_initialised={"cp1": True}), "post")
        self.assertEqual(codes(p), ["E-K8S-024"])

    def test_pre_without_state_is_noop(self):
        p = plan({}, desired(), view(), "pre")
        self.assertEqual(p["action"], "noop")

    def test_resume_create(self):
        p = plan({"phase": "bootstrapping", "cluster_id": "k8s-abc", "control_plane": {"order": ["cp1"]},
                  "kube_version_target": "1.36.4"}, desired(), view(), "post")
        self.assertEqual(p["action"], "resume-create")

    def test_resume_create_cp_change_refused(self):
        p = plan({"phase": "bootstrapping", "control_plane": {"order": ["cp1"]}}, desired(),
                 view(cp=["cp1", "cp2", "cp3"]), "pre")
        self.assertIn("E-K8S-032", codes(p))


class EditTests(unittest.TestCase):
    def test_noop(self):
        p = plan(state(), desired(), view(api_workers=["w1"]), "post")
        self.assertEqual((p["action"], p["errors"]), ("noop", []))

    def test_worker_scale_out(self):
        p = plan(state(), desired(), view(w=["w1", "w2"], w_out=["w2"], api_workers=["w1"]), "post")
        self.assertEqual(p["action"], "worker-scale-out")
        self.assertEqual(p["w_joining"], ["w2"])

    def test_worker_scale_in(self):
        p = plan(state(workers=("w1", "w2")), desired(),
                 view(w=["w1"], w_in=["w2"], api_workers=["w1", "w2"], ready_schedulable_workers=["w1", "w2"]), "pre")
        self.assertEqual(p["action"], "worker-scale-in")
        self.assertEqual(p["w_leaving"], ["w2"])

    def test_worker_scale_in_last_ready_refused(self):
        p = plan(state(workers=("w1", "w2")), desired(),
                 view(w=["w1"], w_in=["w2"], api_workers=["w1", "w2"], ready_schedulable_workers=["w2"]), "pre")
        self.assertIn("E-K8S-030", codes(p))

    def test_converge_with_scale_out(self):
        p = plan(state(), desired(converge_generation=1), view(w=["w1", "w2"], api_workers=["w1"]), "post")
        self.assertEqual(p["action"], "converge")
        self.assertEqual(p["w_joining"], ["w2"])

    def test_addon_on_is_converge(self):
        add = dict(ADD, gateway_api_crds=True)
        p = plan(state(), desired(addons=add), view(api_workers=["w1"]), "post")
        self.assertEqual(p["action"], "converge")

    def test_addon_off_refused(self):
        add = dict(ADD, metallb=False)
        self.assertIn("E-K8S-013", codes(plan(state(), desired(addons=add), view(api_workers=["w1"]), "pre")))

    def test_generation_decrease_refused(self):
        p = plan(state(converge_generation=3), desired(converge_generation=2), view(api_workers=["w1"]), "pre")
        self.assertIn("E-K8S-014", codes(p))

    def test_create_only_drift(self):
        co = dict(CO, pod_network_cidr="10.10.0.0/16")
        self.assertIn("E-K8S-001", codes(plan(state(), desired(create_only=co), view(api_workers=["w1"]), "pre")))

    def test_upgrade(self):
        p = plan(state(kube_version="1.35.8"), desired(kube_version="1.36.4"), view(api_workers=["w1"]), "post")
        self.assertEqual((p["action"], p["kube_version"]), ("upgrade", "1.36.4"))

    def test_downgrade_refused(self):
        p = plan(state(), desired(kube_version="1.35.8"), view(api_workers=["w1"]), "pre")
        self.assertIn("E-K8S-007", codes(p))

    def test_minor_skip_refused(self):
        p = plan(state(kube_version="1.34.11"), desired(kube_version="1.36.4"), view(api_workers=["w1"]), "pre")
        self.assertIn("E-K8S-008", codes(p))

    def test_upgrade_plus_scale_refused(self):
        p = plan(state(kube_version="1.35.8"), desired(kube_version="1.36.4"),
                 view(w=["w1", "w2"], api_workers=["w1"]), "pre")
        self.assertIn("E-K8S-006", codes(p))

    def test_cp_scale_out(self):
        p = plan(state(), desired(), view(cp=["cp1", "cp3", "cp2"], cp_out=["cp2", "cp3"], api_workers=["w1"]), "post")
        self.assertEqual(p["action"], "cp-scale-out")
        self.assertEqual(p["cp_order_after"], ["cp1", "cp2", "cp3"])

    def test_cp_1_to_5_refused(self):
        p = plan(state(), desired(), view(cp=CP, api_workers=["w1"]), "pre")
        self.assertIn("E-K8S-003", codes(p))

    def test_cp_scale_in_bootstrap_leaves(self):
        p = plan(state(order=("cp1", "cp2", "cp3")), desired(),
                 view(cp=["cp2"], cp_in=["cp1", "cp3"], api_workers=["w1"]), "pre")
        self.assertEqual(p["action"], "cp-scale-in")
        self.assertEqual(p["cp_order_after"], ["cp2"])
        self.assertEqual(p["errors"], [])

    def test_cp_scale_in_survivor_down(self):
        p = plan(state(order=("cp1", "cp2", "cp3")), desired(),
                 view(cp=["cp2"], cp_in=["cp1", "cp3"], down=["cp2"], api_workers=["w1"]), "pre")
        self.assertIn("E-K8S-020", codes(p))

    def test_cp_replace_refused(self):
        p = plan(state(order=("cp1", "cp2", "cp3")), desired(),
                 view(cp=["cp1", "cp2", "cp4"], cp_in=["cp3"], api_workers=["w1"]), "pre")
        self.assertIn("E-K8S-005", codes(p))

    def test_cp_plus_worker_scale_out(self):
        v = view(cp=["cp1", "cp2", "cp3"], w=["w1", "w2"], cp_out=["cp2", "cp3"], w_out=["w2"], api_workers=["w1"])
        self.assertEqual(plan(state(), desired(), v, "pre")["errors"], [])
        p = plan(state(), desired(), v, "post")
        self.assertEqual((p["action"], p["errors"]), ("cp-scale-out", []))
        self.assertEqual(p["cp_order_after"], ["cp1", "cp2", "cp3"])
        self.assertEqual(p["w_joining"], ["w2"])

    def test_cp_plus_worker_scale_out_retry_after_cp_commit(self):
        # the CP part committed its order, the worker part failed: the retry only adds the workers
        p = plan(state(order=("cp1", "cp2", "cp3"), pending={"workers": ["w2"]}), desired(),
                 view(cp=["cp1", "cp2", "cp3"], w=["w1", "w2"], api_workers=["w1"]), "post")
        self.assertEqual((p["action"], p["errors"]), ("worker-scale-out", []))
        self.assertEqual(p["w_joining"], ["w2"])

    def test_cp_scale_out_plus_new_worker_down_fails(self):
        p = plan(state(), desired(), view(cp=["cp1", "cp2", "cp3"], w=["w1", "w2"], down=["w2"], api_workers=["w1"]), "post")
        self.assertIn("E-K8S-017", codes(p))

    def test_cp_scale_out_plus_worker_scale_in_refused(self):
        p = plan(state(workers=("w1", "w2")), desired(),
                 view(cp=["cp1", "cp2", "cp3"], w=["w1"], w_in=["w2"], api_workers=["w1", "w2"]), "pre")
        self.assertIn("E-K8S-006", codes(p))

    def test_cp_scale_out_plus_converge_refused(self):
        p = plan(state(), desired(converge_generation=1), view(cp=["cp1", "cp2", "cp3"], api_workers=["w1"]), "pre")
        self.assertIn("E-K8S-006", codes(p))

    def test_first_cp_down(self):
        p = plan(state(), desired(converge_generation=1), view(down=["cp1"], api_workers=["w1"]), "post")
        self.assertIn("E-K8S-016", codes(p))

    def test_existing_worker_down_is_warning(self):
        p = plan(state(workers=("w1", "w2")), desired(), view(w=["w1", "w2"], down=["w2"], api_workers=["w1", "w2"]), "post")
        self.assertEqual(p["errors"], [])
        self.assertEqual(p["w_excluded"], ["w2"])

    def test_new_worker_down_fails(self):
        p = plan(state(), desired(), view(w=["w1", "w2"], down=["w2"], api_workers=["w1"]), "post")
        self.assertIn("E-K8S-017", codes(p))

    def test_foreign_node(self):
        p = plan(state(), desired(), view(api_workers=["w1"], node_cluster_ids={"w1": "k8s-other"}), "pre")
        self.assertIn("E-K8S-022", codes(p))

    def test_rename_guard(self):
        v = view(cp=["cp1.fqdn"], api_workers=["w1"])
        v["server_ids"] = {"cp1.fqdn": SIDS["cp1"], "w1": SIDS["w1"]}
        v["up_hosts"] = ["cp1.fqdn", "w1"]
        self.assertIn("E-K8S-041", codes(plan(state(), desired(), v, "pre")))

    def test_cp_scale_in_revert_after_partial(self):
        s = state(order=("cp1", "cp2", "cp3"), operation={"kind": "cp-scale-in", "removed": ["cp3"]})
        p = plan(s, desired(), view(cp=["cp1", "cp2", "cp3"], api_workers=["w1"]), "pre")
        self.assertIn("E-K8S-035", codes(p))


class HelperTests(unittest.TestCase):
    def test_ranges_shapes(self):
        r = k8s_ext.k8s_ranges([{"startIp": "10.0.0.20", "endIp": "10.0.0.23"},
                                {"start": "10.0.0.10", "ipCount": 2},
                                {"startIp": "10.0.0.20", "endIp": "10.0.0.23"}])
        self.assertEqual(r, [{"start": "10.0.0.10", "end": "10.0.0.11", "count": 2},
                             {"start": "10.0.0.20", "end": "10.0.0.23", "count": 4}])

    def test_rfc1123(self):
        self.assertTrue(k8s_ext.k8s_rfc1123("api.k8s1.site1.example.com."))
        self.assertFalse(k8s_ext.k8s_rfc1123("api.My_Cluster.zone"))

    def test_overrides(self):
        r = k8s_ext.k8s_overrides_check({"kubelet_max_pods": 200, "kube_vip_arp_enabled": False,
                                          "calico_vxlan_mode": "CrossSubnet"}, bootstrapped=True)
        self.assertEqual(r["vars"], {"kubelet_max_pods": 200})
        self.assertEqual(r["denied"], ["kube_vip_arp_enabled"])
        self.assertEqual(r["frozen_ignored"], ["calico_vxlan_mode"])
        self.assertTrue(r["errors"])
        self.assertIn("Jinja", " ".join(k8s_ext.k8s_overrides_check({"a": "{{ x }}"})["errors"]))

    def test_net_errors(self):
        ok = {"pod_cidr": "10.233.64.0/18", "service_cidr": "10.233.0.0/18", "vip": "10.20.30.6",
              "lb_ranges": [{"start": "10.20.30.7", "end": "10.20.30.11"}], "dns": ["8.8.8.8"]}
        self.assertEqual(k8s_ext.k8s_net_errors(ok), [])
        bad = dict(ok, pod_cidr="10.233.0.0/22", vip="10.233.0.10", dns=["1.1.1.1", "x"],
                   lb_ranges=[{"start": "10.233.1.1", "end": "10.233.1.4"}])
        text = " | ".join(k8s_ext.k8s_net_errors(bad))
        for frag in ("must be an IPv4 network /12../20", "overlaps service_network_cidr",
                     "API VIP 10.233.0.10 lies inside", "LoadBalancer pool 10.233.1.1 lies inside", "'x' is not an IPv4"):
            self.assertIn(frag, text)
        self.assertTrue(k8s_ext.k8s_net_errors(dict(ok, pod_cidr="10.233.64.1/18")))  # host bits set

    def test_overlaps(self):
        self.assertEqual(k8s_ext.k8s_cidr_overlaps(["10.233.64.0/18", "10.233.0.0/18", "10.233.100.0/24"]),
                         ["10.233.64.0/18 overlaps 10.233.100.0/24"])


if __name__ == "__main__":
    unittest.main()
