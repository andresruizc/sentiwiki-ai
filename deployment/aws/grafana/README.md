# Grafana Configuration for SentiWiki RAG

## Quick Setup

After deploying Grafana, follow these steps:

### 1. Add Prometheus Data Source

1. Open Grafana: `http://<grafana-ip>:3002`
2. Login: `admin` / `admin`
3. Go to **Configuration** → **Data Sources** → **Add data source**
4. Select **Prometheus**
5. Set URL: `http://prometheus.esa-iagen.local:9090`
6. Click **Save & Test**

### 2. Import Dashboard

1. Go to **Dashboards** → **Import**
2. Upload `dashboards/rag-metrics.json`
3. Select the Prometheus data source
4. Click **Import**

## Dashboard Panels

The RAG dashboard includes:

### Overview Row
- **Total RAG Queries**: Counter of all RAG requests
- **Total Agent Queries**: Counter of agent (chat) requests  
- **Total LLM Cost**: Running cost in USD
- **Total Tokens Used**: Token consumption

### Latency Row
- **RAG Query Latency**: p50/p95/p99 end-to-end latency
- **Retrieval vs LLM**: Breakdown of where time is spent

### Retrieval Quality Row
- **Relevance Score**: Average semantic similarity scores
- **Documents Retrieved**: How many docs per query
- **Routing Decisions**: Pie chart of RAG vs Direct routing

### HTTP Metrics Row
- **Requests by Status**: Success/error rates
- **Request Duration**: HTTP latency percentiles

### Cost Analysis Row
- **LLM Cost by Model**: Cost breakdown per model
- **Token Usage**: Prompt vs completion tokens

## Alerts

To add alerts, go to **Alerting** → **Alert rules** and create rules like:

```
# High Latency Alert
PromQL: histogram_quantile(0.95, rate(rag_query_duration_seconds_bucket[5m])) > 10
Condition: For 5 minutes
Severity: Warning

# High Error Rate Alert  
PromQL: sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) > 0.05
Condition: For 2 minutes
Severity: Critical
```

## Metrics Reference

| Metric | Type | Description |
|--------|------|-------------|
| `rag_queries_total` | Counter | Total RAG queries |
| `rag_query_duration_seconds` | Histogram | E2E query latency |
| `rag_retrieval_duration_seconds` | Histogram | Retrieval stage latency |
| `rag_llm_duration_seconds` | Histogram | LLM generation latency |
| `rag_retrieval_docs` | Histogram | Docs retrieved per query |
| `rag_retrieval_avg_score` | Histogram | Avg relevance score |
| `llm_tokens_total` | Counter | Token usage by type |
| `llm_cost_total` | Counter | Cost by model |
| `agent_queries_total` | Counter | Agent queries by route |
| `agent_routing_decisions_total` | Counter | RAG vs Direct decisions |
| `http_requests_total` | Counter | HTTP requests by status |
| `http_request_duration_seconds` | Histogram | HTTP latency |

