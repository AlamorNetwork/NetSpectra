# Project knowledge graph

Graphify 0.9.79 is installed as an isolated uv tool. Its project-local outputs are
`graphify-out/graph.html`, `graph.json`, `GRAPH_REPORT.md`, and `health.json`.
Open graph.html directly in a browser. Outputs and extraction caches are ignored
by Git: they are generated analysis, not application runtime dependencies.

The initial snapshot covers 87 files (48 code, 37 documents, 2 SVGs), including the
redesign source and design brief. This guide and the acceptance note were added
subsequently; refresh the graph after later changes. Structural extraction uses
ASTs; document/image semantics were extracted by the host agents without a provider
API key. No Gemini key was configured. Host token usage is unavailable; zero
numeric counters in cost.json are placeholders, not evidence of free extraction.

`.graphifyignore` excludes artifacts, environment files, keys, captures, traces,
virtual environments, font binaries and generated outputs. Scan only this repo,
never the parent workspace. Review exclusions before extracting new content.

## Use

Invoke the installed graphify skill on this repository for full or incremental
rebuilds. An agent must follow its extraction and diagnostic workflow; a CLI-only
semantic refresh without a configured backend is not equivalent.

```powershell
graphify query "capture qlog SSH orchestration" --budget 1500
graphify explain "Inventory"
graphify export html
graphify benchmark
```

The initial export has 692 nodes, 1,485 edges and 63 named communities. Diagnostics
report 392 dangling-endpoint edges, one self-loop and 74 undirected edge collapses.
External AST references and unresolved symbols make this a partial map. INFERRED
links require verification against source; graph connectivity is not runtime proof.
The benchmark estimates 7.3x fewer context tokens per query; this is a heuristic,
not measured billing or a guarantee of retrieval completeness. The corpus already
fits a context window, so the main benefit here is navigation and relationship discovery.
