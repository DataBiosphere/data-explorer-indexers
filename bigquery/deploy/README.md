## Running on GKE

For a Kubernetes cluster running an externally or internally exposed elasticsearch
instance, the bigquery indexer can be run as a Kubernetes job as follows:

1. Build, tag, and upload the base docker image to GCR:
    ```
    docker build -t gcr.io/PROJECT_ID/es-indexer-base ..
    docker push gcr.io/PROJECT_ID/es-indexer-base:latest
    ```
2. Pull this repository into a properly configured and authenticated console (e.g. GCP
console) and update `indexer-job.yaml` with the desired MY_GOOGLE_CLOUD_PROJECT,
LOAD_BALANCER_IP and CONFIG_DIR.
3. [Using steps 3-5 as a reference,](https://cloud.google.com/kubernetes-engine/docs/tutorials/authenticating-to-cloud-platform#step_3_create_service_account_credentials)
create a secret named `indexer-key` for the Compute Engine service account private
key so that the service account can access BigQuery.
4. Generate a configmap for the indexer:
    ```
    kubectl create configmap indexer --from-file=../indexer.py
    ```
5. Run the job:
    ```
    kubectl create -f indexer-job.yaml
    ```
6. Verify the indexer was successful:
    ```
    kubectl get pods -a
    kubectl logs bq-indexer-xxxxx
    ```