# !/bin/bash
#
# Run Data Explorer Indexer integration tests.
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

# Compare the index to a golden index file.
golden_index=$(cat tests/integration_golden_index.json)
current=$(curl -s 'http://localhost:9200/1000_genomes/_search?size=10000&sort=_id:asc' | jq -r '.hits.hits')
if [[ "$golden_index" != "$current" ]]; then
  echo "Index does not match golden json file"
  exit 1
fi

curl -XDELETE localhost:9200/1000_genomes
docker-compose stop
