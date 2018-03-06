## BigQuery indexer

### Overview
Index BigQuery tables into Elasticsearch. Only specified facet fields will be indexed.

Given this BigQuery table:
participant_id | age | weight
- | - |-
1 | 23 | 140
2 | 33 | 150

Elasticsearch index will contain 2 documents. First document has id `1` and contains:

	{
	  "age": "23",
	  "weight": "140",
	}
	
### How to run
TODO: Create Dockerfile and simplify these steps.
* Edit files in `config/`.
* 
    ```
    virtualenv ~/virtualenv/elasticsearch
    ~/virtualenv/elasticsearch/bin/activate
    pip install elasticsearch pandas pandas_gbq
    python indexer.py
   ```
