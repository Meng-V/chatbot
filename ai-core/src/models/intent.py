"""
Intent Normalization Models

Defines the structured output for intent normalization layer.
This is the ONLY representation of user intent used for routing.
"""

from typing import Optional, List
from pydantic import BaseModel, Field


class NormalizedIntent(BaseModel):
    """
    Normalized representation of user intent.
    
    This is produced by the intent normalization layer and consumed
    by the category classifier. It represents WHAT the user is asking,
    not HOW to answer it.
    """
    
    intent_summary: str = Field(
        description="Clear, standardized statement of what the user is asking. "
                    "Examples: 'User is asking about borrowing library equipment (laptop)', "
                    "'User is requesting library building hours', "
                    "'User wants to talk to a librarian'"
    )
    
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in understanding the user's intent (0.0-1.0)"
    )
    
    ambiguity: bool = Field(
        description="True if the user's intent is ambiguous and requires clarification"
    )
    
    ambiguity_reason: Optional[str] = Field(
        default=None,
        description="Explanation of why the intent is ambiguous, if applicable"
    )
    
    key_entities: List[str] = Field(
        default_factory=list,
        description="Key entities extracted from the query (e.g., 'laptop', 'King Library', 'biology')"
    )
    
    original_query: str = Field(
        description="Original user message for reference"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "intent_summary": "User is asking about borrowing library equipment (laptop) at Oxford campus",
                "confidence": 0.95,
                "ambiguity": False,
                "ambiguity_reason": None,
                "key_entities": ["laptop", "borrow", "equipment"],
                "original_query": "Can I borrow a laptop?"
            }
        }


class CategoryClassification(BaseModel):
    """
    Category classification result from RAG classifier.
    
    This maps a NormalizedIntent to a category from category_examples.py.
    """
    
    category: str = Field(
        description="Category name from category_examples.py"
    )
    
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in the category classification (0.0-1.0)"
    )
    
    is_out_of_scope: bool = Field(
        description="True if the category is out-of-scope for library services"
    )
    
    needs_clarification: bool = Field(
        description="True if confidence is too low or category is ambiguous"
    )
    
    clarification_reason: Optional[str] = Field(
        default=None,
        description="Reason for needing clarification, if applicable"
    )


class RoutingDecision(BaseModel):
    """
    Final routing decision combining intent, category, and agent selection.
    
    This is the complete routing trace for logging and evaluation.
    """
    
    normalized_intent: NormalizedIntent = Field(
        description="Normalized intent from intent normalization layer"
    )
    
    category: str = Field(
        description="Category from category classifier"
    )
    
    category_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in category classification"
    )
    
    primary_agent_id: Optional[str] = Field(
        default=None,
        description="Primary agent selected to handle this request"
    )
    
    secondary_agent_ids: List[str] = Field(
        default_factory=list,
        description="Optional secondary agents for multi-agent queries"
    )
    
    needs_clarification: bool = Field(
        description="True if clarification is required before routing"
    )
    
    clarification_reason: Optional[str] = Field(
        default=None,
        description="Reason for clarification, if needed"
    )
    
    routing_trace: dict = Field(
        default_factory=dict,
        description="Additional routing metadata for debugging"
    )
