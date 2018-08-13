"""Indexes GCS directories."""

import argparse
import csv
import jsmin
import json
import logging
import os
import re

from google.cloud import storage

from indexer_util import indexer_util

# Log to stderr.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(filename)10s:%(lineno)s %(levelname)s %(message)s',
    datefmt='%Y%m%d%H:%M:%S')
logger = logging.getLogger('indexer.gcs')

ES_TIMEOUT_SEC = 20
FILE_TYPES = ['bam', 'vcf', 'fastq', 'cram']


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


def _append_to_file_sets(file_sets, primary_key, file_type, path):
    if primary_key not in file_sets:
        file_sets[primary_key] = {}
    if file_type not in file_sets[primary_key]:
        file_sets[primary_key][file_type] = {'files': []}
    file_sets[primary_key][file_type]['files'].append(path)


def index_gcs_files(es, index_name, gcs_pattern):
    logger.info('Processing %s' % gcs_pattern)

    # Input gcs_pattern looks like
    # gs://genomics-public-data/1000-genomes/bam/PRIMARY_KEY.
    trimmed_gcs_pattern = gcs_pattern.replace('gs://', '')
    # bucket_str looks like genomics-public-data
    bucket_str = trimmed_gcs_pattern.split('/')[0]
    # prefix looks like 1000-genomes/bam/
    prefix = trimmed_gcs_pattern.split('/', 1)[1]
    prefix = prefix[:prefix.index('PRIMARY_KEY')]

    logger.info('Retrieving objects from bucket %s with prefix %s.' %
                (bucket_str, prefix))
    bucket = storage.Client(project=None).bucket(bucket_str)
    objects = bucket.list_blobs(prefix=prefix)
    regex = re.compile(gcs_pattern.replace('PRIMARY_KEY', '(\w+)'))

    # Group each object by primary key and file type, e.g.
    # {
    #   'PRIMARY_KEY1' : {
    #       'bam': {
    #           'count': 2,
    #           'files': ['gs://b/file1.bam', 'gs://b/file2.bam'],
    #       'vcf', {...}
    #   }, ...
    # }
    file_sets = {}
    for obj in objects:
        path = 'gs://%s/%s' % (bucket_str, obj.name)
        match = re.match(regex, path)
        if not match:
            continue
        primary_key = match.group(1)
        file_type = ''
        for t in FILE_TYPES:
            if t in path:
                file_type = t
        if not file_type:
            continue
        _append_to_file_sets(file_sets, primary_key, file_type, path)

    indexer_util.bulk_index(es, index_name, file_sets.iteritems())


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
        index_gcs_files(es, index_name, gcs_pattern)


if __name__ == '__main__':
    main()
