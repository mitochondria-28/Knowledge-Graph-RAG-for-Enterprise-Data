# TechNova Engineering Department — Organizational Structure

## Overview

The Engineering Department is TechNova's largest department, comprising approximately 900 engineers as of Q1 2024. The department is part of TechNova Corporation and reports to Marcus Thompson, Vice President of Engineering. Marcus Thompson reports directly to Dr. Elena Vasquez, Chief Technology Officer.

The Engineering Department is organized into three teams: the Platform Team, the Data Engineering Team, and the DevOps Team.

## Department Leadership

**Marcus Thompson** — Vice President of Engineering

Marcus Thompson joined TechNova in 2017 as Director of Infrastructure. He was promoted to VP of Engineering in 2020. Thompson manages the Engineering Department's three teams and is responsible for engineering hiring, technical roadmap execution, and cross-team coordination.

Thompson manages Aisha Patel, Sandra Müller, and Kevin Park, who are the leads of the three Engineering Department teams.

**Priya Sharma** — Lead Architect

Priya Sharma is TechNova's Lead Architect and reports to Dr. Elena Vasquez, CTO. Sharma joined TechNova from Stellar Systems, Inc. as part of TechNova's acquisition of Stellar Systems in February 2022. At Stellar Systems, she held the role of Principal Architect and was the primary designer of StellarDB's query optimizer and replication protocol.

At TechNova, Sharma's role is cross-functional: she reviews architectural decisions across all three Engineering Department teams and serves as a technical advisor to Project Phoenix and Project Nexus. She is not a team lead but is a senior individual contributor with broad technical authority.

## Platform Team

**Lead:** Aisha Patel — Head of Platform Team

The Platform Team is part of TechNova's Engineering Department. The team is responsible for TechNova's core infrastructure technologies:

- **StellarDB** — TechNova's primary distributed database (acquired from Stellar Systems in 2022; maintained by Platform Team)
- **GraphQL Gateway** — TechNova's internal query routing layer (developed by Platform Team; used by all NovaSuite product teams)

The Platform Team is the owner of Project Phoenix, the NovaSuite-to-StellarDB migration initiative. Lisa Chen, Senior Engineer on the Platform Team, is the technical lead for Project Phoenix.

The Platform Team is also the technical dependency point for any team that requires StellarDB or GraphQL Gateway changes. Teams building features that require new StellarDB query patterns or new GraphQL Gateway capabilities must submit requests to the Platform Team.

Aisha Patel reports to Marcus Thompson, VP of Engineering.

## Data Engineering Team

**Lead:** Sandra Müller — Engineering Manager, Data Engineering

The Data Engineering Team is part of TechNova's Engineering Department. The team is responsible for:

- **DataBridge ETL** — TechNova's internal ETL platform (developed and maintained by Data Engineering Team)
- **Apache Kafka** — TechNova's central event streaming cluster (operated by Data Engineering Team)
- Data pipeline development for internal data science and ML workloads
- Data quality monitoring and lineage tracking

The Data Engineering Team manages Project Nexus, the unified data platform initiative. Sandra Müller is the project manager for Project Nexus.

The team operates the Apache Kafka cluster that is shared by StellarDB's replication pipeline, DataBridge ETL, and ApexML. This makes the Data Engineering Team a critical infrastructure dependency for the Platform Team and the ML Team.

Sandra Müller reports to Marcus Thompson, VP of Engineering.

## DevOps Team

**Lead:** Kevin Park — DevOps Lead

The DevOps Team is part of TechNova's Engineering Department. The team is responsible for:

- **Kubernetes** — TechNova's container orchestration platform for all production services
- CI/CD pipeline management
- Infrastructure provisioning and cost management
- Production deployment support for all TechNova services

The DevOps Team provides Kubernetes infrastructure to Project Phoenix (NovaSuite application deployment), Project Atlas (ApexML inference services deployment), and Project Nexus (DataBridge ETL deployment).

Kevin Park reports to Marcus Thompson, VP of Engineering.

## Cross-Team Dependencies

The three teams within the Engineering Department have significant interdependencies:

| Consuming Team | Depending On | Providing Team |
|---|---|---|
| Platform Team | Apache Kafka (StellarDB replication) | Data Engineering Team |
| ML Team | Apache Kafka (ApexML feature ingestion) | Data Engineering Team |
| Platform Team | Kubernetes (StellarDB deployment) | DevOps Team |
| ML Team | Kubernetes (ApexML inference deployment) | DevOps Team |
| Data Engineering Team | Kubernetes (DataBridge ETL deployment) | DevOps Team |

This dependency structure means the Data Engineering Team (Kafka) and DevOps Team (Kubernetes) are foundational infrastructure providers for both the Platform Team and the ML Team.
