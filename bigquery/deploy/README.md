## Running on GKE

* Run Elasticsearch on GKE
  * ```
  git clone https://github.com/pires/kubernetes-elasticsearch-cluster.git
  cd kubernetes-elasticsearch-cluster
  ```
  * Set up [Internal Load Balancer](https://cloud.google.com/kubernetes-engine/docs/how-to/internal-load-balancing). Note: This is not needed for indexing. This will be needed for having API server on App Engine Flex talk to Elasticsearch in GKE; might as well set up now. Change `es-svc.yaml` to:
    ```
    apiVersion: v1
    kind: Service
    metadata:
      name: elasticsearch
      labels:
        component: elasticsearch
        role: client
      annotations:
        cloud.google.com/load-balancer-type: "Internal"
    spec:
      selector:
        component: elasticsearch
        role: client
      ports:
      - name: http
        port: 9200
      type: LoadBalancer
    ```
  * Create cluster
    * Go to https://console.cloud.google.com/kubernetes/list and click `Create Cluster`
    * Change name to `elasticsearch-cluster`
    * Change `Machine type` to `4 vCPUs`. (Otherwise will get Insufficient CPU error.)
    * Expand `More` -> Click on `Set access for each API` -> Change `BigQuery` to enabled.
    * Click `Create`
  * In terminal, run:
    ```
    gcloud container clusters get-credentials elasticsearch-cluster
    ```
  This will make `kubectl` use this cluster.
  * Run [kubectl commands](https://github.com/pires/kubernetes-elasticsearch-cluster#deploy)
  * Test that Elasticsearch is up
    ```
    kubectl get svc,pods
    kubectl ES_CLIENT_POD exec -it  -- /bin/bash
    curl EXTERNAL_IP:9200
    ```

* Run indexer on GKE
  * If you are using the default [platinum_genomes dataset](https://github.com/DataBiosphere/data-explorer-indexers/tree/master/bigquery/config/platinum_genomes), don't forget to set project IDs in [facet_fields.csv](https://github.com/DataBiosphere/data-explorer-indexers/blob/master/bigquery/config/platinum_genomes/facet_fields.csv).
  * Build, tag, and upload the base docker image to GCR:
    ```
    docker build -t gcr.io/PROJECT_ID/bq-indexer ..
    docker push gcr.io/PROJECT_ID/bq-indexer
    ```
  * Update `bq-indexer.yaml` with the desired MY_GOOGLE_CLOUD_PROJECT,
  LOAD_BALANCER_IP and CONFIG_DIR.
  * Run the indexer:
    ```
    kubectl create configmap dataset-config --from-file=DATASET_CONFIG_DIR
    kubectl create -f bq-indexer.yaml
    ```
  * Verify the indexer was successful:
    ```
    kubectl get svc,pods
    kubectl ES_CLIENT_POD exec -it  -- /bin/bash
    curl EXTERNAL_IP:9200/_cat/indices?v
    ```
