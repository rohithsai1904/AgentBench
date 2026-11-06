# AgentBench

**An LLM Engineering, Evaluation & Observability Platform**

AgentBench is an open-source platform for developing, evaluating, and monitoring LLM-powered applications and AI agents.

It provides a unified way to trace agent executions, measure output quality, run evaluations, compare experiments, and identify regressions. The goal is to make LLM application development more observable, measurable, and reproducible.

## Key Features

- **LLM Observability:** Capture end-to-end execution traces, including LLM calls, tool invocations, retrieval operations, latency, token usage, and errors.
- **Evaluation Engine:** Evaluate LLM applications using built-in metrics, custom evaluators, and LLM-as-a-Judge.
- **Experiment Tracking:** Track evaluation runs, datasets, model configurations, prompts, and metrics to compare different experiments.
- **Prompt Management:** Version prompts, maintain prompt lineage, and evaluate different prompt variations.
- **RAG Evaluation:** Measure retrieval and generation quality using metrics such as Recall@K, MRR, faithfulness, and answer relevance.
- **LLM Gateway:** Provide a unified interface for interacting with different LLM providers, with support for routing, retries, rate limiting, and usage tracking.

## Technology Stack

- **Language:** Python
- **Backend:** FastAPI, Pydantic
- **Database:** PostgreSQL
- **Observability:** OpenTelemetry
- **AI / Agents:** LangGraph, LLM provider APIs
- **Vector Search:** pgvector
- **Testing:** pytest
- **Deployment:** Docker

## Design Goals

- Framework-independent evaluation of LLM applications and agents.
- Reproducible experiments with versioned prompts and datasets.
- Visibility into multi-step agent execution and tool interactions.
- Extensible evaluation metrics and custom evaluators.
- Reliable evaluation through concurrency control and failure isolation.

## Motivation

LLM applications are increasingly becoming complex systems involving multiple model calls, tools, retrieval pipelines, and autonomous agent workflows. Evaluating only the final response is not enough to understand their behaviour or reliability.

AgentBench aims to bring software engineering discipline to LLM development through observability, systematic evaluation, and experiment tracking.

---

**AgentBench — Build, Trace, Evaluate, Improve.**