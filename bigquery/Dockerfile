# A base image wrapping together all dependencies on which the indexer can
# be executed as a script
FROM gcr.io/google-appengine/python

RUN virtualenv ~/virtualenv/indexer-bigquery -p python2.7
ENV VIRTUAL_ENV /virtualenv/indexer-bigquery
ENV PATH /virtualenv/indexer-bigquery/bin:$PATH
ADD . /app
RUN pip install -r /app/requirements.txt