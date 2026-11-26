# Architecture (trust boundary + approval gate)

![architecture](architecture.svg)

```mermaid
flowchart LR
 U[Light-theme chat UI] -->|event| G[Guardrails: schema, length, injection, secrets, rate/token limits]
 G --> R{Deterministic router}
 R -->|greeting| D[Direct reply]
 R -->|IT question| K[Hybrid retrieval BM25+vector, RRF, relevance gate]
 R -->|diagnostic / NDMC| T[Validated simulated tools, max 5]
 T -->|error signature| K
 R -->|unresolved / privileged| H[Ticket draft: hash, priority, expiry]
 K --> S[Grounded synthesis: OpenAI or extractive fallback]
 T --> S
 S --> V[Citation validation vs retrieved IDs]
 V --> U
 K -.no evidence.-> A[Abstain / offer ticket]
 H --> P[[Human approval: atomic, hash+expiry+owner checked]]
 P -->|approved only| M[(Mock ITSM ticket)]
 G & K & T & S & P --> X[(SQLite state + audit)]
 G & K & T & S & P -.aggregate metrics.-> O[Prometheus -> Grafana, staff only]
```
Trust boundary: the browser is untrusted; the Streamlit backend owns identity, state and the model key. Retrieved text and tool output are data, never instructions. Model output is never rendered as HTML (escaped; only validated citation labels become chips).
