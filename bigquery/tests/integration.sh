# !/bin/bash
#
# Run Data Explorer Indexer integration tests.
#
# Regenerate golden files by running from bigquery/:
#   docker-compose up -d elasticsearch
#   curl -XDELETE localhost:9200/1000_genomes && curl -XDELETE localhost:9200/1000_genomes_fields
#   BILLING_PROJECT_ID=google.com:api-project-360728701457 docker-compose up --build -d indexer
#   curl -s 'http://localhost:9200/1000_genomes/type/HG02924' | jq -rS '._source' > 'tests/1000_genomes_golden.json'
#   curl -s 'http://localhost:9200/1000_genomes/_mappings?pretty' | jq -rS '.' > 'tests/1000_genomes_mappings_golden.json'
#   curl -s 'http://localhost:9200/1000_genomes_fields/_search?size=200' | jq -rS '.hits.hits' > 'tests/1000_genomes_fields_golden.json'

# if (( $# != 1 ))
# then
#   echo "Usage: tests/integration.sh <billing_project_id>"
#   echo "  where <billing_project_id> is the GCP project billed for BigQuery usage"
#   echo "Run this script from bigquery/ directory"
#   exit 1
# fi

# waitForClusterHealthy() {
#   status=''
#   # For some reason, cluster health is green on CircleCI
#   while [[ $status != 'yellow' && $status != 'green' ]]; do
#     echo "Waiting for Elasticsearch cluster to be healthy"
#     sleep 1
#     status=$(curl -s localhost:9200/_cluster/health | jq -r '.status')
#   done
#   echo "Elasticsearch cluster is now healthy"
# }


# billing_project_id=$1
# docker network create data-explorer_default

# # Run Elasticsearch in the background with the indexer in the foreground to prevent blocking the main thread.
# docker-compose up -d elasticsearch
# waitForClusterHealthy
# curl -XDELETE localhost:9200/1000_genomes
# curl -XDELETE localhost:9200/1000_genomes_fields

# BILLING_PROJECT_ID=${billing_project_id} docker-compose up --build indexer
# # For some reason index isn't available right after indexer terminates, so sleep.
# sleep 5

# Validate the correct number of documents were indexed.
DOC_COUNT=$(curl -s 'http://localhost:9200/1000_genomes/_search' | jq -r '.hits.total')
if [ "$DOC_COUNT" != "3714" ]; then
  echo "Number of documents is incorrect, expected 3714, got $DOC_COUNT"
  exit 1
fi

# Write the index out to a file in order to diff.
curl -s 'http://localhost:9200/1000_genomes/type/HG02924' | jq -rS '._source' > 'tests/1000_genomes.json'
DIFF=$(diff tests/1000_genomes_golden.json tests/1000_genomes.json)
if [ "$DIFF" != "" ]; then
  echo "Index does not match golden json file, diff:"
  echo "$DIFF"
  exit 1
fi

# Write the mappings out to a file in order to diff.
curl -s 'http://localhost:9200/1000_genomes/_mappings' | jq -rS '.' > 'tests/1000_genomes_mappings.json'
DIFF=$(diff tests/1000_genomes_mappings_golden.json tests/1000_genomes_mappings.json)
if [ "$DIFF" != "" ]; then
  echo "Index does not match golden json file, diff:"
  echo "$DIFF"
  exit 1
fi

# Write the fields index out to a file in order to diff.
curl -s 'http://localhost:9200/1000_genomes_fields/_search?size=200' | jq -rS '.hits.hits' > 'tests/1000_genomes_fields.json'
DIFF=$(diff tests/1000_genomes_fields_golden.json tests/1000_genomes_fields.json)
if [ "$DIFF" != "" ]; then
  echo "Fields index does not match golden json file, diff:"
  echo "$DIFF"
  exit 1
fi


rm tests/1000_genomes.json
rm tests/1000_genomes_mappings.json
rm tests/1000_genomes_fields.json
docker-compose stop
