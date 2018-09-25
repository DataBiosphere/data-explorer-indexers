# Data explorer indexers

### Overview

This repo contains indexers which index a dataset into Elasticsearch, for
use by the [Data Explorer UI](https://github.com/DataBiosphere/data-explorer).

For each dataset, two Elasticsearch indices are created:

1. The main dataset index, named DATASET
1. The fields index, named DATASET_fields

#### Main dataset index

This index is used for faceted search.

Each Elasticsearch document represents a participant. The document id is participant id.  

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

#### Fields index

This index is used for field search. TODO: Include screenshot.

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

### One-time setup

[Set up git secrets.](https://github.com/DataBiosphere/data-explorer-indexers/tree/master/hooks)
