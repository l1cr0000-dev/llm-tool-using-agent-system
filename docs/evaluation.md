# Agent Pipeline vs. Dify Workflow Evaluation

This project compares equivalent workflows on the version-controlled tasks in
`evaluation/cases.json`. Run the code-based pipeline with:

```bash
tool-agent evaluate --output evaluation/results/agent-report.json
```

To add a Dify comparison, run the same questions in the imported Dify workflow,
record the observations in a copy of `evaluation/dify_results_template.json`,
then run:

```bash
tool-agent evaluate \
  --dify-results evaluation/dify_results.json \
  --output evaluation/results/comparison-report.json
```

The report is JSON so it can be checked into an experiment branch, visualized in
a notebook, or consumed by CI. The template intentionally contains no claimed
Dify benchmark result: Dify measurements must come from an actual workflow run.

## Dimensions

| Dimension | Measurement | Why it matters |
| --- | --- | --- |
| Task decomposition | Planned executable steps / expected minimum steps | Detects under- or over-decomposition. |
| Tool selection | Multiset F1 against the required tools | Penalizes missing required tools and needless calls. |
| Execution stability | Successful tool calls / all tool calls | Captures API, retrieval, routing, and recovery failures. |
| Calling cost | Explicit unit-price estimate or provider bill | Makes added retries and fallback calls visible. |

The default pipeline cost card charges one combined planner/synthesizer unit and
per-tool units. It is an estimate, not a billing record; change `CostModel` to
match the selected LLM provider, token prices, and tool plan.

## Error analysis

Each failed tool call is classified as `configuration`, `external_dependency`,
`retrieval_miss`, `routing`, or `tool_execution`. The generated report lists the
affected case IDs and a recommended action for each category. This makes retry
and fallback behavior measurable rather than just described in the architecture.

For fair comparisons, pin the model, prompt, knowledge base, case set, tool
credentials, and price card for both implementations. The automatic
decomposition score checks plan size; review plan quality manually when tasks
have several valid decompositions.
