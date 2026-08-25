# DataBridge ETL — Internal ETL Platform

## Overview

DataBridge ETL is TechNova's internally developed data extraction, transformation, and loading platform. It is the primary tool used by TechNova's Data Engineering Team to build and operate data pipelines that move and transform data between TechNova's internal systems.

DataBridge ETL was developed entirely by TechNova Corporation and is maintained by the Data Engineering Team under Sandra Müller.

## Purpose and Scope

DataBridge ETL serves as the data movement layer between TechNova's operational systems. Its primary responsibilities are:

- Reading change events from StellarDB via Apache Kafka (change data capture)
- Transforming raw operational data into ML features for ApexML's feature store
- Loading transformed data into downstream systems including ApexML, TechNova's data warehouse, and external reporting tools
- Providing pipeline monitoring, data quality checks, and alerting

Without DataBridge ETL, StellarDB and ApexML would be isolated systems with no automated data flow between them. DataBridge ETL is the critical bridge that makes Project Nexus possible.

## Technical Design

DataBridge ETL is built on Apache Kafka as its event streaming backbone. The platform operates as a set of Kafka Streams applications and standalone consumers:

**Kafka consumers:** DataBridge ETL workers consume change events published by StellarDB's replication pipeline to Apache Kafka topics. Each event represents an insert, update, or delete in a StellarDB table.

**Transformations:** Consumed events are processed through configurable transformation pipelines. Transformations include:
- Field filtering and renaming
- Type casting and normalization
- Aggregation (rolling windows, cumulative sums)
- Enrichment by joining with reference data from StellarDB

**Kafka producers:** After transformation, DataBridge ETL publishes the transformed records to output Kafka topics that are consumed by downstream systems. ApexML's feature store consumes from these output topics to update ML features.

## Role in TechNova's Architecture

DataBridge ETL is the connective tissue between TechNova's two core technology platforms:

```
StellarDB → (Kafka CDC events) → DataBridge ETL → (Kafka feature events) → ApexML
```

This pipeline makes it possible for ApexML to have continuously updated ML features derived from NovaSuite's operational data in StellarDB, enabling real-time model serving for NovaSuite's AI features.

DataBridge ETL is a dependency of Project Nexus, which relies on it for all StellarDB-to-ApexML data synchronization.

## Operational Ownership

The Data Engineering Team, led by Sandra Müller, owns DataBridge ETL. The team develops new pipeline configurations as requested by product teams and ML engineers. DataBridge ETL is part of TechNova's core infrastructure and is considered a tier-1 system, meaning incidents affecting DataBridge ETL pipelines are escalated to the on-call team immediately.

Apache Kafka, which DataBridge ETL depends on, is also managed by the Data Engineering Team. The team operates TechNova's central Kafka cluster, which is shared by StellarDB replication, DataBridge ETL, and ApexML.
