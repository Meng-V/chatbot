"""
Weaviate Router - Prototype-based semantic routing

This is Node B in the RouterSubgraph. It uses Weaviate to search
for high-quality prototypes (NOT bulk samples) to classify queries.

Key differences from old approach:
- Uses 8-12 prototypes per agent (not 60+ samples)
- Prototypes emphasize action verbs and distinctive features
- Separate collection from training samples
"""

import os
import sys
import asyncio
from typing import List, Dict, Any, Optional
from pathlib import Path
from langchain_openai import OpenAIEmbeddings

# Import centralized Weaviate client
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.weaviate_client import get_weaviate_client


class WeaviateRouter:
    """
    Prototype-based semantic router using Weaviate.

    Uses a dedicated 'Prototypes' collection with high-quality,
    high-distinction examples for each agent.
    """

    def __init__(self):
        """Initialize Weaviate router"""
        self.client = None
        self.collection_name = "AgentPrototypes"
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-large", api_key=os.getenv("OPENAI_API_KEY", "")
        )

    def _connect(self):
        """Connect to Weaviate using centralized client factory."""
        if self.client is None:
            self.client = get_weaviate_client()

    def _disconnect(self):
        """Disconnect from Weaviate (v3 client doesn't need explicit close)"""
        self.client = None

    def __del__(self):
        """Cleanup when object is destroyed"""
        self._disconnect()

    async def search_prototypes(
        self, query: str, top_k: int = 5, blocked_agents: List[str] = None, logger=None
    ) -> List[Dict[str, Any]]:
        """
        Search for top-K prototype matches.

        Args:
            query: User's question
            top_k: Number of top matches to return
            blocked_agents: List of agent IDs to exclude from results
            logger: Optional logger

        Returns:
            List of matches with agent_id, score, text, and metadata
        """
        self._connect()

        if blocked_agents is None:
            blocked_agents = []

        if logger:
            logger.log(f"🔍 [Weaviate Router] Searching prototypes for: {query}")

        # Embed query
        query_embedding = await self.embeddings.aembed_query(query)

        try:
            # V4 API: Query with near vector
            collection = self.client.collections.get(self.collection_name)
            response = collection.query.near_vector(
                near_vector=query_embedding,
                limit=top_k * 2,
                return_metadata=['distance']
            )

            matches = []
            for obj in response.objects:
                distance = obj.metadata.distance if obj.metadata else 1.0
                certainty = 1.0 - min(distance, 1.0)
                agent_id = obj.properties.get("agent_id", "")
                if agent_id in blocked_agents:
                    continue

                matches.append({
                    "agent_id": agent_id,
                    "prototype_text": obj.properties.get("prototype_text", ""),
                    "category": obj.properties.get("category", ""),
                    "is_action_based": obj.properties.get("is_action_based", False),
                    "priority": obj.properties.get("priority", 5),
                    "certainty": certainty,
                    "distance": distance
                })

                if len(matches) >= top_k:
                    break

        except Exception as e:
            if logger:
                logger.log(f"❌ [Weaviate Router] Search error: {str(e)}")
            return []

        if logger:
            logger.log(f"📊 [Weaviate Router] Found {len(matches)} prototype matches")
            for i, match in enumerate(matches[:3]):
                logger.log(
                    f"   {i+1}. {match['agent_id']} ({match['certainty']:.3f}): {match['prototype_text'][:60]}..."
                )

        return matches

    async def ensure_collection(self):
        """Ensure the prototypes collection exists"""
        self._connect()

        # V4 API: Check if collection exists
        exists = self.client.collections.exists(self.collection_name)
        
        if not exists:
            # V4 API: Create collection with proper schema
            import weaviate.classes.config as wvc
            
            self.client.collections.create(
                name=self.collection_name,
                description="High-quality prototypes for agent routing (8-12 per agent)",
                properties=[
                    wvc.Property(name="agent_id", data_type=wvc.DataType.TEXT, description="Agent identifier"),
                    wvc.Property(name="prototype_text", data_type=wvc.DataType.TEXT, description="Prototype question/phrase"),
                    wvc.Property(name="category", data_type=wvc.DataType.TEXT, description="Category name"),
                    wvc.Property(name="is_action_based", data_type=wvc.DataType.BOOL, description="Whether this prototype emphasizes action verbs"),
                    wvc.Property(name="priority", data_type=wvc.DataType.INT, description="Priority level (higher = more important)"),
                ]
            )

    async def add_prototype(
        self,
        agent_id: str,
        prototype_text: str,
        category: str = "",
        is_action_based: bool = False,
        priority: int = 1,
    ):
        """
        Add a single prototype to the collection.

        Args:
            agent_id: Agent identifier
            prototype_text: The prototype question/phrase
            category: Optional category name
            is_action_based: Whether this emphasizes action verbs
            priority: Priority level (1-3, higher = more important)
        """
        self._connect()
        await self.ensure_collection()

        collection = self.client.collections.get(self.collection_name)

        # Embed prototype
        embedding = await self.embeddings.aembed_query(prototype_text)

        # Add to collection
        collection.data.insert(
            properties={
                "agent_id": agent_id,
                "prototype_text": prototype_text,
                "category": category,
                "is_action_based": is_action_based,
                "priority": priority,
            },
            vector=embedding,
        )

    async def bulk_add_prototypes(self, prototypes: List[Dict[str, Any]]):
        """
        Bulk add prototypes to collection.

        Args:
            prototypes: List of dicts with keys:
                - agent_id: str
                - prototype_text: str
                - category: str (optional)
                - is_action_based: bool (optional)
                - priority: int (optional)
        """
        self._connect()
        await self.ensure_collection()

        collection = self.client.collections.get(self.collection_name)

        with collection.batch.dynamic() as batch:
            for proto in prototypes:
                embedding = await self.embeddings.aembed_query(proto["prototype_text"])

                batch.add_object(
                    properties={
                        "agent_id": proto["agent_id"],
                        "prototype_text": proto["prototype_text"],
                        "category": proto.get("category", ""),
                        "is_action_based": proto.get("is_action_based", False),
                        "priority": proto.get("priority", 1),
                    },
                    vector=embedding,
                )

    async def clear_collection(self):
        """Clear all prototypes from collection"""
        self._connect()

        try:
            self.client.collections.delete(self.collection_name)
        except Exception:
            pass

        await self.ensure_collection()
