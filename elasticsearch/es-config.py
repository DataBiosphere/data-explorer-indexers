#!/usr/bin/env python3

# es-config.py - Configure an Elasticsearch deployment.
#
# Usage will typically flow as:
#
#   es-config.py k8-create MY-DEPLOYMENT # Create a kubernetes cluster
#
#   es-config.py es-deploy MY-DEPLOYMENT # Deploy Elasticsearch into the kubernetes cluster
#   es-config.py es-delete MY-DEPLOYMENT # Delete Elasticsearch from the kubernetes cluster
#
#   es-config.py k8-delete MY-DEPLOYMENT # Delete the kubernetes cluster
#

import json
import math
import sys
import time

import gen_util
import k8_util
import es_util


def _usage(argv):
  gen_util.err_exit(1, f"Usage: {argv[0]} [k8-create|k8-delete|es-deploy] DEPLOYMENT")


def _vm_memory(ram_string):
  # Try to keep this simple.
  # We only support a string that ends with "gb".
  #
  # Tokenize the value and return a vm_memory value as per:
  #
  # https://cloud.google.com/compute/docs/instances/creating-instance-with-custom-machine-type
  # NOTE: memory must be a multiple of 256 MB
  #
  # So just convert GB to MB.

  if ram_string.endswith('GB'):
    return int(float(ram_string[:-2]) * 1024)
  else:
    gen_util.err_exit(1, [
      "Invalid 'ram' value: '{ram_string}'",
      "Must end in 'GB'"])


def _machine_type(node_config):
  cpu = node_config.get('vm_cpu', 2)
  mem = _vm_memory(node_config.get('vm_ram', '6gb'))

  # Default to e2 for now; might want to make this configurable
  return f"e2-custom-{cpu}-{mem}"


def k8_create(config):
  cluster_name = config['name']

  # Ensure the deployments directory is clean for this cluster
  gen_util.rm_deployment_files(cluster_name)

  cluster_config = {
    'name': config['name'],
    'project': config['project'],
    'zone': config['zone']
  }

  master_pool_config = {
    'name': 'master-pool',
    'count': config['master']['count'],
    'machine-type': _machine_type(config['master']),
    'node-type': 'es-master'
  }

  data_pool_config = {
    'name': 'data-pool',
    'count': config['data']['count'],
    'machine-type': _machine_type(config['data']),
    'node-type': 'es-data'
  }

  # The gcloud create cluster command doesn't allow one to name the default
  # pool (which we'd like to use for the master), though there is a feature
  # request filed for this.
  # For now, we create a default cluster, add the master and data pools
  # and then delete the default-pool.

  gen_util.timestamp()
  print(f"*** Create Kubernetes cluster {cluster_name}.*")
  k8_util.create_cluster(cluster_config)

  gen_util.timestamp()
  k8_util.create_node_pool(cluster_config, master_pool_config)
  gen_util.timestamp()
  k8_util.create_node_pool(cluster_config, data_pool_config)

  gen_util.timestamp()
  k8_util.delete_node_pool(cluster_config, { 'name': 'default-pool' }, True)

  gen_util.timestamp()


def k8_delete(config):
  cluster_name = config['name']

  # Delete the cluster
  gen_util.timestamp()
  print(f"*** Delete Kubernetes cluster {cluster_name}.*")
  k8_util.delete_cluster(config)

  # Clean up the deployments directory
  gen_util.timestamp()
  print(f"*** Delete deployments files for {cluster_name}")
  rm_deployment_files(cluster_name)

  gen_util.timestamp()


def get_loadbalancer_ip(config):

  print("Getting elasticsearch loadbalancer IP address")

  # Right after deployment, the service will not yet be defined
  # Allow for multiple attemps.

  attempt_max = 12
  for attempt in range(attempt_max):
    # NOTE: The hard-coded service name "elasticsearch-es-http" likely
    # limits deployments to one per cloud project. This limitation
    # should be lifted (by changing the es-template.yaml).

    time.sleep(5)

    exit_on_error = (attempt >= attempt_max-1)
    exitcode, value = k8_util.kubectl_command(config, f"""\
      get service elasticsearch-es-http""" + """\
        -o jsonpath="{.status.loadBalancer.ingress[0].ip}"
    """, exit_on_error)

    if value and not exitcode:
      break

    if exit_on_error:
      gen_util.err_exit(1, "loadbalancer IP address not found after {attempt_max} attempts")

  return value


def get_es_user_password(config):

  print("Getting elasticsearch user password")

  ignore, value = k8_util.kubectl_command(config, f"""\
    get secret elasticsearch-es-elastic-user""" + """\
      -o go-template='{{.data.elastic | base64decode }}'
    """)

  return value


def get_tls_crt(config):
  print("Getting elasticsearch TLS certificate")

  ignore, value = k8_util.kubectl_command(config, f"""\
    get secret elasticsearch-es-http-certs-public""" + """\
      -o go-template='{{index .data "tls.crt" | base64decode }}'
    """)

  return value

def es_deploy(config):
  # There is a multi-pass process for configuration, driven by
  # TLS configuration. We first bring up the cluster, including
  # the load balancer. We then get the IP address of the load
  # balancer and include it in the TLS configuration.

  runtime = {
    'loadbalancer_ip': ""
  }

  gen_util.timestamp()

  print()
  print("*** Preparing cluster")
  es_util.prepare_cluster(config)

  print()
  print("*** Formatting configuration")
  gen_util.format_cluster_yaml(config, runtime)

  print()
  print("*** Applying configuration")
  es_util.apply_cluster_yaml(config)

  runtime['loadbalancer_ip'] = get_loadbalancer_ip(config)

  print()
  print("*** Formatting configuration")
  gen_util.format_cluster_yaml(config, runtime)

  print()
  print("*** Applying configuration")
  es_util.apply_cluster_yaml(config)

  runtime['password'] = get_es_user_password(config)

  print()
  print("*** Writing deployment information")
  gen_util.write_runtime_file(config, runtime)
  gen_util.write_netrc_file(config, runtime)
  gen_util.write_tls_crt_file(config, get_tls_crt(config))

  gen_util.timestamp()


def es_delete(config):

  gen_util.timestamp()

  print()
  print("*** Deleting Elasticsearch cluster")
  es_util.delete_cluster(config)


### MAIN

def main(argv):
  if len(argv) != 3:
    _usage(argv)

  command = argv[1]
  deployment = argv[2]

  if not command in ['k8-create', 'k8-delete', 'es-deploy', 'es-delete']:
    _usage(argv)

  config = gen_util.load_config(deployment)

  if command == 'k8-create':
    k8_create(config)
  if command == 'k8-delete':
    k8_delete(config)


  if command == 'es-deploy':
    es_deploy(config)
  if command == 'es-delete':
    es_delete(config)


if __name__ == '__main__':
  main(sys.argv)
