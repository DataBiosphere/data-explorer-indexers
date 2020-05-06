"""Utilities for Data Explorer indexers"""

import jsmin
import json
import logging
import os
import time
import multiprocessing
from multiprocessing import Pool, TimeoutError

from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ConnectionError
from elasticsearch.helpers import parallel_bulk, bulk

from collections import deque

# Log to stderr.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(filename)10s:%(lineno)s %(levelname)s %(message)s',
    datefmt='%Y%m%d%H:%M:%S')
logger = logging.getLogger('indexer.util')

ES_TIMEOUT_SEC = 20


def parse_json_file(json_path):
    """Opens and returns JSON contents.

  Args:
    json_path: Relative or absolute path of JSON file

  Returns:
    Parsed JSON
  """
    with open(json_path, 'r') as f:
        # Remove comments using jsmin, as recommended by JSON creator
        # (https://plus.google.com/+DouglasCrockfordEsq/posts/RK8qyGVaGSr).
        jsonDict = json.loads(jsmin.jsmin(f.read()))
        return jsonDict


# Keep in sync with convert_to_index_name() in data-explorer repo.
def _convert_to_index_name(s):
    """Converts a string to an Elasticsearch index name."""
    # For Elasticsearch index name restrictions, see
    # https://github.com/DataBiosphere/data-explorer-indexers/issues/5#issue-308168951
    # Elasticsearch allows single quote in index names. However, they cause other
    # problems. For example,
    # "curl -XDELETE http://localhost:9200/nurse's_health_study" doesn't work.
    # So also remove single quotes.
    prohibited_chars = [
        ' ', '"', '*', '\\', '<', '|', ',', '>', '/', '?', '\''
    ]
    for char in prohibited_chars:
        s = s.replace(char, '_')
    s = s.lower()
    # Remove leading underscore.
    if s.find('_', 0, 1) == 0:
        s = s.lstrip('_')
    print('Index name: %s' % s)
    return s


def get_index_name(dataset_config_dir):
    json_path = os.path.join(dataset_config_dir, 'dataset.json')
    dataset_name = parse_json_file(json_path)['name']
    return _convert_to_index_name(dataset_name)


def _wait_elasticsearch_healthy(es):
    """Waits for Elasticsearch to be healthy.

    Args:
        es: An Elasticsearch instance.
    """
    # Don't print NewConnectionError's while we're waiting for Elasticsearch
    # to come up.
    start = time.time()
    logging.getLogger("elasticsearch").setLevel(logging.ERROR)
    for _ in range(0, ES_TIMEOUT_SEC):
        try:
            es.cluster.health(wait_for_status='yellow')
            print('Elasticsearch took %d seconds to come up.' %
                  (time.time() - start))
            break
        except ConnectionError:
            print('Elasticsearch not up yet, will try again.')
            time.sleep(1)
    else:
        raise EnvironmentError("Elasticsearch failed to start.")
    logging.getLogger("elasticsearch").setLevel(logging.INFO)


def get_es_client(elasticsearch_url):
    # Retry flags needed for large datasets.
    es = Elasticsearch([elasticsearch_url],
                       retry_on_timeout=True,
                       max_retries=10,
                       timeout=300)

    _wait_elasticsearch_healthy(es)
    return es


def maybe_create_elasticsearch_index(es, elasticsearch_url, index_name):
    """Creates Elasticsearchindex if it doesn't already exist."""

    if es.indices.exists(index=index_name):
        logger.info('Using existing %s index at %s.' %
                    (index_name, elasticsearch_url))
    else:
        logger.info('Creating %s index at %s.' %
                    (index_name, elasticsearch_url))
        es.indices.create(
            index=index_name,
            body={
                'settings': {
                    # Default of 1000 fields is not enough for some datasets
                    'index.mapping.total_fields.limit': 1000000,
                    'index.number_of_shards': 50,
                },
            })


def _prepare_for_indexing(es):
    # Temporarily Update the settings to temporarily optimize for write-heavy performance.
    es.indices.put_settings(
        {
            'index.refresh_interval': '-1',
            'index.number_of_replicas': 0,
            'index.translog.durability': 'async',
            'index.translog.flush_threshold_size': '2048MB',
            'index.mapping.total_fields.limit': 1000000
        }
    )


def _complete_indexing(es):
    es.indices.put_settings({
        'index.refresh_interval': '1s',
        'index.number_of_replicas': 1,
        'index.translog.durability': 'request',
    }
    )


def bulk_index_scripts(es, index_name, scripts_by_id):
    # Use generator so we can index arbitrarily large iterators (like tables),
    # without having to load into memory.
    def es_actions(scripts_by_id):
        for _id, script in scripts_by_id:
            yield ({
                '_op_type': 'update',
                '_index': index_name,
                # type will go away in future versions of Elasticsearch. Just
                # use any string here.
                '_type': 'type',
                '_id': _id,
                'scripted_upsert': True,
                'script': script,
                'upsert': {},
            })

    _prepare_for_indexing(es)
    # For large datasets, the default timeout of 10s is sometimes not enough.
    bulk(es, es_actions(scripts_by_id), request_timeout=1200)
    _complete_indexing(es)

def split_dict_equally(input_dict, chunks=20):
    "Splits dict by keys. Returns a list of dictionaries."
    # prep with empty dicts
    return_list = [dict() for idx in xrange(chunks)]
    idx = 0
    for k in input_dict.keys():
        return_list[idx][k] = input_dict[k]
        if idx < chunks-1:  # indexes start at 0
            idx += 1
        else:
            idx = 0
        del input_dict[k]
    return return_list

def bulk_index_scripts_in_parallel(elasticsearch_ip, index_name, docs_by_id):
    es = Elasticsearch(elasticsearch_ip, timeout=300)
    num_threads = multiprocessing.cpu_count()
    #num_threads = 50
    pool = Pool(processes=num_threads)
    dicts = split_dict_equally(docs_by_id, chunks=num_threads)
    results = []
    _prepare_for_indexing(es)
    for d in dicts:
        #print(d)
        results.append(pool.apply_async(bulk_index_scripts_in_parallel_helper, (elasticsearch_ip, index_name, d)))
    for res in results:
        res.wait(timeout=600)
    logger.info('CLosing the pool')
    pool.close()
    pool.join()
    logger.info('Pool is closed.')
    _complete_indexing(es)

def bulk_index_scripts_in_parallel_helper(elasticsearch_ip, index_name, scripts_by_id):
    # Use generator so we can index arbitrarily large iterators (like tables),
    # without having to load into memory.
    es = Elasticsearch(elasticsearch_ip, timeout=300)
    def es_actions(scripts_by_id):
        for _id, script in scripts_by_id.iteritems():
            yield ({
                '_op_type': 'update',
                '_index': index_name,
                # type will go away in future versions of Elasticsearch. Just
                # use any string here.
                '_type': 'type',
                '_id': _id,
                'scripted_upsert': True,
                'script': script,
                'upsert': {},
            })

    # For large datasets, the default timeout of 10s is sometimes not enough.
    bulk(es, es_actions(scripts_by_id), request_timeout=1200, filter_path='-*')

def bulk_index_docs_in_parallel(elasticsearch_ip, index_name, docs_by_id):
    es = Elasticsearch(elasticsearch_ip, timeout=300)
    num_threads = multiprocessing.cpu_count() 
    #num_threads = 50
    pool = Pool(processes=num_threads)
    dicts = split_dict_equally(docs_by_id, chunks=num_threads)
    results = []
    _prepare_for_indexing(es)
    for d in dicts:
        #print(d)
        results.append(pool.apply_async(bulk_index_docs_in_parallel_helper, (elasticsearch_ip, index_name, d)))
    for res in results:
        res.wait(timeout=600)
    logger.info('CLosing the pool')
    pool.close()
    pool.join()
    logger.info('Pool is closed.')
    _complete_indexing(es)
    
def bulk_index_docs_in_parallel_helper(elasticsearch_ip, index_name, docs_by_id):
    es = Elasticsearch(elasticsearch_ip, timeout=300)
    def es_actions(docs_by_id):
        for _id, doc in docs_by_id.iteritems():
            yield ({
                '_op_type': 'update',
                '_index': index_name,
                # type will go away in future versions of Elasticsearch. Just
                # use any string here.
                '_type': 'type',
                '_id': _id,
                'doc': doc,
                'doc_as_upsert': True
            })
    bulk(es, es_actions(docs_by_id), request_timeout=1800, filter_path='-*')

def bulk_index_docs(es, index_name, docs_by_id):
    # Use generator so we can index arbitrarily large iterators (like tables),
    # without having to load into memory.
    def es_actions(docs_by_id):
        for _id, doc in docs_by_id:
            yield ({
                '_op_type': 'update',
                '_index': index_name,
                # type will go away in future versions of Elasticsearch. Just
                # use any string here.
                '_type': 'type',
                '_id': _id,
                'doc': doc,
                'doc_as_upsert': True
            })

    _prepare_for_indexing(es)
    # For large datasets, the default timeout of 10s is sometimes not enough.
    deque(parallel_bulk(es, es_actions(docs_by_id), request_timeout=1200, chunk_size=10000, max_chunk_bytes=10485760000, thread_count=50), maxlen=0)
    _complete_indexing(es)
