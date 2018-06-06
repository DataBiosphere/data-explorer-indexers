## Running on GKE

* Set up the Kubernetes environment
  * Create cluster
    * Go to https://console.cloud.google.com/kubernetes/list and click `Create Cluster`
    * Change name to `elasticsearch-cluster`
    * Change `Machine type` to `4 vCPUs`. (Otherwise will get Insufficient CPU error.)
    * Expand `More` -> Click on `Set access for each API` -> Change `BigQuery` to enabled.
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
    docker build -t gcr.io/PROJECT_ID/bq-indexer
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
