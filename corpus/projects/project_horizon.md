# Project Horizon — Customer-Facing Analytics Dashboard

## Project Overview

Project Horizon is TechNova's initiative to build a next-generation customer-facing analytics dashboard within NovaSuite. The goal is to replace NovaSuite's existing static reporting views with an interactive, self-service analytics experience.

Project Horizon is managed by TechNova's Frontend Team and is owned by TechNova Corporation.

## Objectives

1. Deliver an interactive analytics dashboard embedded within NovaSuite that customers can use without training.
2. Support custom dashboard configurations per customer, persisted in NovaSuite's settings store.
3. Integrate with NovaSuite Analytics to expose AI-generated insights alongside traditional metrics.
4. Replace legacy static report generation with real-time query results.

## Technical Architecture

**Frontend:** Project Horizon's dashboard is a React-based single-page application embedded within NovaSuite's web interface.

**Data access:** The Horizon dashboard sends all data queries through TechNova's GraphQL Gateway. The GraphQL Gateway routes queries to StellarDB for operational data and to ApexML for AI-generated insights from Project Atlas.

**NovaSuite Analytics dependency:** Project Horizon depends on NovaSuite Analytics for its AI insights layer. NovaSuite Analytics is the module that exposes the ML model outputs from Project Atlas as customer-visible metrics.

**Authentication and permissions:** Dashboard access and data visibility are controlled by NovaSuite's existing permission model, enforced at the GraphQL Gateway layer.

## Leadership

The Frontend Team is responsible for Project Horizon. The Frontend Team is part of TechNova's Engineering Department.

Project Horizon is coordinated with Project Atlas (which provides the ML-powered insights that Horizon displays) and with Project Phoenix (which ensures the underlying StellarDB data is available with the performance characteristics that Horizon requires for real-time queries).

## Dependencies

- **GraphQL Gateway** — primary data access layer, routes queries to StellarDB and ApexML
- **NovaSuite Analytics** — provides AI-powered insights from Project Atlas
- **StellarDB** — underlying operational data store (via GraphQL Gateway)

## Current Status

Project Horizon is in early development as of Q1 2024. The dashboard framework and GraphQL integration are complete. Data visualization components are in development. Customer pilot rollout is planned for Q4 2024 alongside the full completion of Project Phoenix.
