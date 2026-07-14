"""ETH Research Collection harvest + RAG index.

Pipeline (each stage resumable from disk):

    discover  ──► fetch_text  ──► extract_matches ──► extract_relations
                                                       │
                                                       ▼
                                                   fetch_related
                                                       │
                                       chunk ──► embed ──► store
                                                                │
                                                                ▼
                                              query (filter → vector → rerank)

Entry point: `python -m open_pulse_sources.index.ethz_research_collection <subcommand>`.
"""
