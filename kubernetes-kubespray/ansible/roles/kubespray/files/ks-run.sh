#!/bin/bash
# ks-run.sh <ks_dir> <run_label> <playbook> [extra ansible-playbook args...]
#
# One nested kubespray run in a scrubbed environment:
#   - env -i + allowlist: nothing from ansible-runner leaks in (callbacks, AWX_*, the runner's
#     fact cache, ANSIBLE_ROLES_PATH, ...). SSH_AUTH_SOCK passes: the runner loads the platform
#     SSH key into an agent.
#   - kubespray's own ansible.cfg, run from the tree root (library = ./library), its own venv
#     (ansible-core 2.19), a fact cache shared by every run of this task (--limit needs it).
#   - fail-fast ssh (kubespray's cfg says ConnectionAttempts=100, timeout 300).
#   - verbosity 0: kubespray prints the kubeadm certificate key / bootstrap token at -v.
#   - stdout+stderr go to <ks_dir>/logs/<run_label>.log (container-local); rc to <run_label>.rc.
set -u
ks_dir=$1; shift
label=$1; shift
playbook=$1; shift
mkdir -p "$ks_dir/home" "$ks_dir/tmp" "$ks_dir/cp" "$ks_dir/facts" "$ks_dir/logs"
inv_args=()
while IFS= read -r src; do
  [ -n "$src" ] && inv_args+=(-i "$src")
done < "$ks_dir/sources"
inv_args+=(-i "$ks_dir/inventory")
rm -f "$ks_dir/logs/$label.rc"

cd /opt/kubespray/src || { echo 97 > "$ks_dir/logs/$label.rc"; exit 0; }
env -i \
  PATH=/opt/kubespray/venv/bin:/usr/bin:/bin \
  HOME="$ks_dir/home" LANG=C.UTF-8 \
  ${SSH_AUTH_SOCK:+SSH_AUTH_SOCK="$SSH_AUTH_SOCK"} \
  ANSIBLE_CONFIG=/opt/kubespray/src/ansible.cfg \
  ANSIBLE_LOCAL_TEMP="$ks_dir/tmp" \
  ANSIBLE_SSH_CONTROL_PATH_DIR="$ks_dir/cp" \
  ANSIBLE_CACHE_PLUGIN_CONNECTION="$ks_dir/facts" \
  ANSIBLE_SSH_ARGS="-o ControlMaster=auto -o ControlPersist=30m -o ConnectionAttempts=10 -o ServerAliveInterval=30 -o ServerAliveCountMax=10 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no" \
  ANSIBLE_TIMEOUT=60 \
  ANSIBLE_FORKS="${KS_FORKS:-50}" \
  ANSIBLE_BECOME=True ANSIBLE_BECOME_METHOD=sudo ANSIBLE_BECOME_USER=root \
  ANSIBLE_NOCOLOR=1 ANSIBLE_FORCE_COLOR=0 ANSIBLE_STDOUT_CALLBACK=default \
  ANSIBLE_DISPLAY_SKIPPED_HOSTS=False \
  /opt/kubespray/venv/bin/ansible-playbook "${inv_args[@]}" -e "@$ks_dir/run-$label.json" "$playbook" "$@" \
  </dev/null >"$ks_dir/logs/$label.log" 2>&1
echo $? > "$ks_dir/logs/$label.rc"
exit 0
