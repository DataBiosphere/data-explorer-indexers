"""Indexes a files from a manifest."""

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
logger = logging.getLogger('indexer.files')

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


def index_file_manifest(es, index_name, manifest):
    path = manifest['path']
    delimiter = str(manifest['delimiter'])
    primary_key = manifest['primary_key']
    logger.info('Processing CSV manifest %s' % path)

    # TODO(bryancrampton): Make this non gcs-specific.
    trimmed_path = path.replace('gs://', '')
    bucket_str = trimmed_path.split('/')[0]
    obj_str = trimmed_path.split('/', 1)[1]

    client = storage.Client(project=None)
    bucket = client.bucket(bucket_str)
    obj = bucket.get_blob(obj_str)
    if not obj:
        raise ValueError('Manifest file [%s/%s] does not exist.' % (bucket_str, obj_str))

    file_str = obj.download_as_string(client)
    lines = iter(file_str.split('\n'))

    # TODO(bryancrampton): Allow configuration of the number of header lines.
    header = []
    for col in csv.reader(iter([lines.next()]), delimiter=delimiter).next():
        header.append(col)

    docs = {}
    for line in csv.reader(lines, delimiter=','):
        # Ignore blank lines.
        if len(line) == 0:
            continue

        idx = 0
        id = ''
        f = {}
        for col in line:
            col_name = header[idx]
            if col_name == primary_key:
                id = col
            else:
                f[col_name] = col
            idx += 1

        if not id:
            raise ValueError(
                'No primary key found for CSV row: %s' % line)
        if id not in docs:
            docs[id] = {'files': []}
        docs[id]['files'].append(f)

    indexer_util.bulk_index(es, index_name, docs.iteritems())


def main():
    args = parse_args()

    # Read dataset config files
    index_name = indexer_util.get_index_name(args.dataset_config_dir)
    gcs_config_path = os.path.join(args.dataset_config_dir, 'files.json')
    manifests = indexer_util.parse_json_file(gcs_config_path)['manifest_files']

    es = indexer_util.maybe_create_elasticsearch_index(args.elasticsearch_url,
                                                       index_name)

    for manifest in manifests:
        index_file_manifest(es, index_name, manifest)


if __name__ == '__main__':
    main()
