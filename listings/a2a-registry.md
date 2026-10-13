# A2A Registry (after the site is live)
Validate first (read-only, no listing): 
  curl -X POST https://api.a2a-registry.org/public/ingest/scan -H 'Content-Type: application/json' -d '{"url":"https://readsigil.com/.well-known/agent-card.json"}'
Submit (creates a public UNCLAIMED listing; needs approval):
  curl -X POST https://api.a2a-registry.org/public/ingest/submit -H 'Content-Type: application/json' -d '{"url":"https://readsigil.com/.well-known/agent-card.json"}'
Note: our card advertises static JSON plus GitHub-issue posting, not a live A2A JSON-RPC `message/send` endpoint, so health-checking directories may mark it partial until a Worker endpoint exists (see the roadmap).
