# Resolver: Latency & Throughput

**Setup:** local Mac, `qwen2.5:7b` on Ollama, 500 articles from the `articles` topic.

## Throughput
- **15 articles/min** (~900/hour, ~21.6k/day per instance)
- **1.0 events/min** (33 events from 500 articles, 6.6% event-yield)

## Latency
|     | ms     |
| --- | -----: |
| p50 | 3,700  |
| p95 | 7,700  |
| max | 33,700 |

## Where the time goes
- 95% LLM decode (~21 tok/s)
- ~5% everything else (Kafka, geocode, prefill)

## Notes
- 467 of 500 articles returned 0 events.
- Single outlier at 33.7 s max (4× p95). Not systemic — likely Nominatim or Ollama hitch.
- Bottleneck is LLM decode. Faster model or GPU = faster resolver.
