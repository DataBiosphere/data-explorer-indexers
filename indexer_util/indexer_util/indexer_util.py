"""Utilities for Data Explorer indexers"""

import csv
import jsmin
import json
import logging
import os
import time

from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ConnectionError

# Log to stderr.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(filename)10s:%(lineno)s %(levelname)s %(message)s',
    datefmt='%Y%m%d%H:%M:%S')
logger = logging.getLogger('indexer.util')

ES_TIMEOUT_SEC = 20


def parse_json_file(json_path):
    """Opens and returns JSON contents.

  Args:
    json_path: Relative or absolute path of JSON file

  Returns:
    Parsed JSON
  """
    with open(json_path, 'r') as f:
        # Remove comments using jsmin, as recommended by JSON creator
        # (https://plus.google.com/+DouglasCrockfordEsq/posts/RK8qyGVaGSr).
        jsonDict = json.loads(jsmin.jsmin(f.read()))
        return jsonDict


# Keep in sync with convert_to_index_name() in data-explorer repo.
def _convert_to_index_name(s):
    """Converts a string to an Elasticsearch index name."""
    # For Elasticsearch index name restrictions, see
    # https://github.com/DataBiosphere/data-explorer-indexers/issues/5#issue-308168951
    # Elasticsearch allows single quote in index names. However, they cause other
    # problems. For example,
    # "curl -XDELETE http://localhost:9200/nurse's_health_study" doesn't work.
    # So also remove single quotes.
    prohibited_chars = [' ', '"', '*', '\\', '<', '|', ',', '>', '/', '?', '\'']
    for char in prohibited_chars:
        s = s.replace(char, '_')
    s = s.lower()
    # Remove leading underscore.
    if s.find('_', 0, 1) == 0:
        s = s.lstrip('_')
    print('Index name: %s' % s)
    return s


def get_index_name(dataset_config_dir):
    json_path = os.path.join(dataset_config_dir, 'dataset.json')
    dataset_name = parse_json_file(json_path)['name']
    return _convert_to_index_name(dataset_name)


def _wait_elasticsearch_healthy(es):
    """Waits for Elasticsearch to be healthy.

    Args:
        es: An Elasticsearch instance.
    """
    # Don't print NewConnectionError's while we're waiting for Elasticsearch
    # to come up.
    start = time.time()
    logging.getLogger("elasticsearch").setLevel(logging.ERROR)
    for _ in range(0, ES_TIMEOUT_SEC):
        try:
            es.cluster.health(wait_for_status='yellow')
            print('Elasticsearch took %d seconds to come up.' %
                  (time.time() - start))
            break
        except ConnectionError:
            print('Elasticsearch not up yet, will try again.')
            time.sleep(1)
    else:
        raise EnvironmentError("Elasticsearch failed to start.")
    logging.getLogger("elasticsearch").setLevel(logging.INFO)


def maybe_create_elasticsearch_index(elasticsearch_url, index_name):
    """Creates Elasticsearchindex if it doesn't already exist."""
    es = Elasticsearch([elasticsearch_url])

    _wait_elasticsearch_healthy(es)

    if es.indices.exists(index=index_name):
        logger.info(
            'Using existing %s index at %s.' % (index_name, elasticsearch_url))
    else:
        logger.info(
            'Creating %s index at %s.' % (index_name, elasticsearch_url))
        es.indices.create(index=index_name, body={})
    return es
