# docker_util.py
#
# Utility functions for interacting with Docker
# to pull images from dockerhub and into gcr.
# 
# This script assumes:
# 1) docker is installed
# 2) The container registry API is enabled
# 3) `gcloud auth configure-docker` has been run.

import gen_util
import os


def pull_image(docker_image_path):

  command = f"docker pull {docker_image_path}"
  gen_util.run_command(command)


def tag_image(docker_image_path, cluster_config):

  gcr_image_path = get_gcr_image_path(docker_image_path, cluster_config)
  command = f"docker tag {docker_image_path} {gcr_image_path}"
  gen_util.run_command(command)


def push_image(docker_image_path, cluster_config):

  gcr_image_path = get_gcr_image_path(docker_image_path, cluster_config)
  command = f"docker push {gcr_image_path}"
  gen_util.run_command(command)


def get_image_name(docker_image_path, cluster_config):
  
  if 'elasticsearch' in docker_image_path:
    # elasticsearch image required to be under a path named 'elasticsearch'
    return f'elasticsearch/{os.path.basename(docker_image_path)}'
  return os.path.basename(docker_image_path)


def get_gcr_image_path(docker_image_path, cluster_config):
  
  image_name = get_image_name(docker_image_path, cluster_config)
  project = cluster_config['project']
  return f'gcr.io/{project}/{image_name}'


def format_all_in_one_yaml(full_image_path, cluster_config):
  # Prepare the elasticsearch operators

  # Read up the template
  with open('templates/all-in-one-template.yaml') as f:
    all_in_one_template = f.read()

  # Format the template with the config values
  all_in_one_config = all_in_one_template.format(ECK_OPERATOR_IMAGE=get_gcr_image_path(full_image_path, cluster_config))

  # Write the results to the deployment directory
  gen_util.write_all_in_one_file(cluster_config, all_in_one_config)


def prepare_image(full_image_path, cluster_config):
  # Given a dockerhub image, pull it, tag it,
  # and push it into gcr.io
  
  pull_image(full_image_path)
  tag_image(full_image_path, cluster_config)
  push_image(full_image_path, cluster_config)


if __name__ == '__main__':
  pass
