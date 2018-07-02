"""Indexes GCS directories."""

import argparse
import csv
import jsmin
import json
import logging
import os

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


def index_gcs_pattern(gcs_pattern):
    # Input gcs_pattern looks like
    # gs://genomics-public-data/platinum-genomes/bam/PRIMARY_KEY_

    logger.info('Processing %s.' % gcs_pattern)

    trimmed_gcs_pattern = gcs_pattern.replace('gs://', '')

    # bucket_str looks like genomics-public-data
    bucket_str = trimmed_gcs_pattern.split('/')[0]

    prefix = trimmed_gcs_pattern.split('/', 1)[1]
    # prefix looks like platinum-genomes/bam/
    prefix = prefix[:prefix.index('PRIMARY_KEY')]

    logger.info('Retrieving objects from bucket %s with prefix %s.' %
                (bucket_str, prefix))
    bucket = storage.Client(project=None).bucket(bucket_str)
    objects = bucket.list_blobs(prefix=prefix)

    regex = re.compile(gcs_pattern.replace('PRIMARY_KEY', '(\w+)'))

    for obj in objects:
        obj_path = 'gs://%s/%s' % (bucket_str, obj.name)
        match = re.match(regex, obj_path)
        if match:
            primary_key = match.group(1)
            print(
                'Identified primary key %s from %s' % (primary_key, obj_path))
        else:
            raise ValueError('Could not find primary key in %s' % obj_path)


def main():
    args = parse_args()

    # Read dataset config files
    index_name = indexer_util.get_index_name(args.dataset_config_dir)
    gcs_config_path = os.path.join(args.dataset_config_dir, 'gcs.json')
    gcs_patterns = indexer_util.parse_json_file(gcs_config_path)[
        'gcs_patterns']

    es = indexer_util.maybe_create_elasticsearch_index(args.elasticsearch_url,
                                                       index_name)

    for gcs_pattern in gcs_patterns:
        index_gcs_pattern(gcs_pattern)


if __name__ == '__main__':
    main()
