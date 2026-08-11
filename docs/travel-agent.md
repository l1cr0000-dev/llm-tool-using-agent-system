# Travel Itinerary Agent

The `travel` command reuses the existing LangGraph state machine:

```text
Travel request -> Planning -> transport_quote + destination_guide (RAG) -> Synthesis -> itinerary renderer
```

## Inputs and output

Required inputs are `origin` and `destination`. Optional inputs are `--days`,
`--budget`, and `--interests`. The final Markdown contains a daily table of two
attractions and one restaurant, transport alternatives, a per-person cost
breakdown, and an explicit budget-overrun warning.

`TravelPlanResult` also keeps the Markdown, structured cost totals, warnings,
Agent trace, and tool results. The CLI uses the Markdown; the REST API persists
and returns the complete structured result for a product client.

## Tools

- `transport_quote` estimates route distance, two one-way transport options,
  and a recommended option. Prices are deterministic estimates, not booking
  quotes.
- `destination_guide` retrieves a destination document from
  `travel_kb/destinations.json`. Each document contains attractions, restaurants,
  tags, ticket prices, and daily baseline costs.
- `web_search` is added to the plan when the request asks for current or latest
  data. It remains optional so the complete showcase works offline.

The local corpus covers Beijing, Shanghai, Hangzhou, Chengdu, and Sanya. For a
new city, add one document with the same schema, or use Web Search as a live
fallback. All price labels are estimates and must be verified before booking.
