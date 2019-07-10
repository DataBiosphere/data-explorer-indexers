# !/bin/bash
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
#   curl -XDELETE localhost:9200/framingham_teaching && curl -XDELETE localhost:9200/framingham_teaching_fields
#   DATASET_CONFIG_DIR=dataset_config/fram_teaching docker-compose up --build indexer
#   curl -s 'http://localhost:9200/framingham_teaching/type/9334261' | jq -rS '._source' > 'tests/framingham_teaching_golden.json'
#   curl -s 'http://localhost:9200/framingham_teaching/_mappings?pretty' | jq -rS '.' > 'tests/framingham_teaching_mappings_golden.json'
#   curl -s 'http://localhost:9200/framingham_teaching_fields/_search?size=200' | jq -rS '.hits.hits' > 'tests/framingham_teaching_fields_golden.json'

set -o errexit
set -o nounset

waitForClusterHealthy() {
  status=''
  # For some reason, cluster health is green on CircleCI
  while [[ $status != 'yellow' && $status != 'green' ]]; do
    echo "Waiting for Elasticsearch cluster to be healthy"
    sleep 1
    status=$(curl -s localhost:9200/_cluster/health | jq -r '.status')
  done
  echo "Elasticsearch cluster is now healthy"
}


docker network create data-explorer_default

# Run Elasticsearch in the background with the indexer in the foreground to prevent blocking the main thread.
docker-compose up -d elasticsearch
waitForClusterHealthy
curl -XDELETE localhost:9200/1000_genomes
curl -XDELETE localhost:9200/1000_genomes_fields
curl -XDELETE localhost:9200/framingham_teaching
curl -XDELETE localhost:9200/framingham_teaching_fields

docker-compose up --build indexer
DATASET_CONFIG_DIR=dataset_config/fram_teaching docker-compose up --build indexer
# For some reason index isn't available right after indexer terminates, so sleep.
sleep 5

# Validate the correct number of documents were indexed.
DOC_COUNT_GENOMES=$(curl -s 'http://localhost:9200/1000_genomes/_search' | jq -r '.hits.total')
if [ "$DOC_COUNT_GENOMES" != "3500" ]; then
  echo "Number of documents is incorrect, expected 3500, got $DOC_COUNT_GENOMES"
  exit 1
fi

DOC_COUNT_FRAMINGHAM=$(curl -s 'http://localhost:9200/framingham_teaching/_search' | jq -r '.hits.total')
if [ "$DOC_COUNT_FRAMINGHAM" != "4434" ]; then
  echo "Number of documents is incorrect, expected 4434, got $DOC_COUNT_FRAMINGHAM"
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

curl -s 'http://localhost:9200/framingham_teaching/type/9334261' | jq -rS '._source' > 'tests/framingham_teaching.json'
DIFF=$(diff tests/framingham_teaching_golden.json tests/framingham_teaching.json)
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

curl -s 'http://localhost:9200/framingham_teaching/_mappings?pretty' | jq -rS '.' > 'tests/framingham_teaching_mappings.json'
DIFF=$(diff tests/framingham_teaching_mappings_golden.json tests/framingham_teaching_mappings.json)
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

curl -s 'http://localhost:9200/framingham_teaching_fields/_search?size=200' | jq -rS '.hits.hits' > 'tests/framingham_teaching_fields.json'
DIFF=$(diff tests/framingham_teaching_fields_golden.json tests/framingham_teaching_fields.json)
if [ "$DIFF" != "" ]; then
  echo "Fields index does not match golden json file, diff:"
  echo "$DIFF"
  exit 1
fi


rm tests/1000_genomes.json
rm tests/1000_genomes_mappings.json
rm tests/1000_genomes_fields.json
rm tests/framingham_teaching.json
rm tests/framingham_teaching_mappings.json
rm tests/framingham_teaching_fields.json
docker-compose stop
