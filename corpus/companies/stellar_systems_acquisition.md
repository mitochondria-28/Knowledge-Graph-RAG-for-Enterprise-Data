# TechNova Acquires Stellar Systems — Acquisition Overview

## Transaction Summary

TechNova Corporation completed the acquisition of Stellar Systems Inc. on February 14, 2022. The total transaction value was approximately $340 million, comprising $295 million in cash and $45 million in TechNova restricted stock units. The acquisition was approved by the boards of both companies in December 2021 and received regulatory clearance in January 2022.

## About Stellar Systems

Stellar Systems Inc. was a privately held data infrastructure company founded in Seattle, Washington in 2015. The company was founded by a team of former database engineers from Amazon Web Services and Microsoft Research, with a mission to build distributed database systems capable of handling real-time analytical workloads at petabyte scale.

Stellar Systems' primary product was **StellarDB**, a distributed, column-oriented database designed for high-throughput analytical queries across horizontally sharded clusters. StellarDB supported multi-region replication using Apache Kafka as its underlying event streaming layer. At the time of acquisition, StellarDB had been deployed by more than 180 enterprise customers.

Stellar Systems employed approximately 220 people at the time of the acquisition, primarily engineers and customer success staff based in Seattle.

## Strategic Rationale

TechNova's then-CTO Dr. Elena Vasquez described the acquisition rationale in an internal memo circulated to engineering leadership:

> "TechNova's legacy PostgreSQL-based infrastructure served us well through our first decade, but we are approaching the architectural limits of what a traditional relational system can support. Stellar Systems has built exactly the kind of distributed, analytically-oriented database that our NovaSuite platform needs to scale to the next generation of customer workloads. Bringing StellarDB in-house gives us full control over our data layer and eliminates a critical external dependency."

## Key Personnel Transitions

Following the acquisition, several Stellar Systems engineers joined TechNova in senior roles:

**Priya Sharma**, previously Stellar Systems' Principal Architect, joined TechNova as Lead Architect within the Engineering Department. Sharma is credited as the primary designer of StellarDB's query optimizer and replication protocol. At TechNova, she has been responsible for integrating StellarDB into the NovaSuite platform and leading Project Phoenix, the internal initiative to migrate NovaSuite's data layer to StellarDB.

Two additional senior engineers from Stellar Systems joined TechNova's Platform Team, which assumed ownership of StellarDB operations and ongoing development after the acquisition closed.

## Post-Acquisition Integration

StellarDB integration into TechNova's infrastructure was managed by the Platform Team under Aisha Patel. The integration involved:

1. Migrating NovaSuite's transactional data storage from the legacy relational system to StellarDB
2. Establishing Kafka-based replication pipelines to synchronize StellarDB clusters across TechNova's data centers in Austin, London, and Singapore
3. Developing internal tooling to allow TechNova's product teams to query StellarDB through TechNova's GraphQL Gateway

By Q3 2022, StellarDB had been deployed across all three of TechNova's primary data centers and was handling production traffic for NovaSuite.

## Current Status

As of 2024, Stellar Systems operates as a wholly owned subsidiary of TechNova Corporation. The Stellar Systems brand has been retained for external communications regarding StellarDB, though engineering operations are fully integrated into TechNova's Engineering Department. The Platform Team at TechNova maintains StellarDB and is responsible for all ongoing development, bug fixes, and customer support related to the database.

Apache Kafka continues to serve as the event streaming backbone for StellarDB's replication and change data capture pipelines.
