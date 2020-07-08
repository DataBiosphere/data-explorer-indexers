import gen_util

# k8_util.py
#
# Utility functions for interacting with Google Kubernetes Engine, including
# cluster creation and deletion, along with configuration deployment.


def create_cluster(cluster_config):

  project = cluster_config['project']
  zone = cluster_config['zone']
  cluster_name = cluster_config['name']

  # This command was initially generated by the Cloud Console by specifying
  # a cluster name, zone, and custom node pool configs.
  #
  # Removed from the command:
  #   --cluster-version "1.14.10-gke.36" \
  #   --image-type "COS" \
  #
  # Changed:
  #   --disk-size from 100 to 50
  #     (assume ES template will have an explicit volume claim)
  #
  # More could probably be removed (need to check the defaults).

  command=f"""
    gcloud beta container clusters create "{cluster_name}" \
      --project "{project}" \
      --zone "{zone}" \
      --no-enable-basic-auth \
      --machine-type "n1-standard-1" \
      --disk-type "pd-standard" \
      --disk-size "50" \
      --metadata disable-legacy-endpoints=true \
      --scopes "https://www.googleapis.com/auth/devstorage.read_only","https://www.googleapis.com/auth/logging.write","https://www.googleapis.com/auth/monitoring","https://www.googleapis.com/auth/servicecontrol","https://www.googleapis.com/auth/service.management.readonly","https://www.googleapis.com/auth/trace.append" \
      --enable-stackdriver-kubernetes \
      --enable-ip-alias \
      --network "projects/{project}/global/networks/default" \
      --subnetwork "projects/{project}/regions/us-central1/subnetworks/default" \
      --default-max-pods-per-node "110" \
      --enable-autoscaling \
      --num-nodes "1" \
      --max-nodes "1" \
      --no-enable-master-authorized-networks \
      --addons HorizontalPodAutoscaling,HttpLoadBalancing \
      --enable-autoupgrade \
      --enable-autorepair \
      --max-surge-upgrade 1 \
      --max-unavailable-upgrade 0 \
      --enable-private-nodes \
      --master-ipv4-cidr 172.16.0.16/28
  """

  gen_util.run_command(command)


def create_node_pool(cluster_config, node_pool_config):

  project = cluster_config['project']
  zone = cluster_config['zone']
  cluster_name = cluster_config['name']

  node_pool_name = node_pool_config['name']
  node_count = node_pool_config['count']
  machine_type = node_pool_config['machine-type']
  node_type = node_pool_config['node-type']

  command = f"""
    gcloud beta container node-pools create "{node_pool_name}" \
      --project "{project}" \
      --zone "{zone}" \
      --cluster "{cluster_name}" \
      --machine-type "{machine_type}" \
      --disk-type "pd-standard" \
      --disk-size "50" \
      --node-labels node-type={node_type} \
      --metadata disable-legacy-endpoints=true \
      --scopes "https://www.googleapis.com/auth/devstorage.read_only","https://www.googleapis.com/auth/logging.write","https://www.googleapis.com/auth/monitoring","https://www.googleapis.com/auth/servicecontrol","https://www.googleapis.com/auth/service.management.readonly","https://www.googleapis.com/auth/trace.append" \
      --enable-autoscaling \
      --num-nodes "{node_count}" \
      --min-nodes "{node_count}" \
      --max-nodes "{node_count}" \
      --enable-autoupgrade \
      --enable-autorepair \
      --max-surge-upgrade 1 \
      --max-unavailable-upgrade 0 \
  """

  gen_util.run_command(command)


def delete_cluster(cluster_config):

  cluster_name = cluster_config['name']
  project = cluster_config['project']
  zone = cluster_config['zone']

  command=f"""
    gcloud beta container clusters delete "{cluster_name}" \
      --project "{project}" \
      --zone "{zone}"
  """

  gen_util.run_command(command)


def delete_node_pool(cluster_config, node_pool_config, force):

  project = cluster_config['project']
  zone = cluster_config['zone']
  cluster_name = cluster_config['name']

  node_pool_name = node_pool_config['name']

  quiet = "--quiet" if force else ""

  command = f"""
    gcloud {quiet} container node-pools delete "{node_pool_name}" \
      --project "{project}" \
      --zone "{zone}" \
      --cluster "{cluster_name}"
  """

  gen_util.run_command(command)


def get_cluster_context(config):
  """Return the name of the kubeconfig cluster context"""

  # Did not find a way to look this up, but could be necessary for
  # different kubernetes providers.
  return f"gke_{config['project']}_{config['zone']}_{config['name']}"


def kubectl_run_command(config, command):
  context = get_cluster_context(config)

  command = f"kubectl --context {context} {command}"
  print(f"Running: {command}")
  gen_util.run_command(command)


def kubectl_command(config, command, exit_on_error=True):
  context = get_cluster_context(config)

  command = f"kubectl --context {context} {command}"
  print(f"Running: {command}")

  return gen_util.get_command_output(command, exit_on_error)


if __name__ == '__main__':
  pass
