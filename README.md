# Data explorer indexers

### Overview

A Data Explorer UI allows for faceted search. For example,
[Boardwalk](https://commons.ucsc-cgp-dev.org/boardwalk) has facets Analysis
Type, Center Name, etc.

A dataset may have hundreds of fields. The dataset owner
must [curate a list](https://github.com/DataBiosphere/data-explorer/blob/master/dataset_config/1000_genomes/ui.json)
of the most important fields (age, gender, etc).

A dataset has a notion of `participant_id` and (optional) `sample_id`. The
columns in BigQuery tables which represent these IDs are configured in [`bigquery.json`](https://github.com/DataBiosphere/data-explorer-indexers/blob/master/dataset_config/template/bigquery.json#L17-L18).


### Participant Indexing
`participant_id` is used as the primary key in the index and ties information
together from different sources. Say there are facets for age and weight; age
and weight are stored in separate BigQuery tables, all with a `participant_id`
column. First, age table is indexed. An Elasticsearch document is created for
each `participant_id` with document id = `participant_id`. A document would look
like:
```
{
  "myproject.mydataset.table1.age": "30",
}
```

Then, the weight table is indexed. The Elasticsearch documents will get a new
weight field:
```
{
  "myproject.mydataset.table1.age": "30",
  "myproject.mydataset.table2.weight": "140",
}
```

`participant_id` will be used to figure out which document to update.

### Sample Indexing
`participant_id` is also used as the foreign key for samples, which are stored
as a [nested datatype](https://www.elastic.co/guide/en/elasticsearch/reference/current/nested.html)
in the index beneath participants. `sample_id` is the secondary key for samples
and can be used to tie together information from different sources, just like
`participant_id`. Suppose we index two samples tables, one containing the tissue
type and the other with the sequencing type. After indexing the first samples
table, a document would look like:
```
{
  "myproject.mydataset.table1.age": "30",
  "myproject.mydataset.table2.weight": "140",
  "samples": [
    "sample_id": "S001",
    "myproject.mydataset.table3.tissue_type": "blood"
  ]  
}
```

Then, the sequencing type table is indexed. The nested sample document will
get a new `sequencing_type` field:
```
{
  ...
  "samples": [
    "sample_id": "S001",
    "myproject.mydataset.table3.tissue_type": "blood",
    "myproject.mydataset.table4.sequencing_type": "WGS"
  ]  
}
```

### Sample File Types
Fields which contain important types of genomic files can additionally be
specified in [`bigquery.json`](https://github.com/DataBiosphere/data-explorer-indexers/blob/master/dataset_config/template/bigquery.json#L20)
under `sample_file_columns`. These columns are used to generated a special
Samples Overview facet.
[comment]: # TODO(bryancrampton): Inline screenshot of Samples Overview facet


## One-time setup

[Set up git secrets.](https://github.com/DataBiosphere/data-explorer-indexers/tree/master/hooks)
