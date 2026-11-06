"""Summarise one nested kubespray log for the job output (stdlib only).

usage: python3 ks-summary.py <log> <rc>
Prints: class=<ok|unreachable|failed|rate-limited|error>, the PLAY RECAP, failed/unreachable
hosts and the last fatal lines (secrets: kubespray runs at verbosity 0, which prints no task
results of changed tasks; bootstrap-token / certificate-key patterns are redacted anyway).
"""
import re
import sys

TOKEN = re.compile(r"\b[a-z0-9]{6}\.[a-z0-9]{16}\b")
CERTKEY = re.compile(r"\b[0-9a-f]{64}\b")


def redact(line):
    return CERTKEY.sub("<redacted-hex>", TOKEN.sub("<redacted-token>", line))


def main():
    path, rc = sys.argv[1], int(sys.argv[2])
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        print("class=error (no log)")
        return
    recap, in_recap = [], False
    for line in lines:
        if line.startswith("PLAY RECAP"):
            in_recap, recap = True, []
            continue
        if in_recap:
            if not line.strip():
                in_recap = False
                continue
            recap.append(line)
    failed = sorted({m.group(1) for line in recap
                     for m in [re.match(r"^(\S+)\s+:.*failed=([1-9]\d*)", line)] if m})
    unreach = sorted({m.group(1) for line in recap
                      for m in [re.match(r"^(\S+)\s+:.*unreachable=([1-9]\d*)", line)] if m})
    fatals = [i for i, line in enumerate(lines) if line.startswith(("fatal:", "ERROR!", "[ERROR]"))]
    text = "\n".join(lines[-400:])
    if rc == 0:
        cls = "ok"
    elif re.search(r"toomanyrequests|429 Too Many Requests|rate limit", text, re.I):
        cls = "rate-limited"
    elif unreach and not failed:
        cls = "unreachable"
    elif failed or fatals:
        cls = "failed"
    else:
        cls = "error"
    print("class=%s rc=%d failed_hosts=%s unreachable_hosts=%s" % (cls, rc, ",".join(failed) or "-", ",".join(unreach) or "-"))
    for line in recap:
        print("RECAP " + line)
    for i in fatals[-5:]:
        for line in lines[max(0, i - 2): i + 4]:
            print("FATAL " + redact(line)[:600])
    if rc != 0 and not fatals:
        for line in lines[-25:]:
            print("TAIL " + redact(line)[:600])


if __name__ == "__main__":
    main()
