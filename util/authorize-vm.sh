#!/bin/bash
IP_ADDRESS=$(gcloud compute instances list | grep indexer | awk '{print $5}')
IP_ADDRESS_OF_VM="${IP_ADDRESS}/32"
CLUSTER_NAME=$(gcloud container clusters list | grep elasticsearch | awk '{print $1}')
gcloud container clusters update ${CLUSTER_NAME} --enable-master-authorized-networks --master-authorized-networks "${IP_ADDRESS_OF_VM}" --zone us-central1-a
