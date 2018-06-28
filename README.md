# Data explorer indexers

### Overview

A Data Explorer UI allows for faceted search. For example,
[Boardwalk](https://commons.ucsc-cgp-dev.org/boardwalk) has facets Analysis
Type, Center Name, etc.

A dataset may have hundreds of fields. The dataset owner
must [curate a list](https://github.com/DataBiosphere/data-explorer-indexers/blob/master/dataset_config/platinum_genomes/ui.json)
of the most important fields (age, gender, etc).

A dataset has a notion of `primary_key`. For a dataset that tracks 1000
participants, `primary_key` could be `participant_id`. For a dataset that
contains 1000 samples from a single person, `primary_key` could be `sample_id`.

`primary_key` is used to tie information together from different sources.
Say there are facets for age and weight; age and weight are
stored in separate BigQuery tables; and `primary_key` is `participant_id`.
First, age table is indexed. An Elasticsearch document is created for each
`participant_id` with document id = `participant_id`. A document would look
like:

```
{
  "age": "30",
}
```

Then, the weight table is indexed. The Elasticsearch documents will get a new
weight field:

```
{
  "age": "30",
  "weight": "140",
}
```

`participant_id` will be used to figure out which document to update.

## One-time setup

[Set up git secrets.](https://github.com/DataBiosphere/data-explorer-indexers/tree/master/hooks)
