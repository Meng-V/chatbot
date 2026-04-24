"""
Grounded synthesis layer.

The synthesizer's job: given a user question and a numbered evidence
bundle from retrieval, produce a structured answer with citations OR
refuse cleanly.

Four pieces:
  - synthesizer.py     -- calls the LLM, parses structured output,
                          orchestrates corrections + post-processing.
  - post_processor.py  -- the LOAD-BEARING citation enforcement layer.
                          Four independent checks (confidence gate,
                          citation match, URL validation, cross-campus
                          guard). Downgrades to a refusal if ANY fails.
                          Never silently drops invalid citations.
  - refusal_templates  -- templated refusal copy keyed by trigger so
                          each refusal type can have appropriate,
                          scope-aware phrasing.
  - corrections.py     -- applies active ManualCorrection rows to the
                          retrieval bundle BEFORE synthesis (suppress /
                          replace / pin / blacklist).

See plan: Citation and refusal contract.
"""

from src.synthesis.corrections import (
    CorrectionOutcome,
    EvidenceChunk,
    ManualCorrection,
    apply_corrections,
)
from src.synthesis.post_processor import (
    Citation,
    PostProcessorResult,
    Refusal,
    SynthesizerOutput,
    ValidationFailure,
    process_synthesizer_output,
)
from src.synthesis.refusal_templates import (
    RefusalContext,
    RefusalTrigger,
    render_refusal,
)
from src.synthesis.synthesizer import (
    SynthesisRequest,
    SynthesisResult,
    synthesize,
)

__all__ = [
    "Citation",
    "CorrectionOutcome",
    "EvidenceChunk",
    "ManualCorrection",
    "PostProcessorResult",
    "Refusal",
    "RefusalContext",
    "RefusalTrigger",
    "SynthesisRequest",
    "SynthesisResult",
    "SynthesizerOutput",
    "ValidationFailure",
    "apply_corrections",
    "process_synthesizer_output",
    "render_refusal",
    "synthesize",
]
