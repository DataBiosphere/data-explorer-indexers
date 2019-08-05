# Data explorer indexers

### Overview

This repo contains indexers which index a dataset into Elasticsearch, for
use by the [Data Explorer UI](https://github.com/DataBiosphere/data-explorer).

For each dataset, two Elasticsearch indices are created:

1. The main dataset index, named DATASET
1. The fields index, named DATASET_fields

The indexers create a facet for each variable in your dataset for faceted search, for example:

![Super Population facet](https://i.imgur.com/qSmeD4l.png)

### Main dataset index

This index is used for faceted search.

Each Elasticsearch document represents a participant. The document id is participant id.  

### Fields index

This index is used for the search box:

![Screenshot of search box](https://i.imgur.com/A595p69.png)

Each document represents a field. The document id is name of the
Elasticsearch field from the main dataset index. Example fields
are age, gender, etc. Here's an example document from `1000_genomes_fields`:
```
"_id" : "samples.verily-public-data.human_genome_variants.1000_genomes_sample_info.In_Low_Coverage_Pilot",
"_source" : {
  "name" : "In_Low_Coverage_Pilot",
  "description" : "The sample is in the low coverage pilot experiment"
}
```
(We need a separate index because there's no place to put BigQuery column
descriptions in the main index.)

### Sample file support

If your dataset includes sample files (VCF, BAM, etc), Data Explorer facets can show sample count, instead of participant count. See the [1000 Genomes Data Explorer](https://test-data-explorer.appspot.com). (Look for facets with `(samples)` in the name.)

A participant can have
zero or more samples. Within a participant document, a sample is a
[nested object](https://www.elastic.co/guide/en/elasticsearch/reference/current/nested.html#_using_literal_nested_literal_fields_for_arrays_of_objects). Each nested object has a `sample_id` field.

Participant fields are in the top-level participant document. Sample fields are in the nested sample objects. For example, here's an excerpt of a `1000_genomes`
document:

```
"_id" : "NA12003",
"_source" : {
  "verily-public-data.human_genome_variants.1000_genomes_participant_info.Super_Population" : "EUR",
  "verily-public-data.human_genome_variants.1000_genomes_participant_info.Gender" : "male",
  "samples" : [
    {
      "sample_id" : "HG02924",
      "verily-public-data.human_genome_variants.1000_genomes_sample_info.In_Low_Coverage_Pilot" : true
      "verily-public-data.human_genome_variants.1000_genomes_sample_info.chr_18_vcf" : "gs://genomics-public-data/1000-genomes-phase-3/vcf-20150220/ALL.chr18.phase3_shapeit2_mvncall_integrated_v5a.20130502.genotypes.vcf",
    }
  ],
}
```

### Time series support

If your dataset contains longitudinal data, Data Explorer can show time series visualizations. See the [Framingham Heart Study Teaching Dataset Data Explorer](https://time-series-data-explorer.appspot.com).

![Time series facet](https://i.imgur.com/2AgdKBY.png)

For example, here's an excerpt of a `framingham_heart_study_teaching` document with time series data for two participant fields:

```
"_id" : "68397",
"_source" : {
  "verily-public-data.framingham_heart_study_teaching.framingham_heart_study_teaching.GLUCOSE" : {
    "1" : "79",
    "2" : "78",
    "3" : "110"
  },
  "verily-public-data.framingham_heart_study_teaching.framingham_heart_study_teaching.HEARTRTE" : {
    "1" : "86",
    "2" : "60",
    "3" : "80"
  }
}
```

### One-time setup

[Set up git secrets.](https://github.com/DataBiosphere/data-explorer-indexers/tree/master/hooks)
