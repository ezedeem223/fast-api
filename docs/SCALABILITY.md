# Scalability Notes

This document outlines optional next steps for scaling the platform beyond a single
service. These are not required today, but provide a roadmap when traffic or team
size grows.

## Candidate Service Boundaries
- Realtime (notifications + call signaling): isolate WebSocket load and scale
  horizontally without impacting HTTP APIs.
- Media/processing: move virus scans, transcoding, and heavy AI inference into a
  dedicated worker service.
- Search/analytics: extract heavy aggregation or AI workloads into async workers
  (Celery/queue-first) and cache results.
- Auth/session: optionally split if SSO or identity traffic dominates.

## Communication Patterns
- Event-driven messaging via Redis streams, RabbitMQ, or Kafka for cross-service
  notifications.
- Internal HTTP/gRPC for synchronous calls that require immediate responses.
- Shared DB remains possible early on; plan for per-service schemas when feasible.

## Scaling Signals
- Sustained CPU or memory pressure from Amenhotep model loading/inference.
- WebSocket connection counts growing faster than HTTP traffic.
- Slow query times on analytics/search routes despite caching.

## Migration Tips
- Start by extracting a worker queue (Celery) for long-running tasks.
- Use a shared OpenAPI contract to keep services compatible.
- Version events/messages to avoid breaking consumers during refactors.
