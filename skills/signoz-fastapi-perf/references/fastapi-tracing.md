# FastAPI/OpenTelemetry instrumentation notes

Do not change business semantics just to add tracing. Instrument concrete phases of a route (e.g. `items.list.fetch_page`, `items.list.hydrate_related`, `items.list.serialize`) and downstream service/dependency work where missing.

Example pseudocode; adapt to the tracing provider/version **already installed** in the repository:

```python
from opentelemetry import trace
tracer = trace.get_tracer(__name__)

async def list_with_tracing(service):
    with tracer.start_as_current_span("items.list.fetch_base_records"):
        base = await service.fetch_base_records()
    with tracer.start_as_current_span("items.list.hydrate_related") as span:
        span.set_attribute("app.records_count", len(base))  # low-cardinality aggregate
        result = await service.hydrate_related(base)
    return result
```

- Avoid email, user ID, tokens, raw request body, Mongo document values and personal data in Span attributes.
- Use stable operation names and bounded-cardinality attributes. Annotate aggregate counts and phases; do not create a Span for every record in a long loop.
- Automatic instrumentation might already cover Mongo queries and HTTP calls. Add application-level context rather than duplicating every dependency Span.
- In async code, a span around `await` shows wall time, not time consumed by Python CPU. Add separate profiler evidence if CPU is suspected.
- Be careful with context propagation across task groups, threads and workers. Do not conflate unrelated traces.
- Check instrumentation version, existing exporter and sampling before recommending modifications.
