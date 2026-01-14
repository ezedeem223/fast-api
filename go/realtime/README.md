# Realtime Gateway (Go)

Small WebSocket fanout service that relays Redis Pub/Sub messages to connected clients.

## Environment

- `REDIS_URL` (default: `redis://localhost:6379/0`)
- `REDIS_CHANNEL` (default: `realtime:broadcast`)
- `BIND_ADDR` (default: `:8081`)

## Run

```bash
go run .
```

Clients connect via `ws://HOST:PORT/ws`.
