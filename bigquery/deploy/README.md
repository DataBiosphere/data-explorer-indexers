## Running on GKE

* Set up the Kubernetes environment
  * Create a service account and give it access to the BigQuery tables for your
  dataset
    * [Following the principle of least privilege](https://cloud.google.com/kubernetes-engine/docs/tutorials/authenticating-to-cloud-platform#why_use_service_accounts),
    we create a service account and give it only the necessary permissions,
    rather than use the default Compute Engine service account. At the end of
    this section, the new service account will have access to the BigQuery
    tables for your dataset. Before creating the service account, you must
    ensure that everyone who could use this service account already has access
    to the BigQuery tables. To see who could use this service account, navigate
    to `IAM & Admin` and look for `Owner`, `Editor`, and `Service Account User`
    roles.
    * Create the service account
      * Navigate to `IAM & Admin > Service Accounts > Create Service Account`.
      * We suggest the name `DATASET-data-explorer-indexer` to make it clear
      what this service account does.
      * Add the `Storage > Storage Object Viewer` role. This is for reading
      docker images from GCR.
      * Add the `BigQuery > BigQuery Job User` role. This allows the service
      account to run a BigQuery query, which takes place while indexing the
      BigQuery tables into Elasticsearch. Note that [this project will be billed](https://github.com/DataBiosphere/data-explorer-indexers/blob/master/bigquery/indexer.py#L131)
      for the BigQuery query, not the project containing the BigQuery tables.
    * Add the service account to the Google Group with read-only access to the
    dataset
  * Create cluster
    * Go to https://console.cloud.google.com/kubernetes/list and click `Create Cluster`
    * Change name to `elasticsearch-cluster`
    * Change `Machine type` to `4 vCPUs`. (Otherwise will get Insufficient CPU error.)
    * Expand `More` and select the service account you just created.
    * Click `Create`
  * After cluster has finished creating, run:
    ```
    gcloud container clusters get-credentials elasticsearch-cluster --zone MY_ZONE
    ```
    This will make `kubectl` use this cluster.

* Run Elasticsearch on GKE
  * Deploy Elasticsearch:
    ```
    cd bigquery/deploy/kubernetes-elasticsearch-cluster/
    ./deploy.sh
    ```
  * Test that Elasticsearch is up. ES_CLIENT_POD is something like
  `es-client-595585f9d4-7jw9v`; it doesn't have the `pod/` prefix.
    ```
    kubectl get svc,pods
    kubectl exec -it ES_CLIENT_POD -- /bin/bash
    curl EXTERNAL_IP:9200
    ```

* Run indexer on GKE
  * If you are using the default [platinum_genomes dataset](https://github.com/DataBiosphere/data-explorer-indexers/tree/master/bigquery/config/platinum_genomes),
don't forget to [copy to your project and set project IDs in facet_fields.csv](https://github.com/DataBiosphere/data-explorer-indexers/tree/master/bigquery#quickstart).
  * Build, tag, and upload the base docker image to GCR:
    ```
    cd bigquery
    docker build -t gcr.io/PROJECT_ID/bq-indexer .
    docker push gcr.io/PROJECT_ID/bq-indexer
    ```
  * Update `bigquery/deploy/bq-indexer.yaml` with the desired MY_GOOGLE_CLOUD_PROJECT and
  EXTERNAL_IP.
  * Run the indexer:
    ```
    cd bigquery/deploy
    kubectl create configmap dataset-config --from-file=DATASET_CONFIG_DIR
    kubectl create -f bq-indexer.yaml
    ```
  * Verify the indexer was successful:
    ```
    kubectl get svc,pods
    kubectl exec -it ES_CLIENT_POD -- /bin/bash
    curl EXTERNAL_IP:9200/_cat/indices?v
    ```

## Bringing down Elasticsearch

If you no longer need this Elasticsearch deployment:
```
kubectl config get-clusters
kubectl config delete-cluster CLUSTER_NAME
```
