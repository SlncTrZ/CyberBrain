# CyberBrain Security Specification v1

## Provider security

CyberBrain follows the repository integration standard in `../MCP_PROVIDER_STANDARD.md`.

Network MCP deployment requires authenticated access.

Primary auth:

```text
Authorization: Bearer <token>
```

Optional compatibility auth:

```text
X-API-Key: <token>
```

Production/network mode must fail closed when required authentication is not configured.

## Secret handling

Never persist or emit:

- passwords
- API keys
- bearer tokens
- private keys
- session secrets
- credential files

Secrets must not appear in:

- Qdrant payloads
- embeddings
- prompts used for Dreaming
- logs
- tool results
- URLs/query strings
- source-controlled config

## Ingestion secret rejection

Durable writes pass a secret-detection gate before embedding or persistence.

Detection should combine deterministic patterns and configurable high-risk field/name rules. LLM judgment must not be the only secret filter.

When a candidate looks sensitive, reject or require explicit safe redaction rather than storing first and cleaning later.

## Authorization boundary

MCP transport authentication answers who may call the provider.

Tool-level authorization/policy may additionally be enforced by SlncTrZ-MCP. CyberBrain must not self-expand gateway authority or bypass gateway policy.

### Tenancy/isolation source foundation

`main` contains the `cyberbrain.tenancy` foundation for transport-neutral tenant/user/agent/project/session authority scopes, true subset narrowing, wildcard rejection, abstract storage filters, concrete write attribution, quota policy models, and readiness gates. Current source binds successfully authenticated MCP requests to an explicit `CallerAuthority` in `single_owner` mode and uses that authority for canonical exact-ID fetch. It can additionally bind one server-configured trusted agent identity only after Bearer/X-API-Key verification; arbitrary caller headers or tool arguments cannot create trusted identity. When such identity is bound, Prediction Learning record/read/calibration operations are narrowed to that agent and Prediction resolution verifies the referenced Prediction agent before Outcome persistence. `agent_ready` and `multi_user` remain fail-closed until full read/write/background enforcement and persisted identity requirements are complete. Broader search/write paths are not yet tenancy-enforced. Release and deployment state are separate from this source security contract.

Wave 2 integration must fail closed in this order:

```text
authenticated caller
→ granted authority
→ requested-scope narrowing
→ effective scope
→ hard storage/read filter
→ retrieval or exact get-by-ID
→ downstream ranking/context packing
```

Exact get-by-ID must never become an authorization bypass, and retrieval ranking/similarity must never broaden caller authority. Current exact fetch combines canonical ID and effective scope in the storage query; missing and out-of-scope IDs intentionally share one not-found response shape. Multi-valued read authority may be narrowed for reads; durable write attribution must resolve every present identity dimension to one concrete value before persistence.

Salience follows the same rule. `SalienceAdvisor` accepts only already-authorized candidates and fails closed if one advisory set crosses a scope marker. Salience score, reason codes, or advisory priority can never make an unauthorized record visible or widen an effective scope.

Concept Formation and Working Memory remain downstream of this boundary. Concept discovery may only examine evidence already admitted to its same-scope candidate set. Working Memory additionally requires exact `scope_marker + session_id + task_id` identity and rejects candidates from another working-set identity. That exact task identity is defense-in-depth against local mixing; it is **not** a substitute for trusted caller identity or full P3 read-path enforcement.

Agent Self-Model remains downstream of trusted prospective identity/evidence. Current source M6 can generate hypotheses only from authenticated prospective Prediction/Outcome samples after the fail-closed readiness gate, requires explicit `pending | accepted | rejected` review, persists accepted-only hypotheses through Knowledge Evolution with `record_class=self_model_hypothesis` and `ordinary_recall=false`, and may project accepted hypotheses into Working Memory only as bounded advisory context. This does not authorize prompt/tool/routing/permission mutation or turn hypotheses into identity truth. `agent_ready`/`multi_user` remain separately blocked on broader P3 isolation.

Schema V2 makes identity provenance explicit with `identity_trust=unspecified | legacy_untrusted | authenticated | system_derived`. Migration must never convert historical caller-provided/stored agent strings into `authenticated` identity without verified provenance. Records that cannot be normalized without fabricating required canonical metadata are preserved as non-recallable `migration_quarantine` rather than silently dropped or invented.

Memory Lifecycle M7 is also downstream of authorization. Suppression/reactivation is metadata-only through `lifecycle_state` and `ordinary_recall`; it must not change caller scope, Knowledge truth status, evidence/provenance, or physically delete canonical content as its normal forgetting mechanism. Lifecycle evaluation may only consume records/signals already eligible under the relevant authority boundary.

## Logging

Logs may include:

```text
request/tool id
operation class
latency
success/failure
safe error code
```

Logs must redact sensitive arguments and never log auth credentials.

## Error safety

External errors must not include full stack traces, environment dumps, connection secrets, or raw dependency configuration.

Internal diagnostics may preserve stack traces only in protected server logs after redaction.

## Dreaming safety

Dreaming only reasons over data CyberBrain is authorized to read.

Dreaming cannot lower verification/security requirements for its own writes.

Derived output containing suspected secrets is rejected before embedding/persistence.

## Dependency failure

Embedding/storage failure must fail explicitly. CyberBrain must not silently generate zero vectors, discard writes, or report false success.

## Configuration

Behavioral non-secret configuration may be source-controlled when the current runtime contract explicitly defines how it is consumed. Tracked examples that are not runtime-loaded must say so clearly.

The current CyberBrain runtime primarily consumes `CYBERBRAIN_*` environment variables plus explicit Dream route JSON. Real credentials remain runtime-only and are never checked into Git.

## Shared trusted coding-agent principal

In the current single-owner deployment, the owner has explicitly chosen a simplified trusted identity policy: any caller that authenticates with the existing shared MCP credential is bound to `agent=coding-agents` for trusted cognition attribution. This allows M6 to accumulate one pooled trusted Prediction/Outcome stream without introducing per-agent credentials.

This policy does not create multi-user/per-agent isolation. It must not be described as `agent_ready` or `multi_user`, both of which remain fail-closed until broader P3 isolation is complete. Caller-supplied agent fields still cannot override the authenticated principal on Prediction Learning paths.
