## Running on GKE

* For private datasets, determine readers Google Group.  
  Work with the Dataset owner to identity a Google Group of users with read-only
  access to the dataset.  
  * If you intend for users to work with your dataset in Terra, you must use
    Terra groups ([group management UI](https://app.terra.bio/#groups),
    [more info](https://software.broadinstitute.org/firecloud/documentation/article?id=9553)) for access control. Terra groups are automatically synced to a
    firecloud.org Google Group. For example, for Terra group foo:
      * Terra workspaces for your dataset will be shared to the Terra group foo.
      * Terra workspaces for your dataset must set [Authorization Domain](https://gatkforums.broadinstitute.org/firecloud/discussion/9524/authorization-domains)
      to Terra group foo. This ensures that only authorized users will see data sent
      from Data Explorer to Terra.
      * The Google Group foo@firecloud.org will be used for [restricting who can see
    Data Explorer](https://github.com/DataBiosphere/data-explorer/tree/master/deploy#enable-access-control).
* Set up the Kubernetes environment
  * Create a service account and give it access to the BigQuery tables for your
  dataset  
  [Following the principle of least privilege](https://cloud.google.com/kubernetes-engine/docs/tutorials/authenticating-to-cloud-platform#why_use_service_accounts),
  we recommend using a service account with only the necessary permissions,
  rather than the default Compute Engine service account (which has the Editor
  role).
    * Create a project for deploying Data Explorer. We recommend the project ID
      be `DATASET-explorer`. We recommend creating a
      project because all project Editors/Owners will indirectly have
      access to the BigQuery tables. (Project Editors/Owners by default have
      permission to act as service accounts, and the indexer service account will be
      given permission to read the BigQuery tables.)
      * Ensure that anyone who is
      granted Editor/Owner roles in this project, already has access to the BigQuery tables.
    * Create the service account
      * Navigate to `IAM & Admin > Service Accounts > Create Service Account`.
      * We recommend the name `indexer` to make it clear what this service account does.
        The full service account email would be `indexer@DATASET-explorer.iam.gserviceaccount.com`
      * Click `Create`
      * Add the `Storage > Storage Admin` role. This is for temporarily
      exporting BigQuery tables to GCS during indexing, reading
      docker images from GCR, and creating the sample export file.
      * Add the `BigQuery > BigQuery Job User` role. This allows the service
      account to run a BigQuery query, which takes place while indexing the
      BigQuery tables into Elasticsearch. Note that [this project will be billed](https://github.com/DataBiosphere/data-explorer-indexers/blob/master/bigquery/indexer.py#L131)
      for the BigQuery query, not the project containing the BigQuery tables.
      * Add the `Logging -> Logs Writer` role. This is needed for GKE logs to
      appear at https://console.cloud.google.com/logs/viewer
      * Click `Continue`
    * In the project with the BigQuery dataset, make the service account a
    BigQuery Data Viewer.
  * Create cluster
    * Go to https://console.cloud.google.com/kubernetes/list and click `Create Cluster`
    * Change name to `elasticsearch-cluster`
    * Set zone
      * If you have [deployed the UI server and/or API server](https://github.com/DataBiosphere/data-explorer/tree/master/deploy),
        select a zone in the same region as UI/API server. (Search for `Region`
        in the App Engine Dashbaord.)
      * If you not not yet deployed the UI/API servers, make a note what region
        your cluster is in. Later when you run `gcloud app create`, select this
        region. This is important because App Engine app regions cannot be
        changed after `gcloud app create`. (The Elasticsearch deployement uses
        [Internal Load Balancing](https://cloud.google.com/kubernetes-engine/docs/how-to/internal-load-balancing),
        so the API server will only be able to talk to Elasticsearch if it's in
        the same region.)
    * Change `Machine type` to `4 vCPUs`. (Otherwise will get Insufficient CPU error.)  
    If you need more memory for Elasticsearch, you may need `n1-highmem-4`. [Elasticsearch recommends](https://www.elastic.co/guide/en/elasticsearch/reference/current/heap-size.html) the VM has at least
    twice the memory you are using for Elasticsearch.
    * Click `Advanced edit` and under `Service account`, select the indexer service account you just created. Click `Save`.
      * If you are using the default Compute service account instead of indexer,
        click `Allow full access to all Cloud APIs`.
    * Click `Create`.
  * After cluster has finished creating, run this command to point `kubectl` to
  the right cluster.
    ```
    gcloud config set project EXPLORER_PROJECT
    gcloud container clusters get-credentials elasticsearch-cluster --zone MY_ZONE
    ```
    `MY_ZONE` is the [zone where elasticsearch-cluster is running](https://console.cloud.google.com/kubernetes/list),
    e.g. `us-central1-a`.

* Run Elasticsearch on GKE
  * Deploy Elasticsearch. From project root:
    ```
    kubernetes-elasticsearch-cluster/deploy.sh MY_DATASET
    ```
    Note: This will delete all existing data in the index; re-deploy 
    with caution.
  * Test that Elasticsearch is up. ES_CLIENT_POD is something like
  `es-client-595585f9d4-7jw9v`.
    ```
    kubectl get pods
    kubectl exec -it ES_CLIENT_POD -- /bin/bash
    curl localhost:9200
    ```

* Update and run indexer on GKE
  * If you did the "Run Elasticsearch on GKE" step a while ago, run
    these commands to point `gcloud` and `kubectl` to the right project.
    ```
    # See what projects gcloud and kubectl are configured for
    gcloud config get-value project
    kubectl config current-context
    # Point gcloud and kubetl to the right project
    gcloud config set project MY_PROJECT
    gcloud container clusters get-credentials elasticsearch-cluster --zone MY_ZONE
    ```
    `MY_ZONE` is the [zone where elasticsearch-cluster is running](https://console.cloud.google.com/kubernetes/list),
    e.g. `us-central1-a`.
  * We recommend you delete the index, to start from a clean slate.
    ```
    kubectl get pods
    kubectl exec -it ES_CLIENT_POD -- /bin/bash
    curl -XDELETE localhost:9200/<MY_DATASET>
    curl -XDELETE localhost:9200/<MY_DATASET>_fields
    ```
  * Make sure the files in `dataset_config/MY_DATASET` are filled out.
    * Make sure `deploy.json` and the `authorization_domain` field in
      `dataset.json` are filled out.
  * From project root, run `bigquery/deploy/deploy-indexer.sh MY_DATASET`, where
  MY_DATASET is the name of the config directory in `dataset_config`.
  * Verify the indexer was successful:
    ```
    kubectl get pods
    kubectl exec -it ES_CLIENT_POD -- /bin/bash
    curl localhost:9200/_cat/indices?v
    ```
