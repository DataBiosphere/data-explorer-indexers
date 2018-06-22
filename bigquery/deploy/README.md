## Running on GKE

* Set up the Kubernetes environment
  * Create a service account and give it access to the BigQuery tables for your
  dataset  
  [Following the principle of least privilege](https://cloud.google.com/kubernetes-engine/docs/tutorials/authenticating-to-cloud-platform#why_use_service_accounts),
  we recommend using a service account with only the necessary permissions,
  rather than the default Compute Engine service account (which has the Editor
  role).
    * Create a project for deploying Data Explorer. We recommend creating a
      project because all project Editors/Owners will indirectly have
      access to the BigQuery tables. (Project Editors/Owners by default have
      permission to act as service accounts, and the indexer service account will be
      given permission to read the BigQuery tables.)
      * Ensure that anyone who is
      granted Editor/Owner roles in this project, already has access to the BigQuery tables.
    * Create the service account
      * Navigate to `IAM & Admin > Service Accounts > Create Service Account`.
      * We suggest the name `DATASET-data-explorer-indexer` to make it clear
      what this service account does.
      * Add the `Storage > Storage Object Viewer` role. This is for reading
      docker images from GCR. Note that this will give the service account access to
      all GCS buckets for this project, so we recommend not storing any
      sensitive data in those buckets.
      * Add the `BigQuery > BigQuery Job User` role. This allows the service
      account to run a BigQuery query, which takes place while indexing the
      BigQuery tables into Elasticsearch. Note that [this project will be billed](https://github.com/DataBiosphere/data-explorer-indexers/blob/master/bigquery/indexer.py#L131)
      for the BigQuery query, not the project containing the BigQuery tables.
    * Work with the Dataset owner to identity a Google Group with read-only
    access to the dataset, that the service account can be added to. Add the
    service account to the Google Group.
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
  * If you did the "Run Elasticsearch on GKE" step a while ago, you can run
    these commands to see if `gcloud` and `kubectl` are configured correctly.
    ```
    gcloud config get-value project
    kubectl config current-context
    ```
    If needed, point `gcloud` and `kubectl` to the right project:
    ```
    gcloud config set project MY_PROJECT
    # This will make kubectl use this cluster.
    gcloud container clusters get-credentials elasticsearch-cluster --zone MY_ZONE
    ```
  * We recommend you delete the index, to start from a clean slate.
    ```
    kubectl get svc,pods
    kubectl exec -it ES_CLIENT_POD -- /bin/bash
    curl -XDELETE EXTERNAL_IP:9200/MY_DATASET
    ```
  * Make sure the files in `dataset_config/MY_DATASET` are filled out.
    * If you don't have config files for your dataset, follow [these
      instructions](https://github.com/DataBiosphere/data-explorer-indexers/tree/master/bigquery#index-a-custom-dataset-locally)
      to set them up.
    * Make sure `dataset_config/MY_DATASET/deploy.json` is filled out.
  * Upload the docker image to GCR. From `bigquery` directory:
    ```
    docker build -t gcr.io/PROJECT_ID/bq-indexer -f Dockerfile ..
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
