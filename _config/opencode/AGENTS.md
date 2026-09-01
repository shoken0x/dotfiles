<!-- codegraph:start -->
**codegraph** is connected. Prefer its tools over re-grepping:

- `codegraph_search` — fuzzy + structured search (`kind:function`, `lang:python`).
- `codegraph_get_node` — fetch a node's full metadata by id.
- `codegraph_callers` / `codegraph_callees` — who calls X / what does X call.
- `codegraph_context` — assemble markdown context for a task.

Trust results; they're deterministic tree-sitter extractions, not LLM summaries.
<!-- codegraph:end -->
