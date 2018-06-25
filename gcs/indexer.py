"""Indexes GCS directories."""

import argparse
import csv
import jsmin
import json
import logging
import os
import time

from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ConnectionError
from elasticsearch.helpers import bulk

from indexer_util import indexer_util

# Log to stderr.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(filename)10s:%(lineno)s %(levelname)s %(message)s',
    datefmt='%Y%m%d%H:%M:%S')
logger = logging.getLogger('indexer.gcs')

ES_TIMEOUT_SEC = 20


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--elasticsearch_url',
        type=str,
        help='Elasticsearch url. Must start with http://',
        default=os.environ.get('ELASTICSEARCH_URL'))
    parser.add_argument(
        '--dataset_config_dir',
        type=str,
        help='Directory containing config files. Can be relative or absolute.',
        default=os.environ.get('DATASET_CONFIG_DIR'))
    return parser.parse_args()


def main():
    args = parse_args()

    json_path = os.path.join(args.dataset_config_dir, 'dataset.json')
    dataset_config = indexer_util.open_and_return_json(json_path)
    index_name = indexer_util.convert_to_index_name(dataset_config['name'])

    es = indexer_util.maybe_create_elasticsearch_index(args.elasticsearch_url,
                                                       index_name)


if __name__ == '__main__':
    main()
