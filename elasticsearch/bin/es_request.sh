#!/bin/bash

set -o errexit
set -o nounset

# es_request.sh
#
# Utility for sending requests to elasticsearch.
#
# Expects cluster information to be found in:
#   data-explorer/elasticsearch/deployments/
#     <deployment>.tls.crt
#     <deployment>.netrc

if [[ $# -lt 1 ]]; then
  2>&1 echo "Usage: $0 DEPLOYMENT [METHOD] [PATH] [BODY]"
  exit 1
fi

readonly DEPLOYMENT="${1}"
readonly METHOD="${2:-GET}"
readonly URL_PATH="${3:-}"
readonly BODY="${4:-}"

readonly DEPLOYMENT_DIR="$(readlink -f "$(dirname "$0")"/../deployments)"

readonly ES_IP="$(jq -r ".loadbalancer_ip" "${DEPLOYMENT_DIR}/${DEPLOYMENT}.runtime.json")"

curl  \
  --cacert "${DEPLOYMENT_DIR}/${DEPLOYMENT}.tls.crt" \
  --netrc-file "${DEPLOYMENT_DIR}/${DEPLOYMENT}.netrc" \
  -H 'Content-Type: application/json' \
  -X "${METHOD}" "https://${ES_IP}:9200/${URL_PATH}" \
  ${BODY:+-d "${BODY}"}
