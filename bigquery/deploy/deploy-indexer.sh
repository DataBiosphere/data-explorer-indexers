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
# Initialize gcloud and kubectl commands
gcloud config set project ${project_id}

# Need to get cluster name by sorting the list of clusters, and choosing to
# use the one with the greatest timestamp (most recent)
cluster_line=$(gcloud container clusters list | grep elasticsearch-cluster- | sort -rn -k1 | head -n1)
cluster_name=$(echo $cluster_line | awk '{print $1}')
zone=$(echo $cluster_line | awk '{print $2}')

bold=$(tput bold)
normal=$(tput sgr0)
echo "Deploying BigQuery indexer in cluster ${bold}$cluster_name${normal} for" \
  "${bold}dataset" "$dataset${normal} in ${bold}project $project_id${normal}"
echo

gcloud container clusters get-credentials ${cluster_name} --zone ${zone}

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

echo "Indexer is running now. Monitor the logs by running \`kubectl logs -f \$(kubectl get pods | awk '/bq-indexer/ {print \$1;exit}')\`"
echo ""
echo "Verify the indexer was successful by running \`kubectl exec -it es-data-0 curl localhost:9200/_cat/indices?v\`"