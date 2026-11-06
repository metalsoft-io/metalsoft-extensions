"""extension.json contract (stdlib unittest; mirrors slurm/tests/definition-spec.yaml).

    python3 -I -m unittest discover -s tests -p 'test_*.py' -v
"""
import json
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEF = json.load(open(os.path.join(ROOT, "extension.json"), encoding="utf-8"))
GLOBALS = open(os.path.join(ROOT, "ansible/roles/globals/defaults/main.yaml"), encoding="utf-8").read()


def _global(name):
    m = re.search(r'^%s:\s*"?([^"\n]+)"?' % re.escape(name), GLOBALS, re.M)
    return m.group(1).strip() if m else None


def _tasks():
    for ev in ("onCreate", "onEdit", "onDelete"):
        for stage in DEF.get(ev, []):
            for t in stage.get("tasks", []):
                yield ev, stage["stage"], t


class DefinitionTests(unittest.TestCase):
    def test_top_level(self):
        self.assertEqual(DEF["kind"], "ExtensionDefinition")
        self.assertRegex(DEF["label"], r"^[A-Za-z][A-Za-z0-9_]{0,62}$")
        self.assertFalse(DEF["label"].endswith("_"))
        self.assertIsInstance(DEF["assets"], list)

    def test_version_pins_match_bundle(self):
        self.assertEqual(DEF["extensionVersion"], _global("k8s_ext_version"))
        bundle = [a for a in DEF["assets"] if a["assetType"] == "AnsibleBundle"][0]
        self.assertTrue(bundle["url"].endswith("kubernetes-kubespray-v%s.zip" % DEF["extensionVersion"]))
        ee = [a for a in DEF["assets"] if a["assetType"] == "OciImage"][0]
        self.assertEqual(ee["tagRegistry"], _global("k8s_ee_tag"))
        self.assertIn(ee["tagRegistry"], ee["url"])
        for a in DEF["assets"]:
            self.assertLessEqual(len(a["url"]), 128, a["label"])

    def test_labels_one_namespace(self):
        labels = [x["label"] for k in ("inputs", "outputs", "configVars") for x in DEF[k]]
        self.assertEqual(len(labels), len(set(labels)))
        for x in DEF["inputs"] + DEF["outputs"] + DEF["configVars"]:
            self.assertEqual(x["label"], x["name"])
        # derived variables are k8s_-prefixed and must never collide with extra-vars
        for lab in labels:
            self.assertFalse(lab.startswith("k8s_"), lab)
            self.assertNotEqual(lab, "context")
        for cv in DEF["configVars"]:
            self.assertTrue(cv["label"].startswith("site_"), cv["label"])

    def test_inputs(self):
        for x in DEF["inputs"] + DEF["configVars"]:
            self.assertLessEqual(len(x["helpText"]), 128, x["label"])
            t = x["inputType"]
            if t in ("ExtensionInputServerType", "ExtensionInputOsTemplate"):
                self.assertNotIn("defaultValue", x)
            rx = x["options"].get("validationRegEx")
            if rx:
                self.assertLessEqual(len(rx), 64, x["label"])
                self.assertNotIn("(?", rx)
                self.assertRegex(str(x["defaultValue"]), rx, x["label"])
            if t == "ExtensionInputEnum":
                vals = x["options"]["values"]
                self.assertLessEqual(len(vals), 12)
                self.assertEqual(len(vals), len(set(vals)))
                self.assertIn(x["defaultValue"], vals)
            if t == "ExtensionInputInteger" and "defaultValue" in x:
                o = x["options"]
                self.assertGreaterEqual(x["defaultValue"], o.get("minValue", x["defaultValue"]))
                self.assertLessEqual(x["defaultValue"], o.get("maxValue", x["defaultValue"]))
                self.assertNotIn(x["defaultValue"], o.get("deniedValues", []))
            self.assertNotEqual(t, "ExtensionInputEnum") if x in DEF["configVars"] else None
        self.assertLessEqual(len(DEF["configVars"]), 100)
        for cv in DEF["configVars"]:
            self.assertIn("defaultValue", cv)

    def test_kube_versions_match_globals(self):
        enum = [x for x in DEF["inputs"] if x["label"] == "kube_version"][0]
        self.assertEqual(json.dumps(enum["options"]["values"]),
                         re.search(r"^k8s_offered_versions:\s*(\[.*\])", GLOBALS, re.M).group(1).replace("'", '"'))

    def test_infrastructure(self):
        arrays = DEF["infrastructure"]["instanceArrays"]
        self.assertEqual([a["label"] for a in arrays], ["k8scp", "k8sworker"])
        for a in arrays:
            self.assertRegex(a["label"], r"^[a-z][a-z0-9]{0,62}$")  # hyphen-free (controller escapes '-')
            for ref in (a["instanceCount"], a["serverType"], a["osTemplate"]):
                self.assertTrue(ref.startswith("#/input/"))
                self.assertIn(ref.split("/")[-1], [x["label"] for x in DEF["inputs"]])
        net = DEF["infrastructure"]["logicalNetworks"][0]
        self.assertIsInstance(net["ipRanges"][0]["ipCount"], int)  # the platform rejects #/input/ here
        self.assertEqual(net["ipRanges"][0]["tags"]["role"], "lb-pool")
        self.assertEqual(net["ipAllocations"][0]["tags"]["role"], "api-vip")

    def test_tasks(self):
        tasks = list(_tasks())
        self.assertEqual(len(tasks), 3)
        ee = [a["label"] for a in DEF["assets"] if a["assetType"] == "OciImage"][0]
        for ev, stage, t in tasks:
            o = t["options"]
            self.assertEqual(t["taskType"], "ExtensionTaskAnsible")
            self.assertEqual(o["ee"], ee, (ev, stage))
            self.assertLessEqual(len(o["playbook"]), 32)
            self.assertNotEqual(o["playbook"], "job.yml")
            self.assertTrue(os.path.exists(os.path.join(ROOT, "ansible", o["playbook"])), o["playbook"])
            self.assertGreater(o["executionTimeout"], 3600)
        # timeout model: drain T<=30m, <=5 CPs serial, <=5 worker batches, fallback drain 300 s
        t_max = [x for x in DEF["inputs"] if x["label"] == "drain_timeout_minutes"][0]["options"]["maxValue"] * 60
        post = [t for ev, st, t in tasks if ev == "onEdit" and st == "postDeploy"][0]["options"]["executionTimeout"]
        model = 5 * (t_max + 300 + 1200 + 900) + 5 * (t_max + 300 + 1200 + 600) + 3600
        self.assertGreaterEqual(post, model)


if __name__ == "__main__":
    unittest.main()
