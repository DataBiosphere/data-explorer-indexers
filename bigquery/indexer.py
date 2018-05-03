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
from elasticsearch.helpers import bulk
import pandas as pd


# Log to stderr.
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(filename)10s:%(lineno)s %(levelname)s %(message)s',
                    datefmt='%Y%m%d%H:%M:%S')
logger = logging.getLogger('indexer.bigquery')


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--elasticsearch_url',
        type=str,
        help='Elasticsearch url. Must start with http://',
        default='http://localhost:9200')
    parser.add_argument(
        '--config_dir',
        type=str,
        help='Directory containing config files. Can be relative or absolute.',
        default='config/platinum_genomes')
    return parser.parse_args()


def open_and_return_json(file_path):
    """Opens and returns JSON contents.

    Args:
      file_path: Relative path of JSON file.

    Returns:
      Parsed JSON.
    """
    with open(file_path,'r') as f:
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
        s = s.replace(char, '_');
    s = s.lower()
    # Remove leading underscore.
    if s.find('_', 0, 1) == 0:
        s = s.lstrip('_')
    print('Index name: %s' % s)
    return s


def init_elasticsearch(elasticsearch_url, index_name):
    es = Elasticsearch([elasticsearch_url])
    logger.info('Deleting and recreating %s index.' % index_name)
    try:
        es.indices.delete(index=index_name)
    except Exception:
        pass
    es.indices.create(index=index_name,body={})
    return es


def index_facet_field(es, index_name, primary_key, project_id, dataset_id,
                      table_name, field_name, readable_field_name):
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
    """
    start_time = time.time()
    logger.info('Indexing %s.%s.%s.%s.' % (project_id, dataset_id, table_name, field_name))
    df = pd.read_gbq(
        'SELECT * FROM `%s.%s.%s`' % (project_id, dataset_id, table_name),
        project_id=project_id, private_key=os.environ['GOOGLE_APPLICATION_CREDENTIALS'], dialect='standard')
    elapsed_time = time.time() - start_time
    elapsed_time_str = time.strftime('%Hh:%Mm:%Ss', time.gmtime(elapsed_time))
    logger.info('BigQuery -> pandas took %s' % elapsed_time_str)
    logger.info('%s has %d rows' % (table_name, len(df)))

    start_time = time.time()
    documents = df.to_dict(orient='records')
    # Use generator so we can index large tables without having to load into
    # memory.
    k = ({
        '_op_type': 'update',
        '_index': index_name,
        # type will go away in future versions of Elasticsearch. Just use any string
        # here.
        '_type' : 'type',
        '_id'   : row[primary_key],
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

    json_path = os.path.join(args.config_dir, 'dataset.json')
    dataset_config = open_and_return_json(json_path)
    index_name = convert_to_index_name(dataset_config['name'])
    primary_key = dataset_config['primary_key']

    es = init_elasticsearch(args.elasticsearch_url, index_name)

    f = open(os.path.join(args.config_dir, 'facet_fields.csv'))
    # Remove comments using jsmin.
    csv_str = jsmin.jsmin(f.read())
    rows = csv.DictReader(iter(csv_str.splitlines()), skipinitialspace=True)
    for row in rows:
        print('row: %s' % row)
        index_facet_field(es, index_name, primary_key, row['project_id'],
                          row['dataset_id'], row['table_name'], row['field_name'], row['readable_field_name'])
    f.close()

if __name__ == '__main__':
    try:
        main()
    except Exception:
        pass
