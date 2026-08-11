# Travel Planner API

Start a local, offline-safe server:

```bash
tool-agent serve --offline
```

The clickable travel workspace is available at `http://127.0.0.1:8000`; interactive OpenAPI documentation is at `/docs`.
Use `--live` only after configuring the required LLM and web-search credentials.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Check service status and whether it is offline. |
| `POST` | `/api/travel-plans` | Generate and persist a travel plan. |
| `GET` | `/api/travel-plans?limit=20` | Read recent plans. |
| `GET` | `/api/travel-plans/{id}` | Read one saved plan. |

Example request:

```json
{
  "origin": "北京",
  "destination": "上海",
  "days": 3,
  "budget_cny": 4500,
  "interests": ["美食", "城市"],
  "travelers": 2,
  "lodging_preference": "舒适",
  "pace": "适中"
}
```

The response includes `result.markdown` for direct display, a structured cost
summary, full decision details for transport/stay/food/drinks/local travel,
warnings, Agent trace, and tool outputs. Plans are stored in SQLite;
the default local database is ignored by Git.
