## Running on GKE

* For private datasets, determine readers Google Group  
  Work with the Dataset owner to identity a Google Group of users with read-only
  access to the dataset.  
  * If you intend for users to work with your dataset in Saturn, it is highly
    recommended to use a Saturn group. The Saturn group will be synced to a
    Google Group, but not the other way around; so group management must be done
    in the Saturn Group UI.  
    For example, consider a Saturn group foo, which is
    automatically synced to Google Group foo@firecloud.org:
      * The Saturn group will be used for setting [Authorization Domains](https://gatkforums.broadinstitute.org/firecloud/discussion/9524/authorization-domains)
      on workspaces. This ensures that only authorized users will see data sent
      from Data Explorer to Saturn.
      * The Google Group will be used for [restricting who can see
    Data Explorer](https://github.com/DataBiosphere/data-explorer/tree/master/deploy#enable-access-control).
* Set up the Kubernetes environment
  * Create a service account and give it access to the BigQuery tables for your
  dataset  
  [Following the principle of least privilege](https://cloud.google.com/kubernetes-engine/docs/tutorials/authenticating-to-cloud-platform#why_use_service_accounts),
  we recommend using a service account with only the necessary permissions,
  rather than the default Compute Engine service account (which has the Editor
  role).
    * Create a project for deploying Data Explorer. We recommend the project ID
      be `DATASET-data-explorer`. We recommend creating a
      project because all project Editors/Owners will indirectly have
      access to the BigQuery tables. (Project Editors/Owners by default have
      permission to act as service accounts, and the indexer service account will be
      given permission to read the BigQuery tables.)
      * Ensure that anyone who is
      granted Editor/Owner roles in this project, already has access to the BigQuery tables.
    * Create the service account
      * Navigate to `IAM & Admin > Service Accounts > Create Service Account`.
      * We recommend the name `indexer` to make it clear what this service account does.
        The full service account email would be `indexer@DATASET-data-explorer.iam.gserviceaccount.com`
      * Add the `Storage > Storage Object Viewer` role. This is for reading
      docker images from GCR. Note that this will give the service account access to
      all GCS buckets for this project, so we recommend not storing any
      sensitive data in those buckets.
      * Add the `BigQuery > BigQuery Job User` role. This allows the service
      account to run a BigQuery query, which takes place while indexing the
      BigQuery tables into Elasticsearch. Note that [this project will be billed](https://github.com/DataBiosphere/data-explorer-indexers/blob/master/bigquery/indexer.py#L131)
      for the BigQuery query, not the project containing the BigQuery tables.
      * Add the `Logging -> Logs Writer` role. This is needed for GKE logs to
      appear at https://console.cloud.google.com/logs/viewer
    * Add the service account to the readers Google Group.
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
  * Deploy Elasticsearch. From project root:
    ```
    cd kubernetes-elasticsearch-cluster
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
  * If you did the "Run Elasticsearch on GKE" step a while ago, run
    these commands to point `gcloud` and `kubectl` to the right project:
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
    * Make sure `deploy.json` and `dataset.json` `authorization_domain` are
      filled out.
  * From project root, run `bigquery/deploy/deploy-indexer.sh MY_DATASET`, where
  MY_DATASET is the name of the config directory in `dataset_config`.
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

## Developer tips

Determine what project/cluster `gcloud` and `kubectl` are currently configured
for.
```
gcloud config get-value project
kubectl config current-context
```
