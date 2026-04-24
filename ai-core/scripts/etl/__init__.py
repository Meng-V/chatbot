"""
Smart-chatbot ETL pipeline.

Replaces the ad-hoc ingestion scripts in ai-core/scripts/ (sync_libguides,
ingest_libguides_policies_oxford, ingest_transcripts_optimized, etc.) with
one orchestrated pipeline that crawls all three campus domains, dedupes
content, tags every chunk with (campus, library, topic), and tombstones
URLs removed from the source sites.

Entry point: `python -m ai_core.scripts.etl.run_etl` (or
`python ai-core/scripts/etl/run_etl.py`).

See plan: Data preparation playbook §4 -- The ETL pipeline, end to end.
"""
