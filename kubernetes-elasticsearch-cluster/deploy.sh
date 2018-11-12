#!/usr/bin/env bash

set -o errexit
set -o nounset

if (( $# != 1 ))
then
  echo "Usage: kubernetes-elasticsearch-cluster/deploy.sh <dataset>"
  echo "  where <dataset> is the name of a directory in dataset_config/"
  echo "Run this script from project root"
  exit 1
fi

dataset=$1
java_opts=$(jq --raw-output '.es_java_opts' dataset_config/${dataset}/deploy.json)

cd kubernetes-elasticsearch-cluster
cp es-data-stateful.yaml es-data-stateful-deploy.yaml
# If a custom es_java_opts is set, replace it in the deploy yaml file.
if [ "$java_opts" != "null" ] && [ ! -z "$java_opts" ]; then
	sed -i -e "s/-Xms1g -Xmx1g/$java_opts/g" es-data-stateful-deploy.yaml
fi

# Do not fail on errors (from set -o errexit) when creating pods because
# they may already exist.
kubectl create -f es-discovery-svc.yaml || true
kubectl create -f es-svc.yaml || true

kubectl create -f es-master-svc.yaml || true
kubectl create -f es-master-stateful.yaml || true
kubectl rollout status -f es-master-stateful.yaml

kubectl create -f es-client.yaml || true
kubectl rollout status -f es-client.yaml

kubectl create -f es-data-svc.yaml || true

# Delete the data nodes if they exist to apply any changes
# to es_java_opts in deploy.json.
kubectl delete -f es-data-stateful-deploy.yaml || true
kubectl create -f es-data-stateful-deploy.yaml
kubectl rollout status -f es-data-stateful-deploy.yaml

rm es-data-stateful-deploy.yaml

cd ..
