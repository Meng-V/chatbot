"""Production wiring for the Weaviate v4 client.

Today this subpackage holds only the ETL adapter (`etl_adapter`).
Retrieval-side adapters live separately because they have different
consistency requirements (read-only, can tolerate slight staleness).
"""
