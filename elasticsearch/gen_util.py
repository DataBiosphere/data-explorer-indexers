#!/usr/bin/env python3

# gen_util.py
#
# Generic utility functions for various operations, including
# running commands and reading/writing deployment configuration.

import datetime
import json
import os
import subprocess
import sys


_CONFIG_FILE="es-config.json"


def err_exit(code, message_list):
  for line in message_list:
    print(line, file=sys.stderr)
  sys.exit(code)


def timestamp():
  print(datetime.datetime.now())


def run_command(command):

  ret = os.system(command)
  if ret:
    err_exit(ret, [f"Command\n{command}"])


def get_command_output(command, exit_on_error=True):
  # Utility routine to run a command as though from the command-line
  # (using the shell) and capture the output if there is no error.
  # If an error occurs, the command will throw an exception and the
  # script will terminate.

  (ret, output) = subprocess.getstatusoutput(command)
  if ret and exit_on_error:
    err_exit(ret, [
      f"Command\n{command}:",
      output,
      f"Exit code: {ret}"])

  return ret, output


def load_config(deployment):
  with open(_CONFIG_FILE) as f:
    all_lines = f.readlines()

  # Support shell/python-style comments
  for line_no in range(len(all_lines)):
    line = all_lines[line_no]

    hash_loc = line.find('#')
    if hash_loc >= 0:
      all_lines[line_no] = line[0:hash_loc]
    else:
      all_lines[line_no] = line.rstrip()

  # Parse the json
  try:
    all_config = json.loads('\n'.join(all_lines))
  except json.decoder.JSONDecodeError as e:
    err_exit(1, all_lines + [e])

  # Return the deployment
  try:
    return next(config for config in all_config if config['name'] == deployment)
  except StopIteration:
    err_exit(1, [f"Deployment {deployment} not found in {_CONFIG_FILE}"])


def create_deployments_dir():
  os.makedirs("./deployments", exist_ok=True)
  os.chmod("./deployments", 0o700)


def get_es_config_file(config):
  return f"./deployments/{config['name']}.yaml"


def get_es_runtime_file(config):
  return f"./deployments/{config['name']}.runtime.json"


def get_es_tls_crt(config):
  return f"./deployments/{config['name']}.tls.crt"


def get_netrc_file(config):
  return f"./deployments/{config['name']}.netrc"


def write_runtime_file(config, runtime):
  # Since this file will contain the password, make sure to open with
  # it being only visible to user.

  output_file = get_es_runtime_file(config)
  print(f"Writing {output_file}...")

  create_deployments_dir()

  os.umask(0)
  with open(os.open(output_file, os.O_CREAT | os.O_WRONLY, 0o600), 'w') as f:
    json.dump(runtime, f, indent=4)


def write_netrc_file(config, runtime):
  # The "curl" command supports user authentication by finding
  # relevant configuration in a netrc format file.
  # See:
  #   man curl
  #   man 5 netrc

  # For simplicity, we write a netrc file for each cluster and
  # users can then use the --netrc-file flag to curl.

  output_file = get_netrc_file(config)
  print(f"Writing {output_file}...")

  machine = runtime['loadbalancer_ip']
  login = "elastic"
  password = runtime['password']

  with open(os.open(output_file, os.O_CREAT | os.O_WRONLY, 0o600), 'w') as f:
    print(f"machine {machine} login {login} password {password}", file=f)


def write_tls_crt_file(config, tls_crt):
  # Since this file will contain the certificate, make sure to open with
  # it being only visible to user.

  output_file = get_es_tls_crt(config)
  print(f"Writing {output_file}...")

  create_deployments_dir()

  os.umask(0)
  with open(os.open(output_file, os.O_CREAT | os.O_WRONLY, 0o600), 'w') as f:
    f.write(tls_crt)


def rm_deployment_files(cluster_name):
  run_command(f"rm -f ./deployments/{cluster_name}.*")


def format_cluster_yaml(config, runtime):
  # Prepare the configuration values
  values = {
    'ELASTICSEARCH_IP': runtime['loadbalancer_ip'],

    'MASTER_COUNT': config['master']['count'],
    'MASTER_K8_NODE_CPU': config['master']['k8_node_cpu'],
    'MASTER_K8_NODE_RAM': config['master']['k8_node_ram'],
    'MASTER_K8_DISK_SIZE': config['master']['k8_disk_size'],
    'MASTER_ES_JVM_RAM': config['master']['es_jvm_ram'],

    'DATA_COUNT': config['data']['count'],
    'DATA_K8_NODE_CPU': config['data']['k8_node_cpu'],
    'DATA_K8_NODE_RAM': config['data']['k8_node_ram'],
    'DATA_K8_DISK_SIZE': config['data']['k8_disk_size'],
    'DATA_ES_JVM_RAM': config['data']['es_jvm_ram']
  }

  # Read up the template
  with open('es-template.yaml') as f:
    es_template = f.read()

  # Format the template with the config values
  es_config = es_template.format(**values)

  # Write the results to the config directory
  output_file = get_es_config_file(config)
  print(f"Writing {output_file}...")

  create_deployments_dir()

  os.umask(0)
  with open(output_file, "w") as f:
    f.write(es_config)


if __name__ == '__main__':
  pass
