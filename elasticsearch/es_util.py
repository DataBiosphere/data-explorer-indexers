import docker_util
import gen_util
import k8_util

# es_util.py
#
# Utility functions for interacting with Google Kubernetes Engine
# to configure Elasticsearch.


def prepare_cluster(config, runtime):

  # Prep the eck-operator image
  docker_util.prepare_image("docker.elastic.co/eck/eck-operator:1.1.2", config)
  docker_util.format_all_in_one_yaml(
    "docker.elastic.co/eck/eck-operator:1.1.2", config)

  # Prep the elasticsearch image
  runtime["elasticsearch_image"] = docker_util.get_gcr_image_path(
    "docker.elastic.co/elasticsearch/elasticsearch:7.7.1", config)
  docker_util.prepare_image(
    "docker.elastic.co/elasticsearch/elasticsearch:7.7.1", config)

  all_in_one_config_file = gen_util.get_all_in_one_config_file(config)
  k8_util.kubectl_run_command(config, f"apply -f {all_in_one_config_file}")


def apply_cluster_yaml(config):

  config_file = gen_util.get_es_config_file(config)
  k8_util.kubectl_run_command(config, f"apply -f {config_file}")


def delete_cluster(config):

  config_file = gen_util.get_es_config_file(config)
  k8_util.kubectl_run_command(config, f"delete -f {config_file}")


if __name__ == '__main__':
  pass
