"""Indexes BigQuery tables."""
import argparse
import json
import logging
import os
import time
import uuid

from elasticsearch_dsl import Search
from google.cloud import bigquery
from google.cloud import exceptions
from google.cloud import storage

from indexer_util import indexer_util

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(filename)10s:%(lineno)s %(levelname)s %(message)s',
    datefmt='%Y%m%d%H:%M:%S')
logger = logging.getLogger('indexer.bigquery')


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
    return parser.parse_args()


def _table_name_from_table(table):
    # table.full_table_id is the legacy format: project id:dataset id.table name
    # Convert to Standard SQL format: project id.dataset id.table name
    # Use rsplit instead of split because project id may have ":", eg
    # "google.com:api-project-123".
    project_id, dataset_table_id = table.full_table_id.rsplit(':', 1)
    return project_id + '.' + dataset_table_id


def _update_fields_docs(id_prefix, name_prefix, fields, field_docs):
    # This method is recursive to handle nested fields (BigQuery RECORD columns).
    # For nested fields, field name includes all levels of nesting, eg "addresses.city".
    for field in fields:
        field_name = field.name
        field_id = field.name
        if name_prefix:
            field_name = name_prefix + '.' + field_name
        if id_prefix:
            field_id = id_prefix + '.' + field_id
        # For 'RECORD' fields, we want to index only the sub fields. For example
        # if 'address' has {city, state, zip}, we want to index 'address.city',
        # 'address.state' and 'address.zip'.
        if field.field_type == 'RECORD':
            _update_fields_docs(field_id, field_name, field.fields, field_docs)
        else:
            field_doc = {'name': field_name}
            if field.description:
                field_doc['description'] = field.description

            if field_id in field_docs:
                field_docs[field_id].update(field_doc)
            else:
                field_docs[field_id] = field_doc


def _rows_from_export(
        storage_client,
        bucket_name,
        export_obj_prefix,
):
    bucket = storage_client.get_bucket(bucket_name)
    for blob in bucket.list_blobs(prefix=export_obj_prefix):
        logger.info(
            'Reading sharded BigQuery JSON export file: %s' % blob.path)
        json_text = blob.download_as_string()
        for row in json_text.split('\n'):
            # Ignore any blank lines
            if not row:
                continue
            yield json.loads(row)
        # Remove the blob now that we're finished loading it into the index.
        blob.delete()


def _add_table_name_to_row(row, sample_id_column, table_name):
    """
    A row is a dictionary of column names to values.
    For indexing purposes, we need to prepend the column with the table.
    """
    formatted_row = {}
    for k, v in row.iteritems():
        if k != sample_id_column:
            formatted_row['{}.{}'.format(table_name, k)] = v
        else:
            formatted_row[k] = v
    return formatted_row


def _add_sample_table_to_participant_docs(
        storage_client, bucket_name, export_obj_prefix, table_name,
        participant_id_column, sample_id_column, sample_file_columns,
        participant_docs):
    for row in _rows_from_export(storage_client, bucket_name,
                                 export_obj_prefix):
        participant_id = row[participant_id_column]
        sample_id = row[sample_id_column]
        del row[participant_id_column]
        row = _add_table_name_to_row(row, sample_id_column, table_name)

        # Use the sample_file_columns configuration to add the internal
        # '_has_<sample_file_type>' fields to the samples index.
        for file_type, col in sample_file_columns.iteritems():
            # Only mark as false if this sample file column is relevant to the
            # table currently being indexed.
            if table_name in col:
                has_name = '_has_%s' % file_type.lower().replace(" ", "_")
                if col in row and row[col]:
                    row[has_name] = True
                else:
                    row[has_name] = False
        if participant_id not in participant_docs:
            participant_docs[participant_id] = {'samples': {sample_id: row}}
        elif 'samples' not in participant_docs[participant_id]:
            participant_docs[participant_id]['samples'] = {sample_id: row}
        elif sample_id not in participant_docs[participant_id]['samples']:
            participant_docs[participant_id]['samples'][sample_id] = row
        else:
            participant_docs[participant_id]['samples'][sample_id].update(row)
    return participant_docs


def _add_participant_table_to_participant_docs(
        storage_client, bucket_name, export_obj_prefix, table_name,
        participant_id_column, participant_docs):
    for row in _rows_from_export(storage_client, bucket_name,
                                 export_obj_prefix):
        participant_id = row[participant_id_column]
        del row[participant_id_column]
        row = {'%s.%s' % (table_name, k): v for k, v in row.iteritems()}
        if participant_id in participant_docs:
            participant_docs[participant_id].update(row)
        else:
            participant_docs[participant_id] = row
    return participant_docs


def _create_table_from_view(bq_client, view):
    # Creates a table named {}_copy that is a copy of view into
    # dataset 'dataset_for_view_exports'.
    # Creates the dataset if it doesn't exist.
    # Both the table and the dataset are created in the deploy project
    dataset_ref = bq_client.dataset('dataset_for_view_exports')
    try:
        bq_client.get_dataset(dataset_ref)
    except exceptions.NotFound:
        dataset = bigquery.Dataset(dataset_ref)
        dataset = bq_client.create_dataset(dataset)
        logger.info('Created new dataset %s' % dataset.dataset_id)
    new_table_name = '%s_copy' % view.table_id
    new_table_ref = dataset_ref.table(new_table_name)
    new_table_job_config = bigquery.QueryJobConfig()
    new_table_job_config.destination = new_table_ref
    sql = 'SELECT * from `%s`' % _table_name_from_table(view)
    query_job = bq_client.query(sql, job_config=new_table_job_config)
    query_job.result()
    new_table = bq_client.get_table(new_table_ref)
    logger.info('Created new table %s as copy of view' %
                _table_name_from_table(new_table))
    return new_table


def add_table_to_participant_docs(es, bq_client, storage_client, index_name,
                                  table, participant_id_column,
                                  sample_id_column, sample_file_columns,
                                  deploy_project_id, participant_docs):
    table_name = _table_name_from_table(table)
    bucket_name = '%s-table-export' % deploy_project_id
    table_export_bucket = storage_client.lookup_bucket(bucket_name)
    if not table_export_bucket:
        table_export_bucket = storage_client.create_bucket(bucket_name)

    unique_id = str(uuid.uuid4())
    export_obj_prefix = 'export-%s' % unique_id
    job_config = bigquery.job.ExtractJobConfig()
    job_config.destination_format = (
        bigquery.DestinationFormat.NEWLINE_DELIMITED_JSON)
    logger.info('Running extract table job for: %s' % table_name)

    table_is_view = table.table_type == 'VIEW'
    if table_is_view:
        # BigQuery cannot export data from a view. So as a workaround,
        # create a table from the view and use that instead.
        logger.info(
            '%s is a view, attempting to create new table' % table_name)
        table = _create_table_from_view(bq_client, table)

    job = bq_client.extract_table(
        table,
        # The '*'' enables file sharding, which is required for larger datasets.
        'gs://%s/%s*.json' % (bucket_name, export_obj_prefix),
        job_id=unique_id,
        job_config=job_config)
    # Wait up to 10 minutes for the resulting export files to be created.
    job.result(timeout=600)
    if sample_id_column in [f.name for f in table.schema]:
        participant_docs = _add_sample_table_to_participant_docs(
            storage_client, bucket_name, export_obj_prefix, table_name,
            participant_id_column, sample_id_column, sample_file_columns,
            participant_docs)
    else:
        participant_docs = _add_participant_table_to_participant_docs(
            storage_client, bucket_name, export_obj_prefix, table_name,
            participant_id_column, participant_docs)

    if table_is_view:
        # Delete the temporary copy table we created
        bq_client.delete_table(table)
        logger.info(
            'Deleted temporary copy table %s' % _table_name_from_table(table))
    return participant_docs


def add_table_to_field_docs(es, index_name, table, sample_id_column,
                             field_docs):
    table_name = _table_name_from_table(table)
    logger.info('Indexing %s into %s.' % (table_name, index_name))

    id_prefix = table_name
    fields = table.schema
    # If the table contains the sample_id_columnm, prefix the elasticsearch Name
    # of the fields in this table with "samples."
    # This is needed to differentiate the sample facets for special handling.
    for field in fields:
        if field.name == sample_id_column:
            id_prefix = "samples." + id_prefix
    _update_fields_docs(id_prefix, '', fields, field_docs)
    return field_docs


def _get_es_field_type(bq_type, bq_mode):
    if bq_type == 'STRING':
        return 'text'
    elif bq_type == 'INTEGER' or bq_type == 'INT64':
        return 'long'
    elif bq_type == 'FLOAT' or bq_type == 'FLOAT64':
        return 'float'
    elif bq_type == 'BOOLEAN' or bq_type == 'BOOL':
        return 'boolean'
    elif bq_type == 'TIMESTAMP' or bq_type == 'DATE' or bq_type == 'TIME' or bq_type == 'DATETIME':
        return 'date'
    elif bq_type == 'RECORD':
        if bq_mode == 'REPEATED':
            return 'nested'
        return 'object'
    else:
        raise Exception('Invalid BigQuery column type')


def _get_datetime_formatted_string(bq_type):
    # When the es field type is date, we need to add a format string
    # according to ISO 8601 standards.
    bq_type_to_iso_formatted_date = {
        'TIMESTAMP': 'yyyy-MM-dd HH:mm:ss z',
        'DATE': 'yyyy-MM-dd',
        'TIME': 'HH:mm:ss',
        'DATETIME': '',  # Intentionally not altering datetime.
    }
    if bq_type not in bq_type_to_iso_formatted_date:
        raise Exception('Invalid BigQuery date type {}'.format(bq_type))
    formatted_date = bq_type_to_iso_formatted_date[bq_type]
    if formatted_date:
        return {'format': formatted_date, 'type': 'date'}
    else:
        return {'type': 'date'}


def _get_has_file_field_name(field_name, sample_file_columns):
    for file_type, col in sample_file_columns.iteritems():
        if field_name in col:
            return '_has_%s' % file_type.lower().replace(" ", "_")
    return ''


def create_mappings(es, index_name, table_name, fields, participant_id_column,
                    sample_id_column, sample_file_columns):
    # By default, Elasticsearch dynamically determines mappings while it ingests data.
    # Instead, we tell Elasticsearch the mappings before ingesting data; and we turn
    # dynamic mapping to false. For large datasets, this dramatically speeds up indexing.
    mappings = {'dynamic': False, 'properties': {}}
    properties = mappings['properties']
    is_samples_table = False
    for field in fields:
        if field.name == sample_id_column:
            is_samples_table = True
            properties['samples'] = {
                'type': 'nested',
                'properties': {
                    sample_id_column: {
                        'type': 'keyword',
                        'ignore_above': 256,
                    }
                }
            }
            properties = properties['samples']['properties']

    for field in fields:
        if field.name == sample_id_column:
            continue
        field_name = '%s.%s' % (table_name, field.name)
        if is_samples_table:
            # Ignore the participant_id_column since it's the
            # root ID of documents.
            if field.name == participant_id_column:
                continue

        es_field_type = _get_es_field_type(field.field_type, field.mode)
        properties[field_name] = {'type': es_field_type}

        if es_field_type == 'nested' or es_field_type == 'object':
            inner_mappings = create_mappings(
                es, index_name, field.fields, participant_id_column,
                sample_id_column, sample_file_columns)
            properties[field_name]['properties'] = inner_mappings['properties']
        elif es_field_type == 'text':
            properties[field_name]['fields'] = {
                'keyword': {
                    'type': 'keyword',
                    'ignore_above': 256
                }
            }
        elif es_field_type == 'date':
            properties[field_name] = _get_datetime_formatted_string(
                field.field_type)

        has_field_name = _get_has_file_field_name(field_name,
                                                  sample_file_columns)
        if has_field_name:
            properties[has_field_name] = {'type': 'boolean'}

    es.indices.put_mapping(doc_type='type', index=index_name, body=mappings)


def read_table(bq_client, table_name):
    # Use rsplit instead of split because project id may have ".", eg
    # "google.com:api-project-123".
    project_id, dataset_id, table_name = table_name.rsplit('.', 2)
    return bq_client.get_table(
        bq_client.dataset(dataset_id, project=project_id).table(table_name))


def create_samples_json_export_file(es, storage_client, index_name,
                                    deploy_project_id, sample_id_column):
    """
    Writes the samples export JSON file to a GCS bucket. This significantly
    speeds up exporting the samples table to Terra in the Data Explorer.

    Args:
        es: Elasticsearch object.
        index_name: Name of Elasticsearch index.
        deploy_project_id: Google Cloud Project ID containing the export samples bucket
    """
    entities = []
    search = Search(using=es, index=index_name)
    for hit in search.scan():
        participant_id = hit.meta['id']
        doc = hit.to_dict()
        for sample in doc.get('samples', []):
            sample_id = sample[sample_id_column]
            export_sample = {'participant': participant_id}
            for es_field_name, value in sample.iteritems():
                # es_field_name looks like "_has_chr_18_vcf", "sample_id" or
                # "verily-public-data.human_genome_variants.1000_genomes_sample_info.In_Low_Coverage_Pilot".
                splits = es_field_name.split('.')
                # Ignore _has_* and sample_id fields.
                if len(splits) != 4:
                    continue
                export_sample[splits[3]] = value

            entities.append({
                'entityType': 'sample',
                'name': sample_id,
                'attributes': export_sample,
            })

    user = os.environ.get('USER')
    # Don't put in deploy_project_id-export because that bucket has TTL= 1 day.
    bucket_name = '%s-export-samples' % deploy_project_id
    bucket = storage_client.lookup_bucket(bucket_name)
    if not bucket:
        bucket = storage_client.create_bucket(bucket_name)
    samples_file_name = '%s-%s-samples' % (index_name, user)
    blob = bucket.blob(samples_file_name)

    # If there are no samples do not create an export file.
    if len(entities) == 0:
        return

    entities_json = json.dumps(entities, indent=4)
    # Remove the trailing ']' character to allow this JSON to be merged
    # with JSON for additional entities using the GCS compose API:
    # https://cloud.google.com/storage/docs/json_api/v1/objects/compose
    entities_json = entities_json[:-1]
    blob.upload_from_string(entities_json)
    logger.info('Wrote gs://%s/%s' % (bucket_name, samples_file_name))


def fix_samples_data_for_es(participant_docs):
    """
    Currently our samples are stored as a dictionary keyed by sample_ids:
    samples: {
        sample_id_1: {
            sample_id_column: sample_id_1
            column_name_1: value_a,
            column_name_2: value_b,
        },
        sample_id_2: {
            sample_id_column: sample_id_2,
            column_name_1: value_c,
            column_name_2: value_d,
        }
    }
    We need to change it to the structure readable by elasticsearch
    samples: [
        {
            sample_id_column: sample_id_1
            column_name_1: value_a,
            column_name_2: value_b,
        },
        {
            sample_id_column: sample_id_1
            column_name_1: value_a,
            column_name_2: value_b,
        }
    ]

    We use the first format for indexing so that if there are two sample tables
    containing information on the same sample, we can look up the sample when
    indexing the second table.
    """
    for participant_id in participant_docs:
        if 'samples' not in participant_docs[participant_id]:
            continue
        participant_docs[participant_id]['samples'] = [
            doc
            for doc in participant_docs[participant_id]['samples'].values()
        ]


def main():
    args = _parse_args()
    # Read dataset config files
    index_name = indexer_util.get_index_name(args.dataset_config_dir)
    fields_index_name = '%s_fields' % index_name
    bigquery_config_path = os.path.join(args.dataset_config_dir,
                                        'bigquery.json')
    bigquery_config = indexer_util.parse_json_file(bigquery_config_path)
    deploy_config_path = os.path.join(args.dataset_config_dir, 'deploy.json')
    deploy_project_id = indexer_util.parse_json_file(
        deploy_config_path)['project_id']
    es = indexer_util.get_es_client(args.elasticsearch_url)
    indexer_util.maybe_create_elasticsearch_index(es, args.elasticsearch_url,
                                                  index_name)
    indexer_util.maybe_create_elasticsearch_index(es, args.elasticsearch_url,
                                                  fields_index_name)

    participant_id_column = bigquery_config['participant_id_column']
    sample_id_column = bigquery_config.get('sample_id_column', None)
    sample_file_columns = bigquery_config.get('sample_file_columns', {})
    bq_client = bigquery.Client(project=deploy_project_id)
    storage_client = storage.Client(project=deploy_project_id)

    participant_docs = {}
    field_docs = {}
    for table_name in bigquery_config['table_names']:
        table = read_table(bq_client, table_name)
        create_mappings(es, index_name, table_name, table.schema,
                        participant_id_column, sample_id_column,
                        sample_file_columns)
        field_docs = add_table_to_field_docs(es, fields_index_name, table,
                                              sample_id_column, field_docs)
        participant_docs = add_table_to_participant_docs(
            es, bq_client, storage_client, index_name, table,
            participant_id_column, sample_id_column, sample_file_columns,
            deploy_project_id, participant_docs)

    fix_samples_data_for_es(participant_docs)

    indexer_util.bulk_index_docs(es, fields_index_name, field_docs)
    indexer_util.bulk_index_docs(es, index_name, participant_docs)

    # Ensure all of the newly indexed documents are loaded into ES.
    time.sleep(5)
    create_samples_json_export_file(es, storage_client, index_name,
                                    deploy_project_id, sample_id_column)


if __name__ == '__main__':
    main()
