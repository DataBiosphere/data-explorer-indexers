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


def open_and_return_json(file_path):
    """Opens and returns JSON contents.

  Args:
    file_path: Relative path of JSON file.

  Returns:
    Parsed JSON.
  """
    with open(file_path, 'r') as f:
        # Remove comments using jsmin, as recommended by JSON creator
        # (https://plus.google.com/+DouglasCrockfordEsq/posts/RK8qyGVaGSr).
        jsonDict = json.loads(jsmin.jsmin(f.read()))
        return jsonDict


# Keep in sync with convert_to_index_name() in data-explorer repo.
def convert_to_index_name(s):
    """Converts a string to an Elasticsearch index name."""
    # For Elasticsearch index name restrictions, see
    # https://github.com/DataBiosphere/data-explorer-indexers/issues/5#issue-308168951
    prohibited_chars = [' ', '"', '*', '\\', '<', '|', ',', '>', '/', '?']
    for char in prohibited_chars:
        s = s.replace(char, '_')
    s = s.lower()
    # Remove leading underscore.
    if s.find('_', 0, 1) == 0:
        s = s.lstrip('_')
    print('Index name: %s' % s)
    return s


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


def init_elasticsearch(elasticsearch_url, index_name):
    """Performs Elasticsearch initialization.

    Waits for Elasticsearch to be healthy, and creates index.

    Args:
        elasticsearch_url: Elasticsearch url
        index_name: Index name. For Elasticsearch index name restrictions, see
            https://github.com/DataBiosphere/data-explorer-indexers/issues/5#issue-308168951
    """
    es = Elasticsearch([elasticsearch_url])

    _wait_elasticsearch_healthy(es)

    logger.info('Deleting and recreating %s index.' % index_name)
    try:
        es.indices.delete(index=index_name)
    except Exception:
        pass
    es.indices.create(index=index_name, body={})
    return es
