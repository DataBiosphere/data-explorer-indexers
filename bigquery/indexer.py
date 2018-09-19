"""Indexes BigQuery tables."""

import argparse
import logging
import os
import time

from google.cloud import bigquery

from indexer_util import indexer_util

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(filename)10s:%(lineno)s %(levelname)s %(message)s',
    datefmt='%Y%m%d%H:%M:%S')
logger = logging.getLogger('indexer.bigquery')

UPDATE_SAMPLES_SCRIPT = """
if (!ctx._source.containsKey('samples')) {
   ctx._source.samples = [params.sample]
} else {
   // If this sample already exists, merge it with the new one.
   int removeIdx = -1;
   for (int i = 0; i < ctx._source.samples.size(); i++) {
      if (ctx._source.samples.get(i).get('%s').equals(params.sample.get('%s'))) {
         removeIdx = i;
      }
   }

   if (removeIdx >= 0) {
      Map merged = ctx._source.samples.remove(removeIdx);
      merged.putAll(params.sample);
      ctx._source.samples.add(merged);
   } else {
      ctx._source.samples.add(params.sample);
   }
}
"""


# Copied from https://stackoverflow.com/a/45392259
def _environ_or_required(key):
    if os.environ.get(key):
        return {'default': os.environ.get(key)}
    else:
        return {'required': True}


def _parse_args():
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
        **_environ_or_required('BILLING_PROJECT_ID'))
    return parser.parse_args()


def _get_nested_mappings(schema, prefix=None):
    # Find all repeated record type fields and create mappings for them
    # recursively.
    nested = {}
    for field in schema:
        if field.mode == 'REPEATED' and field.field_type == 'RECORD':
            name = '%s.%s' % (prefix, field.name) if prefix else field.name
            nested[name] = {"type": "nested"}
            inner_nested = _get_nested_mappings(field.fields)
            if inner_nested:
                nested[name]['properties'] = inner_nested
    return nested if nested else None


def _get_table_name(legacy_table_name):
    project_id, dataset_table_id = legacy_table_name.split(':')
    return project_id + '.' + dataset_table_id


def _create_nested_mappings(es, index_name, table, sample_id_col):
    # Create nested mappings for repeated record type BigQuery fields so that
    # queries will work correctly, see:
    # https://www.elastic.co/guide/en/elasticsearch/reference/6.4/nested.html#_how_arrays_of_objects_are_flattened
    nested = _get_nested_mappings(table.schema,
                                  _get_table_name(table.full_table_id))
    # If the table contains the sample ID column, add a nested samples mapping.
    if sample_id_col in [f.name for f in table.schema]:
        logger.info('Adding nested sample mapping to %s.' % index_name)
        sample_mapping = {'properties': {'samples': {'type': 'nested'}}}
        if nested:
            sample_mapping['properties']['samples']['properties'] = nested
        es.indices.put_mapping(
            doc_type='type', index=index_name, body=sample_mapping)
    elif nested:
        logger.info('Adding neseted mappings to %s.' % index_name)
        es.indices.put_mapping(
            doc_type='type', index=index_name, body={'properties': nested})


def _docs_by_id(df, table_name, participant_id_col):
    for _, row in df.iterrows():
        # Remove nan's as described in
        # https://stackoverflow.com/questions/40363926/how-do-i-convert-my-dataframe-into-a-dictionary-while-ignoring-the-nan-values
        # Elasticsearch crashes when indexing nan's.
        row_dict = row.dropna().to_dict()
        # Remove the participant_id_col since it is stored as document id.
        del row_dict[participant_id_col]
        row_dict = {table_name + '.' + k: v for k, v in row_dict.iteritems()}
        yield row[participant_id_col], row_dict


def _field_docs_by_id(table_name, fields):
    for field in fields:
        field_dict = {'name': field.name}
        if field.description:
            field_dict['description'] = field.description
        yield table_name + '.' + field.name, field_dict


def _sample_scripts_by_id(df, table_name, participant_id_col, sample_id_col,
                          sample_file_cols):
    for _, row in df.iterrows():
        # Remove nan's as described in
        # https://stackoverflow.com/questions/40363926/how-do-i-convert-my-dataframe-into-a-dictionary-while-ignoring-the-nan-values
        # Elasticsearch crashes when indexing nan's.
        row_dict = row.dropna().to_dict()
        # Remove the participant_id_col since it is stored as document id.
        del row_dict[participant_id_col]
        # Use the sample_id_col without the project_id + dataset qualification.
        row_dict = {
            table_name + '.' + k if k != sample_id_col else k: v
            for k, v in row_dict.iteritems()
        }

        # Use the sample_file_cols configuration to add the internal
        # '_has_<sample_file_type>' fields to the samples index.
        for file_type, col in sample_file_cols.iteritems():
            # Only mark as false if this sample file column is relevant to the
            # table currently being indexed.
            if col.split('.')[:3] == table_name.split('.'):
                has_name = '_has_%s' % file_type.lower().replace(" ", "_")
                if col in row_dict and row_dict[col]:
                    row_dict[has_name] = True
                else:
                    row_dict[has_name] = False

        script = UPDATE_SAMPLES_SCRIPT % (sample_id_col, sample_id_col)
        yield row[participant_id_col], {
            'source': script,
            'lang': 'painless',
            'params': {
                'sample': row_dict
            }
        }


def index_table(es, index_name, client, table, participant_id_col,
                sample_id_col, sample_file_cols):
    """Indexes a BigQuery table.

    Args:
        es: Elasticsearch object.
        index_name: Name of Elasticsearch index.
        table_name: Fully-qualified table name of the format:
            "<project id>.<dataset id>.<table name>"
        participant_id_col: Name of the column containing the participant ID.
        sample_id_col: (optional) Name of the column containing the sample ID
            (only needed on samples tables).
        sample_file_cols: (optional) Mappings for columns which contain genomic
            files of a particular type (specified in ui.json).
    """
    _create_nested_mappings(es, index_name, table, sample_id_col)
    table_name = _get_table_name(table.full_table_id)
    start_time = time.time()
    logger.info('Indexing %s into %s.' % (table_name, index_name))

    # There is no easy way to import BigQuery -> Elasticsearch. Instead:
    # BigQuery table -> pandas dataframe -> dict -> Elasticsearch
    df = client.list_rows(table).to_dataframe()
    elapsed_time = time.time() - start_time
    elapsed_time_str = time.strftime('%Hh:%Mm:%Ss', time.gmtime(elapsed_time))
    logger.info('BigQuery -> pandas took %s' % elapsed_time_str)
    logger.info('%s has %d rows' % (table_name, len(df)))

    if not participant_id_col in df.columns:
        raise ValueError(
            'Participant ID column %s not found in BigQuery table %s' %
            (participant_id_col, table_name))

    # Samples tables and participant tables need to be indexed in distinct
    # ways. Participants can be updated using the standard partial update,
    # while nested samples must be appended using a 'script', see:
    # https://www.elastic.co/guide/en/elasticsearch/reference/6.4/docs-update.html
    if sample_id_col in df.columns:
        scripts_by_id = _sample_scripts_by_id(df, table_name,
                                              participant_id_col,
                                              sample_id_col, sample_file_cols)
        indexer_util.bulk_index_scripts(es, index_name, scripts_by_id)
    else:
        docs_by_id = _docs_by_id(df, table_name, participant_id_col)
        indexer_util.bulk_index_docs(es, index_name, docs_by_id)

    elapsed_time = time.time() - start_time
    elapsed_time_str = time.strftime("%Hh:%Mm:%Ss", time.gmtime(elapsed_time))
    logger.info('pandas -> ElasticSearch index took %s' % elapsed_time_str)


def index_fields(es, index_name, table):
    table_name = _get_table_name(table.full_table_id)
    logger.info('Indexing %s into %s.' % (table_name, index_name))
    field_docs = _field_docs_by_id(
        table_name, table.schema)
    indexer_util.bulk_index_docs(es, index_name, field_docs)


def read_table(client, table_name):
    project_id, dataset_id, table_name = table_name.split('.')
    return client.get_table(
        client.dataset(dataset_id, project=project_id).table(table_name))


def main():
    args = _parse_args()

    # Read dataset config files
    index_name = indexer_util.get_index_name(args.dataset_config_dir)
    config_path = os.path.join(args.dataset_config_dir, 'bigquery.json')
    bigquery_config = indexer_util.parse_json_file(config_path)
    es = indexer_util.maybe_create_elasticsearch_index(args.elasticsearch_url,
                                                       index_name)

    participant_id_col = bigquery_config['participant_id_column']
    sample_id_col = bigquery_config.get('sample_id_column', None)
    sample_file_cols = bigquery_config.get('sample_file_columns', {})
    client = bigquery.Client(project=args.billing_project_id)

    for table_name in bigquery_config['table_names']:
        table = read_table(client, table_name)
        index_table(es, index_name, client, table, participant_id_col,
                    sample_id_col, sample_file_cols)
        index_fields(es, index_name + '_fields', table)


if __name__ == '__main__':
    main()
