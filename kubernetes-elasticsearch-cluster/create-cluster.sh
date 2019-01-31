#!/bin/bash

set -o errexit
set -o nounset

help_text="Usage: kubernetes-elasticsearch-cluster/create-cluster.sh <dataset> <zone>
  where <dataset> is the name of a directory in dataset_config/
  <zone> is only needed if 'gcloud app create' hasn't yet been run in this project.
Run this script from project root"

if (( $# != 1 && $# != 2 )); then
  echo "$help_text"
  exit 1
fi

dataset=$1
zone=""
project_id=$(jq --raw-output '.project_id' dataset_config/${dataset}/deploy.json)

bold=$(tput bold)
normal=$(tput sgr0)
echo "Creating Kubernetes cluster for ${bold}dataset $dataset${normal} in ${bold}project $project_id${normal}"

gcloud config set project $project_id

# Use the zone argument if present, otherwise try to lookup the App Engine location 
# for this project.
if (( $# == 2 )); then
  zone=$2
else
  describe_text=$(gcloud app describe) || true
  app_engine_region=$(echo "$describe_text" | grep locationId | awk '{print $2}')
  # If no zone was found in App Engine, print the help text describing that it must
  # be passed in as an argument to this script.
  if [ -z "$app_engine_region" ]; then
    echo "$help_text"
    exit 1
  fi

  # Locations with only a single region (e.g. "us-central1") do not have the last 
  # number returned in 'gcloud app describe' location (only "us-central"). 
  # Check if the location is missing a digit as its last character and, if so,
  # add a "1".
  last_char=${app_engine_region: -1}
  if [[ ! $last_char =~ ^[0-9]+$ ]]; then
  	app_engine_region+="1"
  fi
  zone="${app_engine_region}-a"
fi

node_pool_machine_type=$(jq --raw-output '.node_pool_machine_type' dataset_config/${dataset}/deploy.json)
if [ "$node_pool_machine_type" == "null" ] || [ -z "$node_pool_machine_type" ]; then
	node_pool_machine_type="n1-standard-4"
fi

if [ "$node_pool_machine_type" == "n1-standard-1" ] || [ "$node_pool_machine_type" == "n1-standard-2" ]; then
  echo "A minimum of n1-standard-4 machine type must be used to avoid out of memory errors."
  exit 1
fi

node_pool_num_nodes=$(jq --raw-output '.node_pool_num_nodes' dataset_config/${dataset}/deploy.json)
if [ "$node_pool_num_nodes" == "null" ] || [ -z "$node_pool_num_nodes" ]; then
	node_pool_num_nodes="3"
fi

gcloud container clusters create elasticsearch-cluster --num-nodes=${node_pool_num_nodes} --machine-type=${node_pool_machine_type} --service-account=indexer@${project_id}.iam.gserviceaccount.com --zone=${zone}
