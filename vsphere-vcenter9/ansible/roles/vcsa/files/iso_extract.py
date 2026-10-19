#!/usr/bin/env python3
"""Extract directory trees from the vCSA ISO without mounting it.

Usage: iso_extract.py <iso> <dest> <iso_dir> [<iso_dir> ...]
Each <iso_dir> (e.g. /vcsa) is written to <dest>/<basename of iso_dir>.

Containers cannot loop-mount and UBI 10 ships no xorriso/bsdtar, hence pycdlib. Files are
read through the UDF view: the appliance OVA is larger than 4 GiB, which ISO 9660 stores as
multiple extents that pycdlib's ISO 9660/Rock Ridge readers truncate (to size mod 4 GiB).
"""
import os
import sys

import pycdlib


def extract_tree(iso, udf, iso_path, out_path):
    os.makedirs(out_path, exist_ok=True)
    for child in udf.list_children(iso_path):
        if child is None:  # parent entry
            continue
        name = child.file_identifier().decode()
        src = iso_path.rstrip('/') + '/' + name
        dst = os.path.join(out_path, name)
        if child.is_dir():
            extract_tree(iso, udf, src, dst)
        elif child.is_symlink():
            # UDF symlink targets are not exposed by pycdlib; Rock Ridge has them
            target = iso.get_record(rr_path=src).rock_ridge.symlink_path().decode()
            if not os.path.lexists(dst):
                os.symlink(target, dst)
        else:
            udf.get_file_from_iso(dst, udf_path=src)
            expected = child.get_data_length()
            if os.path.getsize(dst) != expected:
                sys.exit('short extract of %s: %d of %d bytes' % (src, os.path.getsize(dst), expected))
            # installer binaries, bundled libraries and ovftool must stay executable
            os.chmod(dst, 0o755)


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    iso_file, dest, dirs = sys.argv[1], sys.argv[2], sys.argv[3:]
    iso = pycdlib.PyCdlib()
    iso.open(iso_file)
    try:
        if not iso.has_udf():
            sys.exit('ISO has no UDF filesystem: ' + iso_file)
        udf = iso.get_udf_facade()
        for d in dirs:
            extract_tree(iso, udf, d, os.path.join(dest, os.path.basename(d.rstrip('/'))))
    finally:
        iso.close()


if __name__ == '__main__':
    main()
