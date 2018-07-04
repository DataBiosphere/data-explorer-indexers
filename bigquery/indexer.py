"""Indexes BigQuery tables."""

import argparse
import logging
import os
import time

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


def index_table(es, index_name, primary_key, table_name, billing_project_id):
    """Indexes a BigQuery table.

    Args:
        es: Elasticsearch object.
        index_name: Name of Elasticsearch index.
        primary_key: Name of primary key field.
        table_name: Fully-qualified table name:
            <project id>.<dataset id>.<table name>
        billing_project_id: GCP project ID to bill for reading table
    """
    # I couldn't find an easy way to import BigQuery -> Elasticsearch. Instead:
    #
    #   BigQuery table -> pandas dataframe -> dict -> Elasticsearch

    start_time = time.time()
    logger.info('Indexing %s.' % table_name)
    df = pd.read_gbq(
        'SELECT * FROM `%s`' % table_name,
        project_id=billing_project_id,
        dialect='standard')
    elapsed_time = time.time() - start_time
    elapsed_time_str = time.strftime('%Hh:%Mm:%Ss', time.gmtime(elapsed_time))
    logger.info('BigQuery -> pandas took %s' % elapsed_time_str)
    logger.info('%s has %d rows' % (table_name, len(df)))

    if not primary_key in df.columns:
        raise ValueError('Primary key %s not found in BigQuery table %s' %
                         (primary_key, table_name))

    start_time = time.time()
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
            # Remove nan's as described in
            # https://stackoverflow.com/questions/40363926/how-do-i-convert-my-dataframe-into-a-dictionary-while-ignoring-the-nan-values
            # Elasticsearch crashes when indexing nan's.
            'doc': row.dropna().to_dict(),
            'doc_as_upsert': True
        } for col, row in df.iterrows())

    bulk(es, k)
    elapsed_time = time.time() - start_time
    elapsed_time_str = time.strftime("%Hh:%Mm:%Ss", time.gmtime(elapsed_time))
    logger.info('pandas -> ElasticSearch index took %s' % elapsed_time_str)


def main():
    args = parse_args()

    # Read dataset config files
    index_name = indexer_util.get_index_name(args.dataset_config_dir)
    config_path = os.path.join(args.dataset_config_dir, 'bigquery.json')
    bigquery_config = indexer_util.parse_json_file(config_path)
    primary_key = bigquery_config['primary_key']
    table_names = bigquery_config['table_names']

    es = indexer_util.maybe_create_elasticsearch_index(args.elasticsearch_url,
                                                       index_name)

    for table_name in table_names:
        index_table(es, index_name, primary_key, table_name,
                    args.billing_project_id)


if __name__ == '__main__':
    main()
