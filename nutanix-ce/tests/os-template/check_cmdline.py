r"""Check a rendered grub.cfg the way the CE 2.1 installer will consume it.

Rebuilds the kernel cmdline the way GRUB does (grub_create_loader_cmdline escapes \ ' "), then reproduces, verbatim, phoenix's kernel cmdline parser (sysUtil.parse_cmd_line) and the answer-file load
(arizona._get_params: json.load(urlopen(AZ_CONF_URL))), then asserts the answer file carries what the
unattended CE install needs and that the cmdline fits the x86 kernel limit (COMMAND_LINE_SIZE 2048).

Usage: python3 -I check_cmdline.py <rendered grub.cfg> [expected host ip]
"""
import json
import re
import shlex
import sys
from urllib.request import urlopen

X86_COMMAND_LINE_SIZE = 2048


def grub_linux_args(cfg):
    for line in cfg.splitlines():
        line = line.strip()
        if line.startswith("linuxefi "):
            # GRUB tokenizes like a shell: double quotes are removed, contents kept verbatim.
            return shlex.split(line)[2:]
    raise SystemExit("no linuxefi line found")


def grub_kernel_cmdline(args):
    # Port of grub_create_loader_cmdline() (grub-core/lib/cmdline.c): what the kernel actually receives.
    # Every \ ' " gets a backslash prefix (except \xHH), and an argument containing a space is re-quoted.
    out = []
    for arg in args:
        buf, i = "", 0
        while i < len(arg):
            c = arg[i]
            if c == "\\" and arg[i + 1:i + 2] == "x" and re.match(r"[0-9a-fA-F]{2}", arg[i + 2:i + 4]):
                buf += arg[i:i + 4]; i += 4; continue
            if c in "\\'\"":
                buf += "\\"
            buf += c; i += 1
        out.append('"%s"' % buf if " " in arg else buf)
    return " ".join(out)


def parse_cmd_line(cmd):
    # Copied from phoenix sysUtil.parse_cmd_line (CE 2.1 / phoenix-5.6.1).
    matches = re.findall(r'([^=]+)=([^=]+)(?: |$)', cmd)
    args = {}
    for pair in matches:
        args[pair[0].strip().upper()] = pair[1].strip().split(' ')[0]
    return args


def main():
    cfg = open(sys.argv[1]).read()
    expected_ip = sys.argv[2] if len(sys.argv) > 2 else None
    cmdline = grub_kernel_cmdline(grub_linux_args(cfg))
    print("kernel cmdline length: %d bytes (limit %d)" % (len(cmdline), X86_COMMAND_LINE_SIZE))
    assert len(cmdline) < X86_COMMAND_LINE_SIZE - 64, "kernel cmdline too long"

    args = parse_cmd_line(cmdline)
    for key in ("INIT", "PHOENIX_IP", "MASK", "GATEWAY", "AZ_CONF_URL", "IMG"):
        assert key in args, "phoenix would not see %s" % key
    assert args["INIT"] == "/ce_installer"
    assert args["IMG"] == "squashfs"

    conf = json.load(urlopen(args["AZ_CONF_URL"]))
    print(json.dumps(conf, indent=2, sort_keys=True))

    # arizona._check_required_params / ParamList.validate expectations for a CE KVM install
    for key in ("hyp_type", "node_position", "svm_installer_url", "hypervisor_iso_url",
                "host_ip", "host_subnet_mask", "default_gw", "ce_cvm_boot_disks", "ce_cvm_data_disks"):
        assert conf.get(key), "answer file missing %s" % key
    assert conf["hyp_type"] == "kvm"
    # arizona._check_required_params: hyp_url = (param_list.hypervisor_iso_url or {}).get("url", "")
    # -> must be an object; retrieve_url_and_md5sum then requires 'md5sum' on every object URL.
    for key in ("hypervisor_iso_url", "svm_installer_url"):
        url_obj = conf[key]
        if isinstance(url_obj, dict):
            assert url_obj.get("url") and re.fullmatch(r"[0-9a-f]{32}", url_obj.get("md5sum", "")), key
        else:
            assert key != "hypervisor_iso_url", "hypervisor_iso_url must be {url, md5sum}, not a string"
    assert conf["hypervisor_iso_url"]["url"].endswith(".iso"), "AHV must be an .iso (else anaconda tarball required)"
    assert conf["ce_eula_accepted"] is True and conf["ce_eula_viewed"] is True
    assert isinstance(conf["ce_cvm_boot_disks"], list) and isinstance(conf["ce_cvm_data_disks"], list)
    # CVM IP is assigned by the extension after install, but CE's ParamList.ce_validate() calls len()
    # on all six host/CVM network fields: they must be present as strings ("" = not set).
    for key in ("host_ip", "host_subnet_mask", "default_gw", "svm_ip", "svm_subnet_mask", "svm_default_gw"):
        assert isinstance(conf.get(key), str), "%s must be a string for CE's ce_validate()" % key
    assert conf["svm_ip"] == "" and conf["svm_subnet_mask"] == "" and conf["svm_default_gw"] == ""
    assert not conf["host_ip"].startswith("192.168.5."), "192.168.5.0/24 is reserved by Nutanix"
    assert conf["host_ip"] == args["PHOENIX_IP"], "installer IP must be the host IP"
    # post_phoenix hook: phoenix pipes urlopen(url).read() into bash (shell.pipe_bash) right before rebooting.
    # It mounts the installer ISO and runs the template asset /post_phoenix.sh (UEFI boot entry fix).
    hook = urlopen(conf["hook_scripts"]["post_phoenix"]).read().decode()
    print("post_phoenix hook: %s" % hook)
    assert hook == ("mkdir -p /tmp/msiso;mount -o ro $(blkid|grep 'LABEL=\"PHOENIX\"'|cut -d: -f1|head -1) /tmp/msiso"
                    "&&bash /tmp/msiso/post_phoenix.sh;umount /tmp/msiso"), hook
    # AHV bond: firstboot's get_vswitch_links() matches uplinks by name, lowercase MAC or driver; an empty
    # list falls back to every NIC of the default drivers (all ports bonded -> wrong active port on us06).
    vs = conf["vswitches"]
    assert len(vs) == 1 and vs[0]["name"] == "br0" and vs[0]["bond-mode"] == "active-backup", vs
    assert vs[0]["uplinks"] and all(re.fullmatch(r"([0-9a-f]{2}:){5}[0-9a-f]{2}", m) for m in vs[0]["uplinks"]), vs
    print("bond uplinks: %s" % vs[0]["uplinks"])
    if expected_ip:
        assert conf["host_ip"] == expected_ip, "picked %s, expected %s" % (conf["host_ip"], expected_ip)
    print("OK")


if __name__ == "__main__":
    main()
