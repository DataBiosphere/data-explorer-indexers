#!/usr/bin/env bash

export RESULT=$(curl -s 'http://localhost:9200/platinum_genomes/_search' | jq -r '.hits.total')

# Assert that the BigQuery index contains the expected number of values
if [ "$RESULT" != "17" ]; then
    echo "Expected 17 hits, got $RESULT"
    exit 1
fi

echo "e2e tests passed"
exit 0
