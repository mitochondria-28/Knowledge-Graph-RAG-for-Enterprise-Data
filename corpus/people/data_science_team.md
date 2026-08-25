# TechNova Data Science Department — Team Overview

## Overview

TechNova's Data Science Department is led by James Okafor, who holds the title of Director of Data Science. The department is separate from the Engineering Department and reports directly to Dr. Elena Vasquez, CTO of TechNova Corporation.

The Data Science Department includes the ML Team, which is responsible for the ApexML platform and all machine learning workloads within TechNova.

## Department Leadership

**James Okafor** — Director of Data Science

James Okafor joined TechNova in 2021 from a Senior Data Scientist role at a financial services firm. He was hired to build TechNova's data science capability from the ground up. Under his leadership, TechNova's data science team has grown from four people to more than 60 engineers and data scientists.

Okafor manages the ML Team and oversees all ML initiatives at TechNova, including Project Atlas. He works closely with Marcus Thompson, VP of Engineering, to coordinate between the Data Science Department and the Engineering Department on shared infrastructure projects such as Project Nexus.

Okafor reports to Dr. Elena Vasquez, CTO.

## ML Team

The ML Team is part of TechNova's Data Science Department. The team is responsible for:

- **ApexML** — TechNova's ML platform (acquired from Apex Analytics in 2023; maintained by ML Team)
- Machine learning model development for NovaSuite Analytics features
- Feature engineering in ApexML's feature store
- ML model monitoring and retraining in production

The ML Team is the owner of Project Atlas, TechNova's initiative to integrate ApexML into NovaSuite's AI features.

**David Reyes** — Senior ML Engineer, Project Atlas Lead

David Reyes joined TechNova from Apex Analytics as part of the August 2023 acquisition. At Apex Analytics, Reyes was the Director of Engineering and the lead designer of ApexML's feature store and model serving infrastructure.

At TechNova, Reyes leads Project Atlas as the technical project lead and is the primary technical owner of the ApexML platform. He reports to James Okafor, Director of Data Science.

Reyes collaborates closely with the Platform Team (which provides the GraphQL Gateway that routes inference requests to ApexML) and the Data Engineering Team (which operates the Kafka infrastructure and DataBridge ETL pipelines that feed data into ApexML's feature store).

## Cross-Department Collaboration

The Data Science Department depends on the Engineering Department for several critical infrastructure capabilities:

- **Apache Kafka** (provided by Data Engineering Team): ApexML's training and real-time feature pipelines consume from Kafka topics managed by the Data Engineering Team.
- **Kubernetes** (provided by DevOps Team): ApexML's inference serving layer runs on Kubernetes clusters managed by the DevOps Team.
- **GraphQL Gateway** (provided by Platform Team): Inference requests from NovaSuite are routed through the GraphQL Gateway before reaching ApexML.
- **DataBridge ETL** (provided by Data Engineering Team): The DataBridge pipelines transform StellarDB data into ML features for ApexML's feature store.

This cross-departmental dependency structure is a key reason why Project Nexus — which integrates StellarDB, ApexML, and DataBridge ETL — requires coordination across both the Engineering Department and the Data Science Department.
