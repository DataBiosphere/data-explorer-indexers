## BigQuery indexer

### Quickstart

Index the public [1000 Genomes BigQuery table](https://bigquery.cloud.google.com/table/genomics-public-data:1000_genomes.sample_info)
into a local Elasticsearch container.

* If `~/.config/gcloud/application_default_credentials.json` doesn't exist,
create it by running `gcloud auth application-default login`.
* Copy [`dataset_config/template/deploy.json`](https://github.com/DataBiosphere/data-explorer-indexers/blob/master/dataset_config/template/deploy.json)
to `dataset_config/1000_genomes/deploy.json`. Set `project_id` to a project
where you are at least Project Editor.
* If `docker network ls` doesn't show `data-explorer_default`, run:
`docker network create data-explorer_default`
* From `bigquery` directory, run: `docker-compose up --build`
* View Elasticsearch index:
  ```
  http://localhost:9200/_cat/indices?v
  http://localhost:9200/1000_genomes/_search?pretty=true
  ```

If you want to run the Data Explorer UI on this dataset, follow the instructions
below. Note that you will have to reindex the data into an Elasticsearch
container from the [data-explorer repo](https://github.com/DataBiosphere/data-explorer/).

### Index a custom dataset locally

* If `~/.config/gcloud/application_default_credentials.json` doesn't exist,
create it by running `gcloud auth application-default login`.
* Setup config files.
  * Create `dataset_config/<my dataset>`. Copy `dataset_config/template/*` to this directory.
  * Edit config files; instructions are in the files. Read
  [Overview](https://github.com/DataBiosphere/data-explorer-indexers#overview)
  for some background information.
* Run Elasticsearch:
  * If you intend to run the [Data Explorer UI](https://github.com/DataBiosphere/data-explorer/)
  after this, run inside the *data-explorer* repo:
    ```
    docker-compose up elasticsearch
    ```
  * If you do not intend to run the Data Explorer UI after this, and just want
  to inspect the index in Elasticsearch, run inside this repo from the
  `bigquery` directory:
    ```
    docker-compose up elasticsearch
    ```
  * If ES crashes due to OOM, you can increase [heap size](https://www.elastic.co/guide/en/elasticsearch/reference/current/heap-size.html):
    ```
    ES_JAVA_OPTS="-Xms10g -Xmx10g" docker-compose up elasticsearch
    ```
    See [tips for indexing large tables](https://github.com/DataBiosphere/data-explorer-indexers/tree/master/bigquery#tips-for-indexing-large-tables-locally).
* Determine the project that will be billed for querying the BigQuery tables.
Your account must have `bigquery.jobs.create` permission on this project; this
includes any project where you have the Viewer/Editor/Owner role.
* Run the indexer. From `bigquery` directory, run:
  ```
  DATASET_CONFIG_DIR=dataset_config/<my dataset> docker-compose up --build indexer
  ```
* View Elasticsearch index:
  ```
  http://localhost:9200/_cat/indices?v
  http://localhost:9200/MY_DATASET/_search?pretty=true
  ```
* Optionally, [bring up a local Data Explorer UI](https://github.com/DataBiosphere/data-explorer/blob/5441559c57ab7a2e0813e8e4fe7e19a9394f1bdf/README.md#run-local-data-explorer-with-a-specific-dataset).

### Overview

In [`bigquery.json`](https://github.com/DataBiosphere/data-explorer-indexers/blob/master/dataset_config/template/bigquery.json),
the dataset curator specifies:

- A list of BigQuery tables
- Name of participant id, sample id, and time series columns

For each table, the entire contents of the table are indexed.
(The dataset curator specifies which fields appear in the Data
Explorer UI in [`ui.json`](https://github.com/DataBiosphere/data-explorer/blob/master/dataset_config/template/ui.json).)

For the main dataset index (see [1000 Genomes example document](https://github.com/DataBiosphere/data-explorer-indexers/blob/master/README.md#main-dataset-index)):
- Each table must contain the participant id column, and optionally can contain either the sample id column or the time series column, but not both.
- If a table does not contain the sample id column or the time series column, then all columns other than the participant id column are treated as participant fields and indexed in a top-level participant document.
- If a table has the participant id and sample id columns, then all other columns are treated as sample fields and are added to a nested sample object under the participant document. Note that there cannot be more than one row per (participant x sample) pair.
- If a table has the participant id and time series columns, then all other columns are treated as participant fields with time series data. The time series column cannot contain any null values. There should only be one row per (participant x time series) pair; if there are multiple such rows, the values from one row will take precedence, and other rows will be ignored by the indexer.

For the fields index (see [1000 Genomes example document](https://github.com/DataBiosphere/data-explorer-indexers/blob/master/README.md#fields-index)):
- Document id is the name of the Elasticsearch field from the main dataset index
- `field_name` is BigQuery column name
- `field_description` is the BigQuery column description, if it exists

To inspect the Elasticsearch indices for 1000 Genomes, run
the [above Quickstart](https://github.com/DataBiosphere/data-explorer-indexers/tree/master/bigquery#quickstart)
and look at:
```
http://localhost:9200/1000_genomes/_search?pretty=true
http://localhost:9200/1000_genomes_fields/_search?pretty=true
```

### Generating `requirements.txt`

`requirements.txt` is autogenerated from `requirements-to-freeze.txt`. The
latter lists only direct dependencies. To regenerate run from `bigquery` directory:

```
virtualenv ~/virtualenv/indexer-bigquery
source ~/virtualenv/indexer-bigquery/bin/activate
pip install -r requirements-to-freeze.txt
pip freeze | sort -f | sed 's/^indexer-util.*/\.\/indexer_util/g' > requirements.txt
deactivate
```

### Troubleshooting

When indexing a large table on a Mac, Elasticsearch may crash with no error
message in the logs. Try increasing Docker's memory, for example from 2 GB to
3 GB.

### Tips for working locally with large tables

A 2 GB table can take 4 hours to index. Here are tips so you don't have to wait
for reindexing.

Note that if your index is already on GKE and you want to test out the UI,
[follow these instructions instead](https://github.com/DataBiosphere/data-explorer-indexers/tree/master/bigquery/deploy#running-a-local-ui-with-an-index-from-gke).

Always pass `--no-recreate` to `docker-compose up elasticsearch`.

What you want to avoid at all costs is this `docker-compose` output:
```
Recreating data-explorer_elasticsearch_1 ... done
```
If you see this, your indices have been deleted. Regardless of whether you running `docker-compose up` on just the `elasticsearch` service or all services, pass `--no-recreate`.

So the basic flow is:
- Run `ES_JAVA_OPTS="-Xms10g -Xmx10g" docker-compose up elasticsearch`, then Ctrl-C
  - You can confirm 10g heap with `http://localhost:9200/_cluster/stats?human&pretty`.
  Look for `jvm`/`mem` section.
- Run `docker-compose up --no-recreate elasticsearch`. Leave this one running.
- In another window, run `DATASET_CONFIG_DIR=dataset_config/<my dataset> docker-compose up --build indexer`
- Then if you want to run Data Explorer UI, don't include `elasticsearch` in
  `docker-compose up`: `docker-compose up --build -t 0 nginx_proxy ui apise kibana`

### Authenticating as a different user

To see which Google account you are authenticated to GCP as, run `gcloud auth list`.
If you need to run the indexer as a different account (eg because the other
account has BigQuery access), run `gcloud auth application-default login` and
select the other account.
