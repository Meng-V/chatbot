"""Production wiring for the Weaviate v4 client.

Holds:
  - `etl_adapter`    WRITE side: upsert / tombstone / gc (destructive)
  - `search_adapter` READ side: hybrid query (idempotent, hot path)

NAMING: this package is deliberately NOT named `weaviate`. An earlier
`src/weaviate/` shadowed the real `weaviate` SDK whenever any module
put `ai-core/src/` on sys.path (several modules do
`sys.path.insert(0, parent.parent)`), making a bare `import weaviate`
in `src/utils/weaviate_client.py` resolve to our package instead of
the SDK -> `AttributeError: module 'weaviate' has no attribute
'connect_to_custom'`. Renaming to `weaviate_adapters` removes that
whole class of bug permanently. Do NOT rename this back to `weaviate`.
"""
