# When running this Dockerfile context must be project root, in order to pick
# up indexer_util and dataset_config

FROM python:2

WORKDIR /app
COPY indexer_util /app/indexer_util
COPY bigquery/requirements.txt /app
RUN pip install -r /app/requirements.txt

COPY dataset_config /app/dataset_config
COPY bigquery /app

COPY tls.crt /app

CMD python indexer.py
