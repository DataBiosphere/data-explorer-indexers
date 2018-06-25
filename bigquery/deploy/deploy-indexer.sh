#!/bin/bash
#
# Deploy indexer on GKE.
#
# jq, gcloud, and kubectl must be installed before running this script.

if (( $# != 1 ))
then
  echo "Usage: bigquery/deploy/deploy-api.sh <dataset>"
  echo "  where <dataset> is the name of a directory in dataset_config/"
  echo "Run this script from project root"
  exit 1
fi

dataset=$1
project_id=$(jq --raw-output '.project_id' dataset_config/${dataset}/deploy.json)

echo "Deploying ${dataset} API Server to project ${project_id}"
echo

# Initialize gcloud and kubectl commands
gcloud config set project ${project_id}
gke_cluster_zone=$(gcloud container clusters list | grep elasticsearch-cluster | awk '{print $2}')
gcloud container clusters get-credentials elasticsearch-cluster --zone ${gke_cluster_zone}

# Create bigquery/deploy/bq-indexer.yml from bigquery/deploy/bq-indexer.yml.templ
elasticsearch_url=$(kubectl get svc elasticsearch | grep elasticsearch | awk '{print $4}')
sed -e "s/PROJECT_ID/${project_id}/" bigquery/deploy/bq-indexer.yaml.templ > bigquery/deploy/bq-indexer.yaml
sed -i -e "s/ELASTICSEARCH_URL/${elasticsearch_url}/" bigquery/deploy/bq-indexer.yaml

# Update docker image to GCR
cd bigquery
docker build -t gcr.io/${project_id}/bq-indexer -f Dockerfile ..
docker push gcr.io/${project_id}/bq-indexer

# Deploy indexer
cd deploy
kubectl delete configmap dataset-config
kubectl create configmap dataset-config --from-file=../../dataset_config/${dataset}
kubectl delete -f bq-indexer.yaml
kubectl create -f bq-indexer.yaml
