# Data explorer indexers

### Overview

This repo contains indexers which index a dataset into Elasticsearch, for
use by the [Data Explorer UI](https://github.com/DataBiosphere/data-explorer).

For each dataset, two Elasticsearch indices are created:

1. DATASET_NAME: Each Elasticsearch document represents a participant. The document id is participant id.  
A participant can have
zero or more samples. Within a participant document, a sample is a
[nested object](https://www.elastic.co/guide/en/elasticsearch/reference/current/nested.html#_using_literal_nested_literal_fields_for_arrays_of_objects). Each nested object has a `sample_id` field.
1. DATASET_NAME_fields: Each document represents a field. The document id is elasticsearch_field_name -- that is, the corresponding Elasticsearch field name from the first index. Example fields are age, gender, etc. This index powers field search. TODO: Include screenshot.


### One-time setup

[Set up git secrets.](https://github.com/DataBiosphere/data-explorer-indexers/tree/master/hooks)
