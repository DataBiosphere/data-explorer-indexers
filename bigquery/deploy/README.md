# Deploying on GKE

## Controlled-access datasets
Work with the Dataset owner to identity a Google Group of users with read-only
access to the dataset. If you intend for users to work with your dataset in
[Terra](https://http://app.terra.bio), you must use
[Terra groups](https://app.terra.bio/#groups); see
[here for more info](https://software.broadinstitute.org/firecloud/documentation/article?id=9553).
Terra groups are automatically synced to a firecloud.org Google Group. For
example, for Terra group `foo`:
* Terra workspaces for your dataset will be shared to the Terra group `foo`.
* Terra workspaces for your dataset must set
  [Authorization Domain](https://gatkforums.broadinstitute.org/firecloud/discussion/9524/authorization-domains)
  to Terra group `foo`. This ensures that only authorized users will see data
  sent from Data Explorer to Terra.
* The Google Group foo@firecloud.org will be used for
  [restricting who can see Data Explorer](https://github.com/DataBiosphere/data-explorer/tree/master/deploy#enable-access-control).

## Create GKE cluster
* Create project  
  We recommend creating a
  project because all project Editors/Owners will indirectly have
  access to the BigQuery tables. (Project Editors/Owners by default have
  permission to act as service accounts, and the indexer service account will be
  given permission to read the BigQuery tables.)
  * Create project. We recommend the project ID
  be `DATASET-explorer`.
    * Ensure that anyone who is
    granted Editor/Owner roles in this project, already has access to the BigQuery tables.
  * Set up Stackdriver at https://app.google.stackdriver.com/?project=PROJECT
  This is needed to view GKE monitoring charts.
* Set up service account  
[Following the principle of least privilege](https://cloud.google.com/kubernetes-engine/docs/tutorials/authenticating-to-cloud-platform#why_use_service_accounts),
we require using a new `indexer` service account with only the necessary permissions.
Only this service account will be given access to the BigQuery tables. Some of the deploy scripts
assume the service account has this name.
  * Create service account
    * Navigate to `IAM & Admin > Service Accounts > Create Service Account`.
    * Name is `indexer`; some scripts assume this.
    * Click `Create` and add roles:
      * `Storage Admin` Temporarily
    exporting BigQuery tables to GCS during indexing, reading
    docker images from GCR, and creating the sample export file.
      * `BigQuery User`
        * `bigquery.jobs.create` permission: Run BigQuery query.
        * `bigquery.datasets.get` permission: Used if dataset contains a view.
      * `Logs Writer` For [GKE logs](https://console.cloud.google.com/logs/viewer).
      * `Monitoring Metric Writer` For GKE monitoring charts.
  * In the project with the BigQuery dataset, make the service account a
  BigQuery Data Viewer.
* Create cluster. From project root, run:
  ```
  kubernetes-elasticsearch-cluster/create-cluster.sh DATASET [ZONE]
  ```
  Where DATASET is the name of the config directory in `dataset_config`.
    * If you have run `gcloud app create` in this project, you don't need to pass zone. The script will use your App Engine ZONE.
    * If you haven't run `gcloud app create`, you must pass ZONE. Make a note of what zone you pass; you must use this zone when you run `gcloud app create`.
  Note that once gcloud app create is run and a zone is selected, the App Engine zone cannot be changed.


## Run Elasticsearch on GKE
* From project root, run:
  ```
  kubernetes-elasticsearch-cluster/deploy-es.sh DATASET
  ```
  Where DATASET is the name of the config directory in `dataset_config`.
* Test that Elasticsearch is up:
  ```
  kubectl exec -it es-data-0 curl localhost:9200/_cat/indices?v
  ```

## Run Indexer on GKE
* If you did the "Run Elasticsearch on GKE" step a while ago, run
  these commands to point `gcloud` and `kubectl` to the right project.
  ```
  # See what projects gcloud and kubectl are configured for
  gcloud config get-value project
  kubectl config current-context
  # Point gcloud and kubetl to the right project
  gcloud config set project PROJECT
  gcloud container clusters get-credentials elasticsearch-cluster --zone ZONE
  ```
  Where `ZONE` is the
  [zone](https://console.cloud.google.com/kubernetes/list) in which
  elasticsearch-cluster is running, e.g. `us-central1-a`.
* We recommend you delete the index, to start from a clean slate.
  ```
  kubectl exec -it es-data-0 -- curl -XDELETE localhost:9200/DATASET*
  ```
  Where DATASET is the name of the config directory in `dataset_config`.
* Make sure the files in `dataset_config/DATASET` are filled out.
  * Make sure `deploy.json` (and the `authorization_domain` field in
    `dataset.json`, if the dataset is private) are filled out.
* From project root, run:
  ```
  bigquery/deploy/deploy-indexer.sh DATASET
  kubectl logs -f $(kubectl get pods | awk '/bq-indexer/ {print $1;exit}')
  ```
* Verify the indexer was successful:
  ```
  kubectl exec -it es-data-0 curl localhost:9200/_cat/indices?v
  ```

## Elasticsearch performance tuning

For a 2.3G BigQuery table, we have found the following `deploy.json` works well:
```
  "node_pool_machine_type": "n1-highmem-8",
  "node_pool_num_nodes": "5",
```
The smallest machine type that can be used is `n1-standard-4` otherwise there
will be OOM errors. If you'd like more CPU or memory you can switch to a
larger machine.

### How to monitor cpu

GKE console: Look at the CPU chart for a Workload.

Command line: `while true; do kubectl top pods; sleep 1; done`

### How to monitor memory

The GKE console charts are not helpful for memory because Elasticsearch heap
size is constant. Instead, use the command line to find out how much of the
heap is used: `while true; do curl -s localhost:9200/_cat/nodes?h=name,heap.percent | sort; sleep 1; done`

### Indexing performance

The bottleneck for indexing performance tends to be data node CPU.
(Here "node" refers to the Elasticsearch node, which runs in a Kubernetes pod.)

To find out how many cpu were requested, navigate to one of the `es-data`
containers in the Cloud Console ([example](https://i.imgur.com/iwygmh9.png)).
In this example, 2 cpu were requested.

During indexing, if the data nodes cpu usage is close to the limit,
give the data nodes more cpu. We can do this by changing the data node
[machine type](https://cloud.google.com/compute/docs/machine-types) in `deploy.json`.

### Query performance

If your Data Explorer UI has [enable_search_values](https://github.com/DataBiosphere/data-explorer/blob/2daf10777470b17f3f43df1685eca0e41323389b/dataset_config/template/ui.json#L24)
set to true, Elasticsearch queries may be slow. For example, if I type `pre`
into the Data Explorer UI search box, it may take 5+ seconds before I get
results back.

In `deploy.json`, try increasing `node_pool_num_nodes` to 5.
By default, Elasticsearch indices use 5 shards. With 5 replicas, each replica
will have 1 shard. (As opposed to one replica having 2 shards and being a
bottleneck.)

## Running a local UI with an index from GKE

This only works on Linux machines because [docker host networking](https://docs.docker.com/network/host/)
only works on Linux machines.

```
gcloud config set project MY_PROJECT
gcloud container clusters get-credentials elasticsearch-cluster --zone MY_ZONE
kubectl port-forward es-data-0 9200:9200
# Now Chrome tab with localhost:9200/_cat/indices?v works
# Run this from inside data-explorer repo
git cherry-pick --no-commit 6cee79dab14fc9707b5936345e35bd0b54578425
DATASET_CONFIG_DIR=dataset_config/<my dataset> docker-compose up --build -t 0 ui apise nginx_proxy
```
Now UI will be at `localhost:4401`.
