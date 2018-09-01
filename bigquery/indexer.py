"""Indexes BigQuery tables."""

import argparse
import logging
import os
import time

from google.cloud import bigquery
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


def get_nested_mappings(schema, prefix=None):
    nested = {}
    for field in schema:
        if field.mode == 'REPEATED' and field.field_type == 'RECORD':
            name = '%s.%s' % (prefix, field.name) if prefix else field.name
            nested[name] = {"type": "nested"}
            inner_nested = get_nested_mappings(field.fields)
            if inner_nested:
                nested[name]['properties'] = inner_nested
    return nested if nested else None


def create_nested_mappings(es, index_name, table_name, billing_project_id):
    project, dataset, table = table_name.split('.')
    bq = bigquery.Client(project=billing_project_id)
    table = bq.get_table(bq.dataset(dataset, project=project).table(table))
    nested = get_nested_mappings(table.schema, table_name)

    if nested:
        logger.info('Adding neseted mappings to %s.' % index_name)
        es.indices.put_mapping(
            doc_type='type', index=index_name, body={'properties': nested})


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
    create_nested_mappings(es, index_name, table_name, billing_project_id)

    start_time = time.time()
    logger.info('Indexing %s.' % table_name)
    # There is no easy way to import BigQuery -> Elasticsearch. Instead:
    # BigQuery table -> pandas dataframe -> dict -> Elasticsearch
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

    def docs_by_id(df):
        for _, row in df.iterrows():
            # Remove nan's as described in
            # https://stackoverflow.com/questions/40363926/how-do-i-convert-my-dataframe-into-a-dictionary-while-ignoring-the-nan-values
            # Elasticsearch crashes when indexing nan's.
            row_dict = row.dropna().to_dict()
            row_dict = {
                table_name + '.' + k: v
                for k, v in row_dict.iteritems()
            }
            yield row[primary_key], row_dict

    indexer_util.bulk_index(es, index_name, docs_by_id(df))
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
