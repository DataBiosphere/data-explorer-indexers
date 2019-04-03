#!/bin/bash
#
# Delete the oldest cluster for a dataset.
# Run after a redeploy.

set -o errexit
set -o nounset

if (( $# != 1 ))
then
  echo "Usage: util/delete-cluster.sh <dataset>"
  echo "  where <dataset> is the name of a directory in dataset_config/"
  echo "Run this script from project root"
  exit 1
fi

dataset=$1
project_id=$(jq --raw-output '.project_id' dataset_config/${dataset}/deploy.json)

gcloud config set project ${project_id}
echo "gcloud project set to $(gcloud config get-value project)"

# Need to get cluster name by sorting the list of clusters, and choosing to
# use the one with the greatest timestamp (most recent)
cluster_list=$(gcloud container clusters list)
cluster_line=$(echo "${cluster_list}" | grep elasticsearch-cluster- | sort -rn -k1 | head -n1)
cluster_name=$(echo "${cluster_line}" | awk '{print $1}')
zone=$(echo "${cluster_line}" | awk '{print $2}')

# Display list of clusters to the user
echo "${cluster_list}"
cluster_to_delete=$(echo "${cluster_list}" | grep elasticsearch-cluster- | sort -n -k1 | head -n1 | awk '{print $1}')
echo "Preparing to delete ${cluster_to_delete}..."
echo "Double check that this is the correct cluster to delete."

gcloud container clusters delete "${cluster_to_delete}" --zone="${zone}"

