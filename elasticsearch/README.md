# Elasticsearch deployments

## Overview

Data Explorer is driven by data stored in Elasticsearch.
For speed and simplicity during development, one typically wants to deploy
Elasticsearch on the local development machine.  When deploying to production,
one typically wants to deploy to an Elasticsearch cluster.

## Configuration

This directory includes tools for such deployments. Deployments are driven by
a configuration file in the local directory. The configuration file is a
simple JSON file (`es-config.json`) with an array of named deployments, each
of the form:

```
{
  "name": "<name>",
  <resource-definitions>
}
```

A deployment on Google Kubernetes Engine will define resource requirements
for the master and data nodes. An example might look like:

```
{
  "name": "my-1000g-small",

  "project": "my-cloud-project",
  "zone": "us-central1-f",

  "master": {
    "count":  1,            # Number of master nodes; 1 per VM

    "vm_cpu": 2,            # Number of cores for the VM
    "vm_ram": "7GB",        # Amount of VM memory

    "k8_node_cpu": "1100m", # Amount of cpu for kubernetes node (1000m == 1 core)
    "k8_node_ram": "4Gi",   # Amount of ram for kubernetes node (docker container system services)
    "k8_disk_size": "30Gi", # Amount of persistent disk

    "es_jvm_ram": "3g"      # Amount of Elasticsearch JVM memory
  },
  "data": {
    "count":  1,

    "vm_cpu": 2,
    "vm_ram": "13GB",

    "k8_node_cpu": "1300m",
    "k8_node_ram": "9.75Gi",
    "k8_disk_size": "100Gi",

    "es_jvm_ram": "9g"
  }
}
```

Kubernetes as a generic deployment platform has a wide range of options that
allow for complex distribution of containerized applications and services
across a pool of compute resources.

Such complexity is not generally needed for a Data Explorer Elasticsearch
deployment. For Data Explorer Elasticsearch, one typically wants some very
specific resources deployed:

- Master Node(s)
  - One GCE VM for each master node
  - One Kubernetes Pod for each master node VM
- Data Node(s)
  - One GCE VM for each data node
  - One Kubernetes Pod for each data VM

The intent of this configuration is to simplify management of deployments.

## Tools

To create a Kubernetes cluster:

`es-config.py k8-create MY-DEPLOYMENT`

To deploy Elasticsearch:

`es-config.py es-deploy MY-DEPLOYMENT`

To delete an Elasticsearch deployment from the Kubernetes cluster:

`es-config.py es-delete MY-DEPLOYMENT`

To delete the Kubernetes cluster:

`es-config.py k8-delete MY-DEPLOYMENT`

To get information about the deployment:

`es-config.py status MY-DEPLOYMENT`

## Deployment state

Deployment information will be stored in:

```
deployments/
  <MY-DEPLOYMENT>.netrc          # Can be used to `curl` commands to Elasticsearch
  <MY-DEPLOYMENT>.runtime.json   # Runtime information (such as IP address)
  <MY-DEPLOYMENT>.tls.crt        # ES cluster certificate
  <MY-DEPLOYMENT>.yaml           # ECK configuration for the cluster
```

