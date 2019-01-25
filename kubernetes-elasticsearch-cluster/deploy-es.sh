#!/bin/bash

set -o errexit
set -o nounset

if (( $# != 1 ))
then
  echo "Usage: kubernetes-elasticsearch-cluster/deploy-es.sh <dataset>"
  echo "  where <dataset> is the name of a directory in dataset_config/"
  echo "Run this script from project root"
  exit 1
fi

dataset=$1
project_id=$(jq --raw-output '.project_id' dataset_config/${dataset}/deploy.json)
echo "Deploying Elasticsearch for dataset $dataset in project $project_id"

gcloud config set project $project_id
zone=$(gcloud container clusters list | grep elasticsearch-cluster | awk '{print $2}')
gcloud container clusters get-credentials elasticsearch-cluster --zone ${zone}

# select (.!=null) makes jq return empty string instead of null
# See https://github.com/stedolan/jq/issues/354#issuecomment-46641827
node_pool_machine_type=$(jq --raw-output '.node_pool_machine_type|select (.!=null)' dataset_config/${dataset}/deploy.json)
node_pool_num_nodes=$(jq --raw-output '.node_pool_num_nodes|select (.!=null)' dataset_config/${dataset}/deploy.json)

cd kubernetes-elasticsearch-cluster
cp es-data-stateful.yaml es-data-stateful-deploy.yaml

# If node_pool_num_nodes is set in deploy.json, replace it in the deploy yaml file.
if [ -n "$node_pool_num_nodes" ]; then
  sed -i -e "s/replicas: 3/replicas: $node_pool_num_nodes/g" es-data-stateful-deploy.yaml
fi
# If node_pool_machine_type is set in deploy.json, update the deploy yaml file with
# the correct resource requirements.
if [ -n "$node_pool_machine_type" ]; then
  if [ "$node_pool_machine_type" == "n1-standard-1" ] || [ "$node_pool_machine_type" == "n1-standard-2" ]; then
    echo "A minimum of n1-standard-4 machine type must be used to avoid out of memory errors."
    exit 1
  fi

  describe_text=$(gcloud compute machine-types describe $node_pool_machine_type --zone ${zone}) || true
  cpu=$(echo "$describe_text" | grep guestCpus | awk '{print $2}')
  mem=$(echo "$describe_text" | grep memoryMb | awk '{print $2}')
  # If no zone was found in App Engine, print the help text describing that it must
  # be passed in as an argument to this script.
  if [ -z "$cpu" ] || [ -z "$mem" ]; then
    echo "Failed to locate data about machine type: $node_pool_machine_type"
    exit 1
  fi

  # Update the CPU request and limit in the kubernetes config to match the machine type. 
  # For more info on requests and limits for Pods, see: 
  # https://kubernetes.io/docs/concepts/configuration/manage-compute-resources-container/#resource-requests-and-limits-of-pod-and-container
  limit_cpu="$(($cpu - 1))"
  req_cpu="$((1000*$cpu/2))"
  sed -i -e "s/cpu: 2/cpu: ${req_cpu}m/g" es-data-stateful-deploy.yaml
  sed -i -e "s/cpu: 3/cpu: ${limit_cpu}/g" es-data-stateful-deploy.yaml

  # Update the java heap size in the kubernetes config to match the machine type.
  # Elasticsearch documentation recommends allocating no more than 50% of physical RAM to
  # the JVM heap: https://www.elastic.co/guide/en/elasticsearch/reference/current/heap-size.html
  heap_mem="$((mem/2))"
  sed -i -e "s/-Xms2g -Xmx2g/-Xms${heap_mem}m -Xmx${heap_mem}m/g" es-data-stateful-deploy.yaml
fi

# Do not fail on errors (from set -o errexit) when because things might not exist.
kubectl delete -f es-discovery-svc.yaml || true
kubectl delete -f es-svc.yaml || true
kubectl delete -f es-master-svc.yaml || true
kubectl delete -f es-data-svc.yaml || true
kubectl delete -f es-master-stateful.yaml || true
kubectl delete -f es-data-stateful-deploy.yaml || true


kubectl create -f es-discovery-svc.yaml
kubectl create -f es-svc.yaml
kubectl create -f es-master-svc.yaml
kubectl create -f es-data-svc.yaml

kubectl create -f es-master-stateful.yaml
kubectl rollout status -f es-master-stateful.yaml
kubectl create -f es-data-stateful-deploy.yaml
kubectl rollout status -f es-data-stateful-deploy.yaml

rm es-data-stateful-deploy.yaml

cd ..
