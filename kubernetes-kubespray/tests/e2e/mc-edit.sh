#!/bin/bash
# mc-edit.sh <extension-instance-id> label=value [label=value...]
#
# One E2E edit of a kubernetes-kubespray instance through the REST API:
#   PATCH the instance config (setOnly inputs are never re-sent: the platform rejects them),
#   deploy the infrastructure, wait for the onEdit Ansible tasks (edit-pre.yaml, deploy.yaml),
#   print each task's result, the failure stdout (from the job exception) and the outputs.
# Needs MC=<path to mc-api.sh> and the METALCLOUD_* env (source the site env file first).
# ALLOW_DATA_LOSS=1 is required for scale-in (the platform refuses to remove servers otherwise).
set -euo pipefail
ei=${1:?usage: mc-edit.sh <instance-id> label=value ...}; shift
: "${MC:?set MC to mc-api.sh}"
setonly='["control_plane_server_type","worker_server_type","os_template","kube_proxy_mode","pod_network_cidr","service_network_cidr","cluster_dns_domain"]'
infra=$($MC GET "/extension-instances/$ei" | jq -r .infrastructureId)
# a PATCH while the previous deploy is still finishing is refused (HTTP 400)
while [ "$($MC GET "/infrastructures/$infra" | jq -r .config.deployStatus)" = "ongoing" ]; do sleep 20; done
cur=$($MC GET "/extension-instances/$ei")
rev=$(echo "$cur" | jq -r .config.revision)
changes=$(printf '%s\n' "$@" | jq -R 'split("=") | {(.[0]): (.[1:] | join("="))}' | jq -s add)
body=$(echo "$cur" | jq -c --argjson so "$setonly" --argjson ch "$changes" '
  {inputVariables: [.inputVariables[] | select(.label as $l | $so | index($l) | not)
     | {label, value: (if $ch[.label] != null then $ch[.label] else .value end)}
     | .value |= (if test("^[0-9]+$") then tonumber elif . == "true" then true elif . == "false" then false else . end)]}')
$MC --if-match "$rev" PATCH "/extension-instances/$ei/config" "$body" >/dev/null
last=$($MC GET "/jobs?filter.infrastructureId=\$eq:$infra&limit=1&sortBy=jobId:DESC" | jq -r '.data[0].jobId // 0')
dl=$([ "${ALLOW_DATA_LOSS:-0}" = 1 ] && echo true || echo false)
dg=$($MC POST "/infrastructures/$infra/actions/deploy" \
  '{"allowDataLoss":'"$dl"',"shutdownOptions":{"attemptSoftShutdown":true,"softShutdownTimeout":180,"attemptHardShutdown":true,"forceShutdown":false}}' | jq -r '.jobGroupId // empty')
echo "$(date -u +%H:%M) deploy of infra $infra started (instance $ei: $*)"
for stage in edit-pre deploy; do
  j=""
  until [ -n "$j" ]; do
    j=$($MC --all GET "/jobs?filter.infrastructureId=\$eq:$infra&filter.functionName=\$eq:ansibleRunnerRun" \
        | jq -r --argjson last "$last" --arg pb "$stage.yaml" \
          '[.[] | select(.jobId > $last and .params[0]=="extension_instance" and .params[4]==$pb)] | .[0].jobId // empty')
    if [ -z "$j" ]; then
      [ "$($MC GET "/infrastructures/$infra" | jq -r .config.deployStatus)" = "finished" ] && { echo "deploy finished, no $stage task ran"; break 2; }
      if [ -n "$dg" ]; then
        cr=$($MC GET "/job-groups/$dg" | jq -r '.cancelReason // empty')
        [ -n "$cr" ] && { echo "deploy rejected: $cr"; exit 1; }
      fi
      sleep 20
    fi
  done
  until st=$($MC GET "/jobs/$j" | jq -r .status); echo "$st" | grep -qE "thrown_error|returned_success|skipped"; do sleep 20; done
  echo "$(date -u +%H:%M) $stage.yaml job $j: $st"
  if [ "$st" != "returned_success" ]; then
    $MC GET "/jobs/$j/exceptions" | jq -r '.data[0].exception.message // empty' > "/tmp/k8s-edit-$j.log"
    grep -E "PLAN|Preflight failed|E-K8S|class=|^fatal|\[ERROR\]" "/tmp/k8s-edit-$j.log" | cut -c1-400 | tail -15
    echo "full log: /tmp/k8s-edit-$j.log (task is auto-retried by the platform; skip with POST /jobs/$j/actions/skip)"
    exit 1
  fi
done
$MC GET "/extension-instances/$ei" | jq -r '.outputVariables[] | select(.label != "admin_kubeconfig" and .label != "ca_cert") | "\(.label) = \(.value)"'
