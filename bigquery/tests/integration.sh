#!/bin/bash -x
#
# Run Data Explorer Indexer integration tests.
#
# From bigquery/, run: tests/integration.sh
#
# Regenerate golden files by running from bigquery/:
#   docker-compose up -d elasticsearch
#
#   curl -XDELETE localhost:9200/1000_genomes && curl -XDELETE localhost:9200/1000_genomes_fields
#   docker-compose up --build indexer
#   curl -s 'http://localhost:9200/1000_genomes/type/HG02924' | jq -rS '._source' > 'tests/1000_genomes_golden.json'
#   curl -s 'http://localhost:9200/1000_genomes/_mappings?pretty' | jq -rS '.' > 'tests/1000_genomes_mappings_golden.json'
#   curl -s 'http://localhost:9200/1000_genomes_fields/_search?size=200' | jq -rS '.hits.hits' > 'tests/1000_genomes_fields_golden.json'
#
#   curl -XDELETE localhost:9200/framingham_heart_study_teaching_dataset && curl -XDELETE localhost:9200/framingham_heart_study_teaching_dataset_fields
#   DATASET_CONFIG_DIR=dataset_config/framingham_heart_study_teaching docker-compose up --build indexer
#   curl -s 'http://localhost:9200/framingham_heart_study_teaching_dataset/type/9334261' | jq -rS '._source' > 'tests/framingham_heart_study_teaching_dataset_golden.json'
#   curl -s 'http://localhost:9200/framingham_heart_study_teaching_dataset/_mappings?pretty' | jq -rS '.' > 'tests/framingham_heart_study_teaching_dataset_mappings_golden.json'
#   curl -s 'http://localhost:9200/framingham_heart_study_teaching_dataset_fields/_search?size=200' | jq -rS '.hits.hits' > 'tests/framingham_heart_study_teaching_dataset_fields_golden.json'

set -o errexit
set -o nounset


function wait_for_cluster_healthy() {
  status=''
  # For some reason, cluster health is green on CircleCI
  while [[ $status != 'yellow' && $status != 'green' ]]; do
    echo "Waiting for Elasticsearch cluster to be healthy"
    sleep 1
    status=$(curl -s localhost:9200/_cluster/health | jq -r '.status')
  done
  echo "Elasticsearch cluster is now healthy"
}
readonly -f wait_for_cluster_healthy


function delete_indexes() {
  curl -XDELETE localhost:9200/1000_genomes
  curl -XDELETE localhost:9200/1000_genomes_fields
  curl -XDELETE localhost:9200/framingham_heart_study_teaching_dataset
  curl -XDELETE localhost:9200/framingham_heart_study_teaching_dataset_fields
  curl -XDELETE localhost:9200/columns_to_ignore_test
  curl -XDELETE localhost:9200/columns_to_ignore_test_fields
}
readonly -f delete_indexes


function set_up_es() {
  docker network inspect data-explorer_default >/dev/null 2>&1 || \
    docker network create data-explorer_default

  # Run Elasticsearch in the background with the indexer in the foreground to prevent blocking the main thread.
  docker-compose up -d elasticsearch
  wait_for_cluster_healthy
  delete_indexes
}
readonly -f set_up_es


function set_up_indexes(){
  docker-compose up --build indexer
  DATASET_CONFIG_DIR=dataset_config/framingham_heart_study_teaching docker-compose up --build indexer
  # For some reason index isn't available right after indexer terminates, so sleep.
  sleep 5
}
readonly -f set_up_indexes


function validate_framingham_heart_study_teaching_dataset() {
  # Validate the correct number of documents were indexed.
  DOC_COUNT_FRAMINGHAM=$(curl -s 'http://localhost:9200/framingham_heart_study_teaching_dataset/_search' | jq -r '.hits.total')
  if [ "$DOC_COUNT_FRAMINGHAM" != "4434" ]; then
    echo "Number of documents is incorrect, expected 4434, got $DOC_COUNT_FRAMINGHAM"
    exit 1
  fi

  # Write the indexes out to a file in order to diff.
  curl -s 'http://localhost:9200/framingham_heart_study_teaching_dataset/type/9334261' | jq -rS '._source' > 'tests/framingham_heart_study_teaching_dataset.json'
  DIFF=$(diff tests/framingham_heart_study_teaching_dataset_golden.json tests/framingham_heart_study_teaching_dataset.json)
  if [ "$DIFF" != "" ]; then
    echo "Index does not match golden json file, diff:"
    echo "$DIFF"
    exit 1
  fi

  # Write the mappings out to files in order to diff.
  curl -s 'http://localhost:9200/framingham_heart_study_teaching_dataset/_mappings?pretty' | jq -rS '.' > 'tests/framingham_heart_study_teaching_dataset_mappings.json'
  DIFF=$(diff tests/framingham_heart_study_teaching_dataset_mappings_golden.json tests/framingham_heart_study_teaching_dataset_mappings.json)
  if [ "$DIFF" != "" ]; then
    echo "Mappings do not match golden json file, diff:"
    echo "$DIFF"
    exit 1
  fi

  # Write the fields indexes out to files in order to diff.
  curl -s 'http://localhost:9200/framingham_heart_study_teaching_dataset_fields/_search?size=200' | jq -rS '.hits.hits' > 'tests/framingham_heart_study_teaching_dataset_fields.json'
  DIFF=$(diff tests/framingham_heart_study_teaching_dataset_fields_golden.json tests/framingham_heart_study_teaching_dataset_fields.json)
  if [ "$DIFF" != "" ]; then
    echo "Fields index does not match golden json file, diff:"
    echo "$DIFF"
    exit 1
  fi
}
readonly -f validate_framingham_heart_study_teaching_dataset


function validate_1000_genomes() {
  # Validate the correct number of documents were indexed.
  DOC_COUNT_GENOMES=$(curl -s 'http://localhost:9200/1000_genomes/_search' | jq -r '.hits.total')
  if [ "$DOC_COUNT_GENOMES" != "3500" ]; then
    echo "Number of documents is incorrect, expected 3500, got $DOC_COUNT_GENOMES"
    exit 1
  fi

  # Write the indexes out to a file in order to diff.
  curl -s 'http://localhost:9200/1000_genomes/type/HG02924' | jq -rS '._source' > 'tests/1000_genomes.json'
  DIFF=$(diff tests/1000_genomes_golden.json tests/1000_genomes.json)
  if [ "$DIFF" != "" ]; then
    echo "Index does not match golden json file, diff:"
    echo "$DIFF"
    exit 1
  fi

  # Write the mappings out to files in order to diff.
  curl -s 'http://localhost:9200/1000_genomes/_mappings' | jq -rS '.' > 'tests/1000_genomes_mappings.json'
  DIFF=$(diff tests/1000_genomes_mappings_golden.json tests/1000_genomes_mappings.json)
  if [ "$DIFF" != "" ]; then
    echo "Mappings do not match golden json file, diff:"
    echo "$DIFF"
    exit 1
  fi

  # Write the fields indexes out to files in order to diff.
  curl -s 'http://localhost:9200/1000_genomes_fields/_search?size=200' | jq -rS '.hits.hits' > 'tests/1000_genomes_fields.json'
  DIFF=$(diff tests/1000_genomes_fields_golden.json tests/1000_genomes_fields.json)
  if [ "$DIFF" != "" ]; then
    echo "Fields index does not match golden json file, diff:"
    echo "$DIFF"
    exit 1
  fi
}
readonly -f validate_1000_genomes


function test_columns_to_ignore() {
  # Index a dataset that has columns named chr_1_vcf, chr_2_vcf, etc
  # In the config files, explicitly mark that chr_3_vcf as ignored
  # Search should match for chr_1_vcf, but not chr_3_vcf
  echo "Running test_columns_to_ignore"

  DATASET_CONFIG_DIR=tests/columns_to_ignore_test docker-compose up --build indexer

  sleep 5

  es_id_in_index='samples.verily-public-data.human_genome_variants.1000_genomes_sample_info.chr_1_vcf'
  FOUND=$(curl -s "localhost:9200/1000_genomes_test_columns_to_ignore_fields/type/${es_id_in_index}" | jq -rS '.found')
  if [ "$FOUND" == "false" ]; then
    echo "${es_id_in_index} was not found in fields when it should have been."
    exit 1
  fi

  es_id_not_in_index='samples.verily-public-data.human_genome_variants.1000_genomes_sample_info.chr_3_vcf'
  FOUND=$(curl -s "localhost:9200/1000_genomes_test_columns_to_ignore_fields/type/${es_id_not_in_index}" | jq -rS '.found')
  if [ "$FOUND" == "true" ]; then
    echo "${es_id_not_in_index} was found in fields when it should NOT have been."
    exit 1
  fi
}
readonly -f test_columns_to_ignore

# Run integration tests that validate that the base 1000 genomes
# and framingham heart study data explorers still work
set_up_es
set_up_indexes
validate_1000_genomes
validate_framingham_heart_study_teaching_dataset

# Run integration test that checks the "columns_to_ignore" feature
test_columns_to_ignore

rm tests/1000_genomes.json
rm tests/1000_genomes_mappings.json
rm tests/1000_genomes_fields.json
rm tests/framingham_heart_study_teaching_dataset.json
rm tests/framingham_heart_study_teaching_dataset_mappings.json
rm tests/framingham_heart_study_teaching_dataset_fields.json
docker-compose stop
