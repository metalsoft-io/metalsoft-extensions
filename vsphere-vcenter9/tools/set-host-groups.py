#!/usr/bin/env python3
"""Rewrite extension.json with N ESXi host groups, each with its own server type and host count.

Every group becomes an instance array labelled esxi-<n> with two inputs, server_type_<n> and
host_count_<n>. Group 1 carries vCenter, so its count is 1..MAX; the others are 0..MAX (0 = unused).
The playbooks find the groups by name (^esxi[-_][0-9]+$), so changing N needs no playbook or bundle change.

  tools/set-host-groups.py 4                 # rewrite ./extension.json in place with 4 groups
  tools/set-host-groups.py 6 --max-hosts 16  # 6 groups, at most 16 hosts each

The platform allows at most 12 instance arrays. Run it before registering the extension; once registered,
a different N is a new extensionVersion (a registered extension keeps the groups it was created with).
"""
import argparse
import copy
import json
import pathlib
import re
import sys

MAX_ARRAYS = 12
GROUP_INPUT = re.compile(r"^(server_type|host_count)_[0-9]+$")


def group_inputs(n, max_hosts):
    first = n == 1
    return [
        {
            "label": f"server_type_{n}",
            "name": f"server_type_{n}",
            "helpText": (f"Server type for host group {n}. "
                         + ("Its first host also runs vCenter ('small': 4 vCPU / 21 GB RAM on top of ESXi)."
                            if first else "Pick any type if the group's host count is 0.")),
            "inputType": "ExtensionInputServerType",
            "options": {"minCpu": 1, "minRamGb": 32},
        },
        {
            "label": f"host_count_{n}",
            "name": f"host_count_{n}",
            "helpText": (f"ESXi hosts in group {n}. "
                         + ("vCenter runs on the first. " if first else "0 leaves the group unused. ")
                         + "Edit later to add/remove hosts (removed hosts: no powered-on VMs)."),
            "inputType": "ExtensionInputInteger",
            "defaultValue": 1 if first else 0,
            "options": {"minValue": 1 if first else 0, "maxValue": max_hosts},
        },
    ]


def main():
    here = pathlib.Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("groups", type=int, help=f"number of host groups, 1..{MAX_ARRAYS}")
    ap.add_argument("--max-hosts", type=int, default=32, help="maximum hosts per group (default 32)")
    ap.add_argument("definition", nargs="?", default=str(here / "extension.json"))
    args = ap.parse_args()
    if not 1 <= args.groups <= MAX_ARRAYS:
        sys.exit(f"groups: 1..{MAX_ARRAYS} (the platform's instance array limit)")

    path = pathlib.Path(args.definition)
    definition = json.loads(path.read_text())
    infra = definition["infrastructure"]

    # The first existing group is the template for networks, OS template and anything else on the array.
    template = copy.deepcopy(infra["instanceArrays"][0])
    arrays = []
    for n in range(1, args.groups + 1):
        array = copy.deepcopy(template)
        array.update({
            "label": f"esxi-{n}",
            "instanceCount": f"#/input/host_count_{n}",
            "serverType": f"#/input/server_type_{n}",
        })
        arrays.append(array)
    infra["instanceArrays"] = arrays

    # Group inputs go first, in group order; every other input keeps its place after them.
    others = [i for i in definition["inputs"] if not GROUP_INPUT.match(i["label"])]
    definition["inputs"] = [i for n in range(1, args.groups + 1) for i in group_inputs(n, args.max_hosts)] + others

    path.write_text(json.dumps(definition, indent=2) + "\n")
    print(f"{path}: {args.groups} host groups (esxi-1..esxi-{args.groups}), up to {args.max_hosts} hosts each")


if __name__ == "__main__":
    main()
