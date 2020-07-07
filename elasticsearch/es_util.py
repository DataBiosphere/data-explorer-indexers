import gen_util
import k8_util

# es_util.py
#
# Utility functions for interacting with Google Kubernetes Engine
# to configure Elasticsearch.

def prepare_cluster(config):

  all_in_one_url = "https://download.elastic.co/downloads/eck/1.1.2/all-in-one.yaml"
  k8_util.kubectl_run_command(config, f"apply -f {all_in_one_url}")


def apply_cluster_yaml(config):

  config_file = gen_util.get_es_config_file(config)
  k8_util.kubectl_run_command(config, f"apply -f {config_file}")


def delete_cluster(config):

  config_file = gen_util.get_es_config_file(config)
  k8_util.kubectl_run_command(config, f"delete -f {config_file}")


if __name__ == '__main__':
  pass
