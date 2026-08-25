# StellarDB — Technical Architecture Reference

## Overview

StellarDB is a distributed, column-oriented database system designed for high-throughput analytical workloads across horizontally sharded clusters. It was originally developed by Stellar Systems Inc., which was acquired by TechNova Corporation in February 2022. Since the acquisition, StellarDB has been maintained and developed by TechNova's Platform Team under the leadership of Aisha Patel.

StellarDB is the primary database system for TechNova's NovaSuite platform. All NovaSuite transactional and analytical data is stored in StellarDB as of Q3 2022, following the completion of Project Phoenix's initial migration phases.

## Core Design Principles

StellarDB was designed around three principles established by its original engineering team at Stellar Systems:

**1. Analytical-first storage:** StellarDB uses a columnar storage format that optimizes for read-heavy analytical queries over wide tables. Columns are stored together on disk, enabling efficient compression and vectorized execution for aggregation queries.

**2. Horizontal sharding:** Data is partitioned across shards based on a configurable sharding key. Each shard is an independent StellarDB node that handles queries against its partition of the data. The query coordinator routes incoming queries to the appropriate shards and merges results.

**3. Streaming replication:** StellarDB uses Apache Kafka for both inter-shard replication and multi-region data synchronization. Write operations are published as Kafka messages and consumed by replica shards in the same cluster and by cross-datacenter standby clusters. This design makes StellarDB's replication pipeline composable with other Kafka-based systems, such as TechNova's DataBridge ETL and ApexML's feature ingestion pipelines.

## Query Interface

StellarDB is not accessed directly by application code at TechNova. All queries are routed through TechNova's GraphQL Gateway, which translates GraphQL queries into StellarDB Query Language (SDQL) statements. The Gateway handles:

- Query parsing and validation
- Query routing to the appropriate StellarDB shards
- Access control enforcement
- Query result caching

The GraphQL Gateway was developed by TechNova's Platform Team and is also maintained by the Platform Team. It serves as the single query interface for all TechNova products that interact with StellarDB.

## Replication Architecture

StellarDB's replication architecture, as deployed at TechNova, operates as follows:

1. Write requests arrive at the StellarDB primary coordinator.
2. The coordinator writes the operation to a Kafka topic maintained by TechNova's Data Engineering Team.
3. Replica shards in the same cluster consume from this Kafka topic and apply the write.
4. Cross-datacenter standby clusters in TechNova's London and Singapore data centers also consume from the same Kafka replication topic, providing geographic redundancy.

This Kafka-based replication design means StellarDB shares its event streaming infrastructure with ApexML (which also consumes Kafka topics for ML feature updates) and with DataBridge ETL (which reads StellarDB change events for ETL processing). All three systems consume from the same Apache Kafka cluster, managed by TechNova's Data Engineering Team.

## Maintenance and Operations

The Platform Team at TechNova is the owner of StellarDB in production. The team's responsibilities include:

- StellarDB version upgrades and patch management
- Cluster scaling and shard rebalancing
- Query performance tuning
- On-call support for StellarDB incidents
- Development of new StellarDB features requested by TechNova's product teams

Aisha Patel, Head of the Platform Team, is the primary operational owner of StellarDB at TechNova. Priya Sharma, TechNova's Lead Architect and former Principal Architect at Stellar Systems, is the authority on StellarDB's internal design and reviews all significant architectural changes to StellarDB's deployment at TechNova.

## Projects Using StellarDB

The following active TechNova projects depend on StellarDB:

- **Project Phoenix** — the initiative responsible for NovaSuite's full migration to StellarDB
- **Project Nexus** — uses StellarDB as the primary store in TechNova's unified data platform
- **Project Horizon** — accesses NovaSuite data stored in StellarDB via the GraphQL Gateway

## Known Limitations

StellarDB's analytical-first design introduces trade-offs for high-frequency, low-latency transactional write workloads. The Platform Team is evaluating a hybrid storage model that combines StellarDB's columnar analytical store with a separate row-oriented write-ahead log for high-throughput transactional writes. This is a planned enhancement for the StellarDB roadmap and is not yet in production at TechNova.
