#!/usr/bin/env python3
"""Print extension.json with the Ansible bundle and EE tarball URLs replaced.

Asset URLs must be literal URLs in the definition (the platform rejects templates such as
{{configVars.x}}), so they are set when the extension is registered, not per site. The vCSA ISO
URL is the site config `vcsa_iso_url`.

  tools/set-asset-urls.py --bundle-url https://mirror/vsphere-vcenter9-v2.0.2.zip \
      --ee-url https://mirror/ee-vsphere-vcenter9.1.0.1.tar.gz > extension.mirror.json

Either option may be omitted to keep the current URL. URLs are limited to 128 characters.
"""
import argparse
import json
import pathlib
import sys

ASSET_TYPES = {"bundle_url": "AnsibleBundle", "ee_url": "OciImage"}


def main():
    here = pathlib.Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bundle-url", help="URL of the Ansible bundle zip")
    ap.add_argument("--ee-url", help="URL of the execution-environment image tarball (docker save | gzip)")
    ap.add_argument("definition", nargs="?", default=str(here / "extension.json"))
    args = ap.parse_args()

    definition = json.loads(pathlib.Path(args.definition).read_text())
    for opt, asset_type in ASSET_TYPES.items():
        url = getattr(args, opt)
        if not url:
            continue
        if not url.startswith(("http://", "https://")) or len(url) > 128:
            sys.exit(f"--{opt.replace('_', '-')}: must be an http(s) URL of at most 128 characters")
        assets = [a for a in definition["assets"] if a["assetType"] == asset_type]
        if len(assets) != 1:
            sys.exit(f"expected one {asset_type} asset, found {len(assets)}")
        assets[0]["url"] = url

    json.dump(definition, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
