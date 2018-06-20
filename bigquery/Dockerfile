# When running this Dockerfile context must be project root, in order to pick
# up indexer_util.

FROM python:2

WORKDIR /app
COPY indexer_util /app/indexer_util
COPY bigquery/requirements.txt /app
RUN pip install -r /app/requirements.txt

COPY bigquery /app

CMD python indexer.py
