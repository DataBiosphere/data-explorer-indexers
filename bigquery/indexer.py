"""Loads BigQuery table into Elasticsearch."""

import csv
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


def open_and_return_json(file_path):
  """Opens and returns JSON contents.

  Args:
    file_path: Relative path of JSON file.

  Returns:
    Parsed JSON.
  """
  with open(file_path,'r') as f:
    # Remove JSON comments.
    jsonDict = json.loads('\n'.join([row for row in f.readlines() if len(row.split('//')) == 1]))
  return jsonDict


def init_elasticsearch(index_name):
  es = Elasticsearch(['http://localhost:9200'], timeout=600)
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
      project_id=project_id, dialect='standard')
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
  dataset_config = open_and_return_json('config/dataset.json')
  index_name = dataset_config['name']
  primary_key = dataset_config['primary_key']

  es = init_elasticsearch(index_name)

  f = open('config/facet_fields.csv')
  rows = csv.DictReader(filter(lambda row: row[0]!='#', f),
      # field_name is BigQuery field name.
      # readable_field_name is used in index and Data Explorer UI.
      fieldnames=['project_id', 'dataset_id', 'table_name', 'field_name', 'readable_field_name'],
      skipinitialspace=True)
  for row in rows:
    print(row)
    index_facet_field(es, index_name, primary_key, row['project_id'],
        row['dataset_id'], row['table_name'], row['field_name'], row['readable_field_name'])
  f.close()

if __name__ == '__main__':
  main()
