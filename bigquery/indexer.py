"""Loads BigQuery table into Elasticsearch.

Note: Elasticsearch index is deleted before indexing.
"""

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
import pandas as pd

from indexer_util import indexer_util

# Log to stderr.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(filename)10s:%(lineno)s %(levelname)s %(message)s',
    datefmt='%Y%m%d%H:%M:%S')
logger = logging.getLogger('indexer.bigquery')

ES_TIMEOUT_SEC = 20


# Copied from https://stackoverflow.com/a/45392259
def environ_or_required(key):
    if os.environ.get(key):
        return {'default': os.environ.get(key)}
    else:
        return {'required': True}


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
    parser.add_argument(
        '--billing_project_id',
        type=str,
        help=
        'The project that will be billed for querying BigQuery tables. The account running this script must have bigquery.jobs.create permission on this project.',
        **environ_or_required('BILLING_PROJECT_ID'))
    return parser.parse_args()


def index_facet_field(es, index_name, primary_key, project_id, dataset_id,
                      table_name, field_name, readable_field_name,
                      billing_project_id):
    """Indexes a facet field.

  I couldn't find an easy way to import BigQuery -> Elasticsearch. So instead:

  - BigQuery -> pandas dataframe
  - Convert datafrom to dict
  - dict -> Elasticsearch

  Args:
    es: Elasticsearch object.
    index_name: Name of Elasticsearch index.
    primary_key: Name of primary key field.
    project_id: BigQuery project ID.
    dataset_id: BigQuery dataset ID.
    table_name: BigQuery table name.
    field_name: BigQuery field name.
    readable_field_name: Field name for index and Data Explorer UI
    billing_project_id: GCP project ID to bill
  """
    start_time = time.time()
    logger.info('Indexing %s.%s.%s.%s.' % (project_id, dataset_id, table_name,
                                           field_name))
    df = pd.read_gbq(
        'SELECT * FROM `%s.%s.%s`' % (project_id, dataset_id, table_name),
        project_id=billing_project_id,
        dialect='standard')
    elapsed_time = time.time() - start_time
    elapsed_time_str = time.strftime('%Hh:%Mm:%Ss', time.gmtime(elapsed_time))
    logger.info('BigQuery -> pandas took %s' % elapsed_time_str)
    logger.info('%s has %d rows' % (table_name, len(df)))

    start_time = time.time()
    documents = df.to_dict(orient='records')
    # Use generator so we can index large tables without having to load into
    # memory.
    k = (
        {
            '_op_type': 'update',
            '_index': index_name,
            # type will go away in future versions of Elasticsearch. Just use any string
            # here.
            '_type': 'type',
            '_id': row[primary_key],
            'doc': {
                readable_field_name: row[field_name]
            },
            'doc_as_upsert': True
        } for _, row in df.iterrows())

    bulk(es, k)
    elapsed_time = time.time() - start_time
    elapsed_time_str = time.strftime("%Hh:%Mm:%Ss", time.gmtime(elapsed_time))
    logger.info('pandas -> ElasticSearch index took %s' % elapsed_time_str)


def main():
    args = parse_args()

    json_path = os.path.join(args.dataset_config_dir, 'dataset.json')
    dataset_config = indexer_util.open_and_return_json(json_path)
    index_name = indexer_util.convert_to_index_name(dataset_config['name'])
    primary_key = dataset_config['primary_key']

    es = indexer_util.init_elasticsearch(args.elasticsearch_url, index_name)

    f = open(os.path.join(args.dataset_config_dir, 'facet_fields.csv'))
    # Remove comments using jsmin.
    csv_str = jsmin.jsmin(f.read())
    rows = csv.DictReader(iter(csv_str.splitlines()), skipinitialspace=True)
    for row in rows:
        print('row: %s' % row)
        index_facet_field(es, index_name, primary_key, row['project_id'],
                          row['dataset_id'], row['table_name'],
                          row['field_name'], row['readable_field_name'],
                          args.billing_project_id)
    f.close()


if __name__ == '__main__':
    main()
