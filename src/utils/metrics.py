"""Prometheus metrics for SentiWiki RAG system."""

from prometheus_client import Counter, Histogram, Gauge, generate_latest

# HTTP Request metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

# RAG-specific metrics
rag_queries_total = Counter(
    'rag_queries_total',
    'Total RAG queries',
    ['collection', 'reranking_enabled', 'hybrid_enabled']
)

rag_query_duration_seconds = Histogram(
    'rag_query_duration_seconds',
    'RAG query duration in seconds',
    ['collection'],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

rag_retrieval_duration_seconds = Histogram(
    'rag_retrieval_duration_seconds',
    'Retrieval duration in seconds',
    ['collection'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0]
)

rag_llm_duration_seconds = Histogram(
    'rag_llm_duration_seconds',
    'LLM generation duration in seconds',
    ['model'],
    buckets=[1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

rag_retrieval_docs = Histogram(
    'rag_retrieval_docs',
    'Number of documents retrieved',
    ['collection'],
    buckets=[1, 5, 10, 20, 30, 50]
)

rag_retrieval_avg_score = Histogram(
    'rag_retrieval_avg_score',
    'Average retrieval relevance score',
    ['collection'],
    buckets=[0.0, 0.2, 0.4, 0.6, 0.8, 0.9, 0.95, 1.0]
)

# LLM cost metrics
llm_tokens_total = Counter(
    'llm_tokens_total',
    'Total LLM tokens used',
    ['model', 'type']  # type: prompt or completion
)

llm_cost_total = Counter(
    'llm_cost_total',
    'Total LLM cost in USD',
    ['model']
)

# Agent-specific metrics
agent_queries_total = Counter(
    'agent_queries_total',
    'Total agent queries (chat endpoint)',
    ['collection', 'route']  # route: 'RAG' or 'DIRECT'
)

agent_query_duration_seconds = Histogram(
    'agent_query_duration_seconds',
    'Agent query duration in seconds',
    ['route'],  # route: 'RAG' or 'DIRECT'
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

agent_routing_decisions_total = Counter(
    'agent_routing_decisions_total',
    'Total routing decisions made by agent',
    ['route']  # route: 'RAG' or 'DIRECT'
)

# System health metrics
qdrant_health = Gauge(
    'qdrant_health',
    'Qdrant health status (1=healthy, 0=unhealthy)'
)

active_connections = Gauge(
    'active_connections',
    'Number of active connections'
)

def get_metrics():
    """Return Prometheus metrics in text format."""
    return generate_latest()

