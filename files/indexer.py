"""Indexes genomic files."""

import argparse
import csv
import jsmin
import json
import logging
import os
import re

from google.cloud import storage

from indexer_util import indexer_util

PARTICIPANT_ID_COL = 'participant_id'
SAMPLE_ID_COL = 'sample_id'
DELIMITER = '\t'
FILE_TYPES = ['bam', 'cram', 'fastq', 'vcf']

# Log to stderr.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(filename)10s:%(lineno)s %(levelname)s %(message)s',
    datefmt='%Y%m%d%H:%M:%S')
logger = logging.getLogger('indexer.files')


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


def read_file_lines(path, dataset_config_dir):
    if 'gs://' in path:
        trimmed_path = path.replace('gs://', '')
        bucket_str = trimmed_path.split('/')[0]
        obj_str = trimmed_path.split('/', 1)[1]

        client = storage.Client(project=None)
        bucket = client.bucket(bucket_str)
        obj = bucket.get_blob(obj_str)
        if not obj:
            raise ValueError('Manifest file [%s/%s] does not exist.' %
                             (bucket_str, obj_str))
        return iter(obj.download_as_string(client).split('\n'))
    else:
        full_path = os.path.join(dataset_config_dir, path)
        return open(full_path, 'r')


def index_file_manifest(es, index_name, path, dataset_config_dir):
    logger.info('Processing TSV manifest %s' % path)
    lines = read_file_lines(path, dataset_config_dir)

    # TODO(bryancrampton): Allow configuration of the number of header lines.
    header = []
    for col in csv.reader(iter([lines.next()]), delimiter=DELIMITER).next():
        header.append(col)

    if PARTICIPANT_ID_COL not in header or SAMPLE_ID_COL not in header:
        raise ValueError('%s and %s are required columns' %
                         (PARTICIPANT_ID_COL, SAMPLE_ID_COL))

    docs = {}
    for line in csv.reader(lines, delimiter='\t'):
        # Ignore blank lines.
        if len(line) == 0:
            continue

        idx = 0
        doc = {}
        participant_id = ''
        sample_id = ''
        file_types_map = {}
        for value in line:
            col_name = header[idx]
            if col_name == PARTICIPANT_ID_COL:
                participant_id = value
            else:
                doc[col_name] = value
                # If this column contains a path for a known file type, mark the
                # helper column '_has_<FILE_TYPE>' as true.
                for file_type in FILE_TYPES:
                    if file_type in col:
                        doc['_has_%s' % file_type] = True
            idx += 1

        if participant_id not in docs:
            docs[participant_id] = {'samples': []}
        docs[participant_id]['samples'].append(doc)

    indexer_util.bulk_index(es, index_name, docs.iteritems())


def main():
    args = parse_args()

    # Read dataset config files
    index_name = indexer_util.get_index_name(args.dataset_config_dir)
    path = os.path.join(args.dataset_config_dir, 'files.json')
    manifest_files = indexer_util.parse_json_file(path)['manifest_files']

    es = indexer_util.maybe_create_elasticsearch_index(args.elasticsearch_url,
                                                       index_name)
    # Add 'samples' as a nested index to prevent array flattening of objects:
    # https://www.elastic.co/guide/en/elasticsearch/reference/6.3/nested.html.
    es.indices.put_mapping(
        doc_type='type',
        index=index_name,
        body={"properties": {
            "samples": {
                "type": "nested"
            }
        }})

    for path in manifest_files:
        index_file_manifest(es, index_name, path, args.dataset_config_dir)


if __name__ == '__main__':
    main()
