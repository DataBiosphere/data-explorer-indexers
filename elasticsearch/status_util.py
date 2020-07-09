import datetime
import json
import os
import re

import gen_util
import k8_util

# status_util.py
#
# Utility functions for the es-config "status" command including for:
# - printing resources (disks, cpu, memory, vms, k8 nodes, etc.)
# - getting resources (clusters, managed instance groups, nodes, pods)


def _printable_disk(disk_type, disk_size_gb):
  if disk_type:
    return f"{os.path.basename(disk_type)}, {disk_size_gb} GB"

  return None


def _printable_cpu(millis):
  if millis < 1000:
    return f"{int(millis)} mCPU"
  return f"{millis/1000:.2f}"


def _printable_mem(bytes):
  if bytes / 1024 < 1:
    return f"{bytes}"
  if bytes / (1024**2) < 1:
    return f"{bytes/1024:.2f} Ki"
  if bytes / (1024**3) < 1:
    return f"{bytes/(1024**2):.2f} Mi"
  if bytes / (1024**4) < 1:
    return f"{bytes/(1024**3):.2f} Gi"

  return f"{bytes/(1024**4):.2f} Ti"


def _cpu_str_to_millis(cpu):
  if cpu.endswith('m'):
    return float(cpu[:-1])

  return int(float(cpu) * 1000)


def _mem_str_to_bytes(mem):
  if mem.endswith('Ki'):
    return float(mem[:-2]) * 1024
  elif mem.endswith('Mi'):
    return float(mem[:-2]) * 1024**2
  elif mem.endswith('Gi'):
    return float(mem[:-2]) * 1024**3
  elif mem.endswith('Ti'):
    return float(mem[:-2]) * 1024**4
  else:
    assert False, mem  # So we can discover and add more cases


def _sum_cpu_requested(pods):
  sum_millis = 0
  for pod in pods:
    for container in pod.get('spec', {}).get('containers', []):
      cpu = container.get('resources', {}).get('requests', {}).get('cpu')
      if cpu:
        sum_millis += _cpu_str_to_millis(cpu)

  return sum_millis


def _sum_mem_requested(pods):

  sum_bytes = 0
  for pod in pods:
    for container in pod.get('spec', {}).get('containers', []):
      mem = container.get('resources', {}).get('requests', {}).get('memory')
      # print(f"{pod['metadata']['name']}: {mem}")
      if mem:
        sum_bytes += _mem_str_to_bytes(mem)

  return sum_bytes


def print_node_pool(pool, mig, disks, nodes, pods):
  """Print information about a node pool.

  This function brings together information from:

  - GKE (the node pool backed by a managed instance group)
  - GCE (the managed instance group of VMs)
  - Kubernetes (the nodes)
  - Kubernetes (the pods on the nodes)

  The goal is to give an overview of the node pool such that one can understand
  resource allocations. Most notably, it can be painful to deal with:

  - different units used by different systems (GB vs G vs. Gi)
  - resource overhead of each system
  """

  scaling = pool['autoscaling']
  print(f"Node pool: {pool['name']}")
  print("  Configuration:")
  print(f"    initial: {pool['initialNodeCount']}, min: {scaling['minNodeCount']}, max: {scaling['maxNodeCount']}")

  print(f"    machine type: {pool['config']['machineType']}")
  print(f"    boot disk: {_printable_disk(pool['config']['diskType'], pool['config']['diskSizeGb'])}")

  if mig:
    print()
    print("  VM Instances:")

    # If there are any actions going on (creating, deleting, etc.) they are in the
    # currentActions dict with a value greater than zero.
    actions = [a for a in mig.get('currentActions', {}).items() if a[1] > 0]
    print(f"    target: {mig['targetSize']}, actions: {actions}")

  if nodes:
    print()
    print("  Kubernetes nodes:")
    print(f"    count: {len(nodes)}")

    # For larger cluster sizes, we should probably do something different.
    # like min/max/avg. For now, just emit all the nodes.

    cpu_requested = {}
    mem_requested = {}
    for node in nodes:
      pods_for_node = get_node_pool_pod_details(pods, [node])

      cpu_requested[node['metadata']['name']] = _sum_cpu_requested(pods_for_node)
      mem_requested[node['metadata']['name']] = _sum_mem_requested(pods_for_node)

    print("    cpu:")
    for node in nodes:
      status = node['status']

      allocatable = _printable_cpu(_cpu_str_to_millis(status['allocatable']['cpu']))
      capacity = _printable_cpu(_cpu_str_to_millis(status['capacity']['cpu']))
      requested = _printable_cpu(cpu_requested[node['metadata']['name']])

      print(f"      requested: {requested}, allocatable: {allocatable}, capacity {capacity}")


    print("    memory:")
    for node in nodes:
      status = node['status']

      allocatable = _printable_mem(_mem_str_to_bytes(status['allocatable']['memory']))
      capacity = _printable_mem(_mem_str_to_bytes(status['capacity']['memory']))
      requested = _printable_mem(mem_requested[node['metadata']['name']])

      print(f"      requested: {requested}, allocatable: {allocatable}, capacity {capacity}")

    print("    disks:")
    for node in nodes:
      node_disks = _get_disks_for_node(node, disks)
      # We expect there to be one (boot) or two (boot + data) disks
      # The boot disk has a sourceImage.
      assert len(node_disks) in (1, 2), f"Unexpected number of disks: {len(node_disks)}"
      boot_disk = next(d for d in node_disks if d.get('sourceImage'))
      data_disk = next((d for d in node_disks if not d.get('sourceImage')),
                       {'type': None, 'sizeGb': None})
      print(f"      boot: {_printable_disk(boot_disk['type'], boot_disk['sizeGb'])}, data: {_printable_disk(data_disk['type'], data_disk['sizeGb'])}")


def print_cluster_metadata(cluster_json):

  # Parse the selfLink:
  #   https://container.googleapis.com/v1/projects/<proj>/zones/<zone>/clusters/<name>"
  # into:
  #   (project, zone, name)
  cluster_elements = re.match(r'https://[^/]+/[^/]+/projects/([^/]+)/zones/([^/]+)/clusters/([^/]+)',
                              cluster_json['selfLink']).groups()

  # Parse the createTime ('2020-07-07T21:33:02+00:00')
  create_time = datetime.datetime.fromisoformat(cluster_json['createTime'])

  # Get the status
  status = cluster_json['status']

  print(f"Cluster: {cluster_elements}")
  print(f"  Created: {create_time}, Status: {status}")


def _check_found(ret, output):
  # Return False if a 404 (not found) is detected.
  # Error out if any other error is detected.
  # Otherwise return True.

  if ret:
    for s404 in ('ResponseError: code=404', 'HTTPError 404'):
      if s404 in output:
        return False

    gen_util.err_exit(ret, [output, f"Exit code: {ret}"])

  return True


def describe_cluster(config):
  print(f"Getting {config['name']} cluster information from GKE...")
  ret, output = k8_util.describe_cluster(config)
  if _check_found(ret, output):
    return json.loads(output)

  return None


def _describe_managed_instance_group(uri):
  ret, output = k8_util.describe_managed_instance_group(uri)
  if _check_found(ret, output):
    return json.loads(output)

  return None


def get_node_pool_details(config, cluster, pool_name):

  # Get the node pool information from the cluster details
  pool = next((p for p in cluster['nodePools'] if p['name'] == pool_name), None)
  if not pool:
    return None, None, []

  # Get the managed instance group information from GCE
  print(f"Getting {pool_name} managed instance information from GCE...")
  mig = _describe_managed_instance_group(pool['instanceGroupUrls'][0])
  if not mig:
    return pool, mig, []

  # Get the node information from kubernetes
  print(f"Getting {pool_name} node pool information from kubernetes...")
  ret, nodes = k8_util.kubectl_command(config, f"""\
    get nodes -l cloud.google.com/gke-nodepool={pool_name} --output=json
    """, emit_command=False, exit_on_error=False)
  if ret:
    return pool, mig, []
  else:
    return pool, mig, json.loads(nodes)['items']


def get_all_disks(config):
  project = config['project']
  zone = config['zone']

  print(f"Getting {project}/{zone} disk information from GCE...")
  return json.loads(k8_util.get_disks(project, zone))


def _get_disks_for_node(node, disks):
  node_disks = []
  for disk in disks:
    # Assume (safely) that a disks users must be in the same project and zone
    # (trim the full path .../projects/.../zones/... to just the name)
    disk_vms = set([os.path.basename(vm) for vm in disk.get('users', [])])

    if node['metadata']['name'] in disk_vms:
      node_disks.append(disk)

  return node_disks

def get_node_pool_disks(all_disks, nodes):
  if not nodes:
    return []

  # We take a short cut in not explicitly looking up the VMs in the
  # managed instance group - assume the node names are the same.
  node_pool_vms = set([n['metadata']['name'] for n in nodes])

  node_pool_disks = []
  for disk in all_disks:
    # Assume (safely) that a disks users must be in the same project and zone
    # (trim the full path .../projects/.../zones/... to just the name)
    disk_vms = set([os.path.basename(vm) for vm in disk.get('users', [])])

    if disk_vms.intersection(node_pool_vms):
      node_pool_disks.append(disk)

  return node_pool_disks

def get_all_pods(config):
  print(f"Getting pod information from kubernetes...")
  ret, pods = k8_util.kubectl_command(config, f"""\
    get pods --all-namespaces --output json
    """, emit_command=False, exit_on_error=False)

  if ret:
    return []
  else:
    return json.loads(pods)['items']


def get_node_pool_pod_details(all_pods, nodes):
  if not nodes:
    return []

  # Pods know about the node they are on, but they don't know what node pool
  # they belong to. So we get all pods and then filter output.
  # In the future, we might want to cut down on the information returned.
  node_names = [n['metadata']['name'] for n in nodes]

  return [pod for pod in all_pods if pod.get('spec', {}).get('nodeName') in node_names]


if __name__ == '__main__':
  pass
