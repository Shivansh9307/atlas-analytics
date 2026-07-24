# Atlas v2: Data Quality Copilot & Analytics Operating System
**Version:** 2.0 (Draft)
**Status:** Design Specification
**Owner:** Shivansh Chauhan
**Audience:** Engineering, AI Platform, Data Engineering, Analytics

---

# Vision

Atlas should evolve from an AI-powered analytics workflow into an **Enterprise AI Analytics Operating System**.

Instead of only answering business questions, Atlas should become responsible for ensuring that every answer is built on trusted, validated, explainable, and governed data.

Atlas should feel like an entire analytics department:

- Chief Analytics Officer
- Data Quality Engineer
- Data Steward
- BI Analyst
- Data Analyst
- Statistician
- Root Cause Analyst
- Storytelling Consultant
- Executive Advisor

---

# Core Design Principles

## Trust Before Intelligence

Atlas should never analyse poor-quality data without informing the user.

Every analysis begins with validating data quality.

---

## Explain Everything

Atlas never performs silent transformations.

Every action should answer:

- What changed?
- Why?
- What business problem does this solve?
- What risks exist?
- How confident is Atlas?
- Can this change be rolled back?

---

## Raw Data Is Sacred

Atlas never modifies the original source.

Repairs always create a semantic clean layer.

Example:

Raw

Sales

↓

Semantic

sales_clean

---

## Config Over Code

Business rules should never be hardcoded.

Everything should be configurable.

Examples

country_region_mapping.yaml

country_standardisation.yaml

repair_rules.yaml

metric_definitions.yaml

semantic_dictionary.yaml

---

## Modular Architecture

Every capability must be pluggable.

Future copilots should integrate without modifying core code.

---

# High-Level Architecture

```text
Business User
        │
        ▼

Chief Analytics Officer

        │

        ▼

──────────────────────────────────────────

Data Quality Copilot

Data Steward

Semantic Layer Manager

Data Catalog

──────────────────────────────────────────

        │

        ▼

Analytics Team

Requirements Analyst

SQL Engineer

BI Analyst

Statistician

Root Cause Analyst

Forecasting Agent

Validation Agent

Narrative Agent

Presentation Agent

──────────────────────────────────────────

        │

        ▼

Executive Deliverables

PowerPoint

Dashboard

HTML

PDF

Slack

Email
```

---

# New Agent

## Data Quality Copilot

Purpose

Become the first specialist that every dataset passes through.

Responsibilities

- Profile datasets
- Detect quality issues
- Estimate business risk
- Recommend repairs
- Preview transformations
- Request approval
- Apply safe repairs
- Create semantic clean layer
- Produce audit trail
- Generate quality score
- Learn business rules

---

# Analytics Pipeline

Current

```text
Connect

↓

Profile

↓

Analyse

↓

PowerPoint
```

Future

```text
Connect

↓

Profile

↓

Detect Issues

↓

Repair Plan

↓

Preview

↓

Approval

↓

Semantic Clean Layer

↓

Readiness Gate

↓

Analysis

↓

Validation

↓

Narrative

↓

PowerPoint
```

---

# New Slash Commands

## /repair

Generate repair plan.

Example

Found 5 Issues

HIGH

Order_Date stored as VARCHAR

Recommendation

Convert to DATE

Business Impact

Time intelligence unreliable.

Confidence

99%

---

## /repair --preview

Display

Before

↓

After

Transformation

SQL

Pandas

Expected quality improvement

Rows affected

---

## /repair --apply

Create

sales_clean

Never overwrite original data.

---

## /repair --undo

Rollback semantic layer.

---

## /repair --history

Display

Timestamp

Repair

Approval

Rows affected

User

---

# Automatic Behaviour

Whenever

/connect

or

/analyze

is executed

Atlas automatically runs Data Quality Copilot.

---

# Data Readiness Gate

Every analysis must pass.

Example

```text
Data Readiness

Quality Score

94

Business Readiness

Excellent

Critical Issues

0

Warnings

2

Semantic Layer

sales_clean

Analysis Confidence

95%

Ready

YES
```

---

# Data Quality Score

Dimensions

Completeness

Consistency

Validity

Freshness

Uniqueness

Semantic Accuracy

Referential Integrity

Business Readiness

Type Safety

Documentation

Overall Score

0–100

---

# Repair Modules

Every repair module implements

Detector

Repair

Confidence

Business Impact

Transformation

Rollback

Audit

Modules

- Date Repair
- Region Repair
- Month Repair
- Quarter Repair
- Year Repair
- Duplicate Detection
- Country Standardisation
- Numeric Type Repair
- Boolean Repair
- Whitespace Repair
- Case Standardisation
- Null Classification

---

# Business Impact Engine

Every issue explains

Problem

Business Risk

Impact

Recommendation

Confidence

Example

Problem

Region missing

Business Impact

North America excluded if Region filter used.

Risk

High

Confidence

99%

---

# Semantic Clean Layer

Atlas creates

Order_Date_Clean

Region_Clean

Country_Clean

Quarter_Clean

Month_Clean

Year_Clean

Original columns remain unchanged.

Analytics agents automatically use clean fields.

---

# SQL Repair Engine

Generate SQL for

DuckDB

Snowflake

PostgreSQL

BigQuery

Databricks

Microsoft Fabric

SQL Server

---

# Pandas Repair Engine

For CSV

Excel

Parquet

Generate equivalent pandas transformations.

---

# Transformation Pipeline

Every repair becomes a pipeline.

Transform 1

Convert Date

↓

Transform 2

Derive Region

↓

Transform 3

Standardise Country

↓

Transform 4

Generate Quarter

Users may

Disable

Edit

Reorder

Preview

Replay

Rollback

---

# Audit Trail

Store

runs/<run_id>/

repair_plan.json

repair_log.json

transformations.sql

transformations.py

before_profile.md

after_profile.md

quality_score.json

---

# Before & After Reports

Generate

Original Profile

↓

Clean Profile

Show

Quality improvements

Repair summary

Remaining warnings

---

# Repair Memory

Remember

Approved repairs

Business rules

Schema mappings

Country mappings

Date parsing rules

Store

memory/quirks/

Future analyses reuse previous knowledge.

---

# Schema Drift Detection

Detect

Renamed columns

Removed columns

Added columns

Datatype changes

Provide mapping suggestions.

---

# Semantic Guardrails

Every column receives status

Trusted

Derived

Deprecated

Unsafe

Blocked

Downstream agents automatically avoid unsafe fields.

---

# Enterprise Data Catalog

Every connected dataset receives

Owner

Quality Score

Certification Status

Last Refresh

Business Description

Tags

Schema

Lineage

---

# Data Lineage

Every metric traces back to

Source

↓

Transformation

↓

Semantic Layer

↓

SQL

↓

Dashboard

↓

PowerPoint

---

# Chief Analytics Officer

Master orchestrator.

Responsibilities

Select agents.

Estimate runtime.

Estimate cost.

Skip unnecessary work.

Enforce quality gates.

Manage parallel execution.

Resolve conflicts.

Produce final recommendation.

---

# Dynamic Agent Routing

Simple question

Revenue last month

Run

Quality

SQL

Validation

Complex question

Why did churn increase?

Run

Quality

Profiling

Statistics

Root Cause

Validation

Narrative

Presentation

---

# Multi-Level Confidence

Score

Data Quality

Metric Definition

Statistics

Business Logic

Narrative

Overall Confidence

---

# Executive Recommendations

Every analysis ends with

Root Cause

Business Recommendation

Estimated Impact

Confidence

Next Best Actions

---

# Interactive Conversation

Atlas should continue helping.

Example

Would you like

- a Power BI dashboard?
- customer segmentation?
- forecasting?
- scenario modelling?
- executive summary?

---

# Plugin Framework

Future copilots

- Governance Copilot
- GDPR Copilot
- PII Copilot
- Forecast Copilot
- Dashboard Copilot
- ML Copilot
- Data Steward Copilot
- Metadata Copilot
- Schema Drift Copilot

Must plug into the same architecture.

---

# Engineering Requirements

- Backward compatible
- Modular
- Plugin-based
- Configuration driven
- Fully tested
- Fully documented
- Provenance preserved
- Deterministic outputs
- Reproducible transformations
- Enterprise ready

---

# Success Criteria

Atlas should no longer behave like a simple AI analyst.

It should behave like an enterprise analytics organization that:

- validates data,
- prepares trusted semantic models,
- orchestrates specialist AI agents,
- generates executive-ready insights,
- explains every decision,
- preserves governance,
- and continuously learns from approved business rules.