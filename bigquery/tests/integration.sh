# !/bin/bash
#
# Run Data Explorer Indexer integration tests.
#
# Regenerate the integration_golden_index.json by running from project root (after indexing):
# curl -s 'http://localhost:9200/1000_genomes/_search?size=3500&sort=_id:asc' | jq -rS '.hits.hits' > 'bigquery/tests/integration_golden_index.json'
#
# bigquery/tests/integration.sh <billing_project_id>
#

if (( $# != 1 ))
then
  echo "Usage: biquery/tests/tests.sh <billing_project_id>"
  echo "  where <billing_project_id> is the GCP project billed for BigQuery usage"
  echo "Run this script from project root"
  exit 1
fi

billing_project_id=$1
docker network create data-explorer_default
cd bigquery
# Run Elasticsearch in the background with the indexer in the foreground to prevent blocking the main thread.
docker-compose up -d elasticsearch
BILLING_PROJECT_ID=${billing_project_id} docker-compose up --build indexer
# For some reason index isn't available right after indexer terminates, so sleep.
sleep 5

# Validate the correct number of documents were indexed.
expr $(curl -s 'http://localhost:9200/1000_genomes/_search' | jq -r '.hits.total') = "3500"

# Write the index out to a file in order to diff.
curl -s 'http://localhost:9200/1000_genomes/_search?size=3500&sort=_id:asc' | jq -rS '.hits.hits' > 'tests/actual_index.json'
DIFF=$(diff tests/integration_golden_index.json tests/actual_index.json) 
if [ "$DIFF" != "" ]; then
  echo "Index does not match golden json file, diff:"
  echo "$DIFF"
  exit 1
fi

rm tests/actual_index.json
curl -XDELETE localhost:9200/1000_genomes
docker-compose stop
