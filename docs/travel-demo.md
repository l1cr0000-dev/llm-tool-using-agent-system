# Offline demo: Beijing → Shanghai, 3 days

Command:

```bash
tool-agent travel 北京 上海 --days 3 --budget 4500 --interests 美食,城市 --offline
```

Generated itinerary (per-person CNY estimate):

## Transport

- Recommended: high-speed rail, about 4 hours each way, ¥491 one way.
- Round trip: ¥982.
- Alternative: economy flight, about 4 hours, ¥832 one way.

## Daily itinerary

| Day | Morning | Afternoon | Restaurant | Daily estimate |
| --- | --- | --- | --- | ---: |
| 1 | The Bund | Yu Garden | Nanxiang Steamed Bun Restaurant | ¥880 |
| 2 | Shanghai Museum East | Wukang Road | Lao Jishi | ¥840 |
| 3 | Shanghai Disney Resort | The Bund | Guangmingcun Restaurant | ¥1,559 |

## Budget

- Accommodation, food, local travel, and attraction tickets: ¥3,279
- Round-trip transport: ¥982
- **Total: ¥4,261 / person**
- Against a ¥4,500 budget: **¥239 remaining**

The output is deterministic in `--offline` mode and sourced from the versioned
travel RAG corpus. Transport and venue prices are estimates for planning; users
must verify live availability and prices before booking.
