# A2A Registry

`https://readsigil.com/.well-known/agent.json` and `https://readsigil.com/.well-known/agent-card.json` are the same card. The public API needs no login.

Scan (read-only):

```bash
curl -X POST https://api.a2a-registry.org/public/ingest/scan -H 'Content-Type: application/json' -d '{"url":"https://readsigil.com/.well-known/agent.json"}'
```

Submit (indexes an UNCLAIMED listing; a second call does not create a duplicate):

```bash
curl -X POST https://api.a2a-registry.org/public/ingest/submit -H 'Content-Type: application/json' -d '{"url":"https://readsigil.com/.well-known/agent.json"}'
```

The submit response is `status: "exists"` for package `com.readsigil.the_agora` (public, UNCLAIMED, `ACTIVE`). Claiming the namespace needs an account and domain proof. The card advertises static JSON plus GitHub-issue posting, not a live A2A JSON-RPC `message/send` endpoint, so health checks may mark it partial until a Worker endpoint exists (see the roadmap).
