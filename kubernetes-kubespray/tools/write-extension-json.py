"""One-shot writer for extension.json (kept for reference; extension.json is the source of truth).

Run: python3 -I tools/write-extension-json.py  (from kubernetes-kubespray/)
"""
import json

VERSION = "1.0.0"
EE = "ee-kubernetes-kubespray-ks2-32-0-b1"
BUNDLE = "kubernetes-kubespray-ansible-bundle"
NET = {"label": "k8s-net", "networkConnection": {"tagged": False, "accessMode": "l2",
       "providesDefaultRoute": True, "dns": {"provisionInstanceDnsRecords": True}}}


def i(label, itype, help_text, default=None, options=None, set_only=False):
    d = {"label": label, "name": label, "helpText": help_text, "inputType": itype}
    if set_only:
        d["setOnly"] = True
    if default is not None:
        d["defaultValue"] = default
    d["options"] = options or {}
    return d


def o(label, help_text, otype="string", secret=False):
    d = {"label": label, "name": label, "helpText": help_text, "outputType": otype}
    if secret:
        d["isPassword"] = True
    return d


def t(label, playbook, timeout):
    return {"label": label, "taskType": "ExtensionTaskAnsible",
            "options": {"asset": BUNDLE, "playbook": playbook, "ee": EE,
                        "executionTimeout": timeout, "executionTimeoutTick": 30}}


d = {
    "kind": "ExtensionDefinition",
    "schemaVersion": "1.1",
    "name": "Kubernetes (kubespray)",
    "label": "kubernetes_kubespray",
    "extensionType": "application",
    "vendor": "MetalSoft",
    "extensionVersion": VERSION,
    "description": "Vanilla upstream Kubernetes on Ubuntu 26.04 bare metal via kubespray v2.32.0: 1/3/5 control-plane nodes with stacked etcd, scalable workers, kube-vip API VIP, MetalLB L2, local-path storage.",
    "icon": "https://raw.githubusercontent.com/cncf/artwork/main/projects/kubernetes/icon/color/kubernetes-icon-color.svg",
    "dependencies": {"controllerVersion": "v7.5.0", "osTemplates": ["ubuntu-26-04-lts-waitforssh"]},
    "inputs": [
        i("control_plane_server_type", "ExtensionInputServerType",
          "Control-plane nodes (API server, etcd). Production: 4+ cores, 16+ GB RAM, SSD. Fixed after create.",
          options={"minRamGb": 8}, set_only=True),
        i("worker_server_type", "ExtensionInputServerType",
          "Server type of every worker node (runs the workloads). Fixed after create.", set_only=True),
        i("os_template", "ExtensionInputOsTemplate",
          "Ubuntu 26.04 LTS wait-for-SSH template (ubuntu-26-04-lts-waitforssh). Fixed after create.",
          options={"osFamily": "Ubuntu"}, set_only=True),
        i("control_plane_count", "ExtensionInputInteger",
          "Control-plane nodes with stacked etcd: 1, 3 or 5. Change by 2 per edit, with no other change in that edit.",
          1, {"minValue": 1, "maxValue": 5, "deniedValues": [2, 4]}),
        i("worker_count", "ExtensionInputInteger",
          "Worker nodes (1-100). Edit to scale out/in; removed nodes are drained first (MetalSoft picks which leave).",
          1, {"minValue": 1, "maxValue": 100}),
        i("kube_version", "ExtensionInputEnum",
          "Kubernetes version. Edit to upgrade: one minor at a time, never down, no other change in the same edit.",
          "1.36.4", {"values": ["1.36.4", "1.35.8"]}),
        i("kube_proxy_mode", "ExtensionInputEnum",
          "kube-proxy mode: iptables (default, tested on Ubuntu 26.04) or nftables (experimental). Fixed after create.",
          "iptables", {"values": ["iptables", "nftables"]}, set_only=True),
        i("pod_network_cidr", "ExtensionInputString",
          "Pod network (Calico), /12 to /20. Must not overlap node, service or client networks. Fixed after create.",
          "10.233.64.0/18", {"validationRegEx": "^([0-9]{1,3}\\.){3}[0-9]{1,3}/(1[2-9]|20)$"}, set_only=True),
        i("service_network_cidr", "ExtensionInputString",
          "Service (ClusterIP) network, /12 to /24. Must not overlap the pod or node networks. Fixed after create.",
          "10.233.0.0/18", {"validationRegEx": "^([0-9]{1,3}\\.){3}[0-9]{1,3}/(1[2-9]|2[0-4])$"}, set_only=True),
        i("cluster_dns_domain", "ExtensionInputString",
          "In-cluster DNS domain (<svc>.<ns>.svc.<domain>), not the site DNS zone. Keep cluster.local. Fixed after create.",
          "cluster.local", {"validationRegEx": "^([a-z0-9]([a-z0-9-]{0,30}[a-z0-9])?\\.){0,3}[a-z]{2,30}$"}, set_only=True),
        i("metrics_server_enabled", "ExtensionInputBoolean",
          "Install metrics-server (kubectl top, autoscaling). Add-only: switching it off later is refused.", True),
        i("local_path_provisioner_enabled", "ExtensionInputBoolean",
          "Install local-path-provisioner as the default StorageClass (node-local disk, no replication). Add-only.", True),
        i("gateway_api_crds_enabled", "ExtensionInputBoolean",
          "Install the Gateway API CRDs (standard channel, no controller). Add-only.", False),
        i("metallb_enabled", "ExtensionInputBoolean",
          "Install MetalLB (L2) for LoadBalancer Services from the 4 reserved IPs (output lb_pool_ranges). Add-only.", True),
        i("drain_timeout_minutes", "ExtensionInputInteger",
          "Per-node drain timeout for scale-in and upgrades (1-30 min).", 10, {"minValue": 1, "maxValue": 30}),
        i("drain_policy", "ExtensionInputEnum",
          "When a drain times out: respect-pdb fails the edit (nothing removed); force-after-timeout evicts anyway.",
          "respect-pdb", {"values": ["respect-pdb", "force-after-timeout"]}),
        i("converge_generation", "ExtensionInputInteger",
          "Raise it (e.g. +1) to re-run the full kubespray converge: repair drift, apply new site settings. Never lower.",
          0, {"minValue": 0, "maxValue": 1000000}),
        i("admin_credential_generation", "ExtensionInputInteger",
          "Raise it to rotate the admin kubeconfig (old one stops working). Never lower it.",
          1, {"minValue": 1, "maxValue": 1000}),
    ],
    "outputs": [
        o("api_url", "Kubernetes API URL (https://<api name or VIP>:6443).", "url"),
        o("api_vip", "API virtual IP (kube-vip, ARP) on the cluster network."),
        o("api_fqdn", "API DNS name; empty when the site has no DNS provisioning for it."),
        o("ca_cert", "Cluster CA certificate (PEM).", "text"),
        o("admin_kubeconfig", "kubeconfig of the extension's admin identity (cluster-admin via its own binding; revocable).",
          "secret", secret=True),
        o("admin_kubeconfig_expires", "Expiry (UTC) of the admin kubeconfig certificate; edits renew it when < 30 days remain."),
        o("admin_credential", "Admin identity name and group (revoke: delete its ClusterRoleBinding)."),
        o("kubernetes_version", "Kubernetes version running on the control plane."),
        o("kubespray_version", "kubespray release used by this extension version."),
        o("control_plane_nodes", "Control-plane (and etcd) node names, comma-separated."),
        o("worker_nodes", "Worker node names, comma-separated."),
        o("lb_pool_ranges", "IP range(s) reserved for LoadBalancer Services (MetalLB), first-last."),
        o("cluster_id", "Cluster id recorded at create."),
        o("cluster_status", "ready, or degraded: <problems> from the last run's health check."),
        o("etcd_last_snapshot", "Last etcd snapshot taken by the extension (node:path, time)."),
    ],
    "infrastructure": {
        "instanceArrays": [
            {"label": "k8scp", "instanceCount": "#/input/control_plane_count",
             "serverType": "#/input/control_plane_server_type", "osTemplate": "#/input/os_template",
             "logicalNetworks": [NET], "tags": ["k8s-control-plane"]},
            {"label": "k8sworker", "instanceCount": "#/input/worker_count",
             "serverType": "#/input/worker_server_type", "osTemplate": "#/input/os_template",
             "logicalNetworks": [NET], "tags": ["k8s-worker"]},
        ],
        "logicalNetworks": [
            {"label": "k8s-net", "profileLabel": "k8s-net",
             "ipAllocations": [{"tags": {"role": "api-vip"}, "ipVersion": "ipv4",
                                "dnsRecords": [{"name": "api.{{CLUSTER_NAME}}.{{default_zone_name}}",
                                                "recordType": "A", "generatePtrRecord": True, "ttl": 3600}]}],
             "ipRanges": [{"tags": {"role": "lb-pool"}, "ipVersion": "ipv4", "ipCount": 4}]},
        ],
    },
    "assets": [
        {"label": BUNDLE, "name": BUNDLE, "assetType": "AnsibleBundle",
         "url": f"https://repo.metalsoft.io/.extensions_ms/kubernetes-kubespray/kubernetes-kubespray-v{VERSION}.zip"},
        {"label": EE, "name": EE, "assetType": "OciImage",
         "url": "https://repo.metalsoft.io/.extensions_ms/ee/ee-kubernetes-kubespray-ks2.32.0-b1.tar.gz",
         "repositoryRegistry": "ee-kubernetes-kubespray", "namespaceRegistry": "ee", "tagRegistry": "ks2.32.0-b1"},
    ],
    "onCreate": [{"stage": "preDeploy", "tasks": []},
                 {"stage": "postDeploy", "tasks": [t("k8s-deploy", "deploy.yaml", 18000)]}],
    "onEdit": [{"stage": "preDeploy", "tasks": [t("k8s-edit-pre", "edit-pre.yaml", 14400)]},
               {"stage": "postDeploy", "tasks": [t("k8s-edit-post", "deploy.yaml", 46800)]}],
    "onDelete": [],
    "configVars": [
        i("site_kubespray_overrides", "ExtensionInputString",
          "Site-admin kubespray group_vars (YAML/JSON or base64); protected keys rejected. Applied on create/converge.", ""),
        i("site_dns_servers", "ExtensionInputString",
          "Up to 3 comma-separated upstream DNS servers for cluster DNS. Empty: use the nodes' own resolvers.", "",
          {"validationRegEx": "^$|^[0-9.]{7,15}(, ?[0-9.]{7,15}){0,2}$"}),
        i("site_ntp_servers", "ExtensionInputString",
          "Comma-separated NTP servers for the nodes (chrony). Empty: site NTP servers, else Ubuntu pool.", "",
          {"validationRegEx": "^$|^[A-Za-z0-9.:-]{1,63}(, ?[A-Za-z0-9.:-]{1,63}){0,3}$"}),
        i("site_admin_cert_validity_days", "ExtensionInputInteger",
          "Validity in days (60-365) of the admin kubeconfig certificate issued by the extension.", 365,
          {"minValue": 60, "maxValue": 365}),
        i("site_auto_renew_certificates", "ExtensionInputBoolean",
          "Renew control-plane certificates monthly on the nodes (kubespray auto_renew_certificates).", True),
        i("site_backup_retention_count", "ExtensionInputInteger",
          "etcd and kubeadm backups kept on each control-plane node (1-100).", 5, {"minValue": 1, "maxValue": 100}),
        i("site_ansible_forks", "ExtensionInputInteger",
          "Parallel SSH connections used by kubespray runs (5-200).", 50, {"minValue": 5, "maxValue": 200}),
    ],
}

with open("extension.json", "w", encoding="utf-8") as fh:
    json.dump(d, fh, indent=2)
    fh.write("\n")
print("wrote extension.json")
