#!/bin/bash
#
# Deploy indexer on GKE.
#
# jq, gcloud, and kubectl must be installed before running this script.

set -o errexit
set -o nounset

if (( $# != 1 ))
then
  echo "Usage: bigquery/deploy/deploy-indexer.sh <dataset>"
  echo "  where <dataset> is the name of a directory in dataset_config/"
  echo "Run this script from project root"
  exit 1
fi

dataset=$1
project_id=$(jq --raw-output '.project_id' dataset_config/${dataset}/deploy.json)

echo "Deploying BigQuery indexer for ${dataset} to project ${project_id}"
echo

# Initialize gcloud and kubectl commands
gcloud config set project ${project_id}
gke_cluster_zone=$(gcloud container clusters list | grep elasticsearch-cluster | awk '{print $2}')
gcloud container clusters get-credentials elasticsearch-cluster --zone ${gke_cluster_zone}

# Create bigquery/deploy/bq-indexer.yaml from bigquery/deploy/bq-indexer.yaml.templ
elasticsearch_url=$(kubectl get svc elasticsearch | grep elasticsearch | awk '{print $4}')
sed -e "s/PROJECT_ID/${project_id}/" bigquery/deploy/bq-indexer.yaml.templ > bigquery/deploy/bq-indexer.yaml
sed -i -e "s/ELASTICSEARCH_URL/${elasticsearch_url}/" bigquery/deploy/bq-indexer.yaml

# Update docker image to GCR
cd bigquery
docker build -t gcr.io/${project_id}/bq-indexer -f Dockerfile ..
docker push gcr.io/${project_id}/bq-indexer

# Deploy indexer
cd deploy
kubectl delete configmap dataset-config || true
kubectl create configmap dataset-config --from-file=../../dataset_config/${dataset}
# Do not fail on errors (from set -o errexit) when deleting the bq-indexer because 
# it may not yet exist.
kubectl delete -f bq-indexer.yaml || true
kubectl create -f bq-indexer.yaml
