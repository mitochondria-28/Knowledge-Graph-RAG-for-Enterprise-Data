# Project Phoenix — NovaSuite Data Layer Migration

## Project Overview

Project Phoenix is TechNova's internal engineering initiative to migrate the NovaSuite platform's primary data storage layer from the legacy relational database system to StellarDB. The project was initiated in Q3 2022, following the completion of StellarDB's deployment across TechNova's data centers.

Project Phoenix is owned by TechNova Corporation and is managed by the Platform Team under the leadership of Aisha Patel.

## Objectives

The primary objectives of Project Phoenix are:

1. Replace NovaSuite's legacy relational database with StellarDB as the primary transactional and analytical store.
2. Eliminate the architectural bottleneck that limits NovaSuite query throughput to approximately 12,000 queries per second.
3. Enable NovaSuite to support customer datasets larger than 10 terabytes, which the legacy system cannot accommodate.
4. Reduce data infrastructure costs by consolidating multiple specialized databases into a single StellarDB deployment.

## Technical Architecture

Project Phoenix introduces the following changes to NovaSuite's architecture:

**Primary data store:** StellarDB replaces the legacy PostgreSQL cluster as NovaSuite's primary database. All NovaSuite modules — financial reporting, supply chain, customer analytics, and operational dashboards — read from and write to StellarDB after the migration.

**Query layer:** All database access from NovaSuite application code is routed through TechNova's internal GraphQL Gateway. The Gateway translates GraphQL queries into optimized StellarDB query plans. This design ensures that NovaSuite application code is decoupled from the underlying database and can be migrated without changes to business logic.

**Container orchestration:** NovaSuite's application services are deployed on Kubernetes. Project Phoenix includes a migration of the NovaSuite deployment configuration to a new Kubernetes cluster topology that co-locates application services with their corresponding StellarDB shards for lower read latency.

**Replication:** StellarDB's multi-region replication relies on Apache Kafka for change data capture and log shipping between TechNova's three data centers.

## Leadership and Team

**Lisa Chen**, Senior Engineer at TechNova, is the technical lead for Project Phoenix. Chen joined TechNova in 2020 and previously worked on the NovaSuite query optimizer. She was selected to lead Project Phoenix due to her deep familiarity with NovaSuite's data access patterns and her collaborative relationship with the former Stellar Systems engineers who joined TechNova in 2022.

Chen reports to Aisha Patel, Head of the Platform Team. Priya Sharma, TechNova's Lead Architect and former Principal Architect at Stellar Systems, serves as a technical advisor to the project and is responsible for reviewing architectural decisions related to StellarDB usage.

The Platform Team owns Project Phoenix and is responsible for its ongoing execution, delivery, and maintenance.

## Current Status

As of Q1 2024, Project Phoenix is in active development. The migration of NovaSuite's financial reporting module to StellarDB has been completed and is running in production. Migration of the supply chain and customer analytics modules is underway.

The project is on track for full completion in Q4 2024, at which point NovaSuite will be fully powered by StellarDB with no remaining dependencies on the legacy relational database system.

## Dependencies

Project Phoenix depends on the following technologies:

- **StellarDB** — the target database system (originally developed by Stellar Systems, acquired by TechNova in 2022; currently maintained by the Platform Team)
- **GraphQL Gateway** — TechNova's internal query routing layer, developed and maintained by the Platform Team
- **Kubernetes** — container orchestration for NovaSuite's application services, managed by the DevOps Team
- **Apache Kafka** — event streaming for StellarDB replication, managed by the Data Engineering Team

## Risks

The primary risks identified by the Platform Team are:

1. Data consistency during the transition period when some NovaSuite modules are on the new StellarDB system and others remain on the legacy database.
2. Query performance for NovaSuite's most complex reporting queries, which were optimized for the legacy relational query planner and may require rewriting for StellarDB.
3. Operational readiness of the team to support StellarDB in production at scale.
