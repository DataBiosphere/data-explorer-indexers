# !/bin/bash
#
# Run Data Explorer Indexer integration tests.
#
# Regenerate golden files by running from bigquery/:
#   docker-compose up -d elasticsearch
#   curl -XDELETE localhost:9200/1000_genomes && curl -XDELETE localhost:9200/1000_genomes_fields
#   BILLING_PROJECT_ID=google.com:api-project-360728701457 docker-compose up --build -d indexer
#   curl -s 'http://localhost:9200/1000_genomes/type/HG02924' | jq -rS '._source' > 'tests/integration_golden_index.json'

if (( $# != 1 ))
then
  echo "Usage: tests/integration.sh <billing_project_id>"
  echo "  where <billing_project_id> is the GCP project billed for BigQuery usage"
  echo "Run this script from bigquery/ directory"
  exit 1
fi

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


billing_project_id=$1
docker network create data-explorer_default

# Run Elasticsearch in the background with the indexer in the foreground to prevent blocking the main thread.
docker-compose up -d elasticsearch
waitForClusterHealthy
curl -XDELETE localhost:9200/1000_genomes

BILLING_PROJECT_ID=${billing_project_id} docker-compose up --build indexer
# For some reason index isn't available right after indexer terminates, so sleep.
sleep 5

# Validate the correct number of documents were indexed.
expr $(curl -s 'http://localhost:9200/1000_genomes/_search' | jq -r '.hits.total') = "3500"

# Write the index out to a file in order to diff.
curl -s 'http://localhost:9200/1000_genomes/type/HG02924' | jq -rS '._source' > 'tests/actual_index.json'
DIFF=$(diff tests/integration_golden_index.json tests/actual_index.json)
if [ "$DIFF" != "" ]; then
  echo "Index does not match golden json file, diff:"
  echo "$DIFF"
  exit 1
fi

rm tests/actual_index.json
docker-compose stop
