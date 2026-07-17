"""Classification module for RAG-based question categorization."""

from src.classification.rag_classifier import RAGQuestionClassifier, classify_with_rag
from src.classification.category_examples import (
    get_all_examples_for_embedding,
    get_boundary_cases,
    get_category_description,
    get_category_agent,
    ALL_CATEGORIES
)

__all__ = [
    "RAGQuestionClassifier",
    "classify_with_rag",
    "get_all_examples_for_embedding",
    "get_boundary_cases",
    "get_category_description",
    "get_category_agent",
    "ALL_CATEGORIES",
]
