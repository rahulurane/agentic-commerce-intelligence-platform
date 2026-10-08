# 04 — LLM SDK Layer (Provider-Agnostic Gateway)

## 1. Goal

All LLM access goes through one shared `llm-gateway` service that exposes a single
internal contract. Providers (Gemini, OpenAI, Anthropic, Llama via Ollama/vLLM) sit
behind an **adapter interface** and are selected by config. Agents never import a
vendor SDK — they call the gateway. This is the "flexible LLM SDK layer / provider
agnosticism" principle made concrete.

## 2. Adapter interface

```python
class LLMProvider(Protocol):
    async def complete(self, req: LLMRequest) -> LLMResponse: ...
    async def health(self) -> ProviderHealth: ...

@dataclass
class LLMRequest:
    system: str
    prompt: str
    temperature: float = 0.2
    max_tokens: int = 512
    response_schema: dict | None = None   # for structured rationale output
    metadata: dict | None = None          # trace_id, agent, txn_id

@dataclass
class LLMResponse:
    text: str
    structured: dict | None
    provider: str
    model: str
    usage: TokenUsage
    latency_ms: int
```

Concrete adapters:

- `GeminiAdapter` — Google GenAI / Vertex SDK, auth via **Application Default
  Credentials (ADC)**. Default provider.
- `OpenAIAdapter`, `AnthropicAdapter`, `LlamaAdapter` (OpenAI-compatible endpoint for
  local Llama) — present as stubs/working adapters, selected by config.
- `MockAdapter` — deterministic, no network. Used when no cloud creds are present so
  the full demo runs offline.

## 3. Provider selection & hot-swap

Config-driven, no code change to switch:

```env
LLM_PROVIDER=gemini          # gemini | openai | anthropic | llama | mock
LLM_MODEL=gemini-1.5-pro
GOOGLE_APPLICATION_CREDENTIALS=/secrets/adc.json
LLM_FALLBACK_PROVIDER=mock   # used on repeated failure / circuit open
```

The gateway resolves the active provider at request time, so swapping `LLM_PROVIDER`
and restarting (or hitting a reload endpoint) hot-swaps the backend. A
`LLM_FALLBACK_PROVIDER` is used when the primary's circuit breaker is open — the demo
degrades to `mock` rather than failing.

## 4. Gemini / ADC auth

- Local/dev: mount a service-account key and set
  `GOOGLE_APPLICATION_CREDENTIALS`; or use `gcloud auth application-default login`.
- The adapter never hard-codes keys; it relies on the ADC chain, which also works
  unchanged on GCP (Workload Identity) in a future K8s deployment.
- If ADC resolution fails at startup, the gateway logs a clear warning and falls back
  to `mock` so the stack still boots.

## 5. Reliability features

- **Timeouts** per request (default 1.5s for rationale calls — off the critical score
  path).
- **Retries** with exponential backoff + jitter on transient errors.
- **Circuit breaker** per provider; when open, requests short-circuit to the fallback.
- **Structured output** via `response_schema` so agents get parseable rationale +
  evidence, not free text.
- **Caching** of rationale for identical (score bucket + top-features) inputs to cut
  cost and latency.

## 6. Request contract (agent → gateway)

```http
POST /v1/complete
{
  "system": "You are a fraud explainability assistant...",
  "prompt": "Score 0.87. Top signals: shared_device_ring_size=4, velocity_1h=11. Explain as evidence.",
  "response_schema": { "rationale": "string", "evidence": "array" },
  "metadata": { "trace_id": "...", "agent": "fraud", "txn_id": "txn_..." }
}
```

Response is normalized `LLMResponse` regardless of provider — the agent code is
identical across Gemini, OpenAI, or mock.

## 7. Observability

- Per-provider latency + token-usage metrics (cost visibility).
- Trace spans wrap every provider call with `trace_id` from the event.
- Degraded calls (fallback used) are counted and surfaced in Grafana.
