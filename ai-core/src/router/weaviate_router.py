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
import weaviate
import weaviate.classes as wvc
from typing import List, Dict, Any, Optional
from langchain_openai import OpenAIEmbeddings


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
            model="text-embedding-3-large",
            api_key=os.getenv("OPENAI_API_KEY", "")
        )
    
    def _connect(self):
        """Connect to Weaviate if not already connected"""
        if self.client is None:
            scheme = os.getenv("WEAVIATE_SCHEME", "http")
            api_key = os.getenv("WEAVIATE_API_KEY", "")
            host = os.getenv("WEAVIATE_HOST", "localhost")
            
            if scheme == "https" and api_key:
                self.client = weaviate.connect_to_weaviate_cloud(
                    cluster_url=f"https://{host}",
                    auth_credentials=weaviate.auth.AuthApiKey(api_key)
                )
            else:
                self.client = weaviate.connect_to_local()
    
    def _disconnect(self):
        """Disconnect from Weaviate"""
        if self.client is not None:
            try:
                self.client.close()
            except:
                pass
            self.client = None
    
    def __del__(self):
        """Cleanup when object is destroyed"""
        self._disconnect()
    
    async def search_prototypes(
        self,
        query: str,
        top_k: int = 5,
        blocked_agents: List[str] = None,
        logger=None
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
        
        # Get collection
        try:
            collection = self.client.collections.get(self.collection_name)
        except Exception as e:
            if logger:
                logger.log(f"⚠️ [Weaviate Router] Collection not found: {str(e)}")
            return []
        
        # Search
        try:
            response = collection.query.near_vector(
                near_vector=query_embedding,
                limit=top_k * 2,  # Get extra to filter blocked agents
                return_metadata=wvc.query.MetadataQuery(distance=True, certainty=True)
            )
        except Exception as e:
            if logger:
                logger.log(f"❌ [Weaviate Router] Search error: {str(e)}")
            return []
        
        # Parse results
        matches = []
        for obj in response.objects:
            agent_id = obj.properties.get("agent_id")
            
            # Skip blocked agents
            if agent_id in blocked_agents:
                continue
            
            matches.append({
                "agent_id": agent_id,
                "score": obj.metadata.certainty if obj.metadata.certainty else 0.0,
                "text": obj.properties.get("prototype_text", ""),
                "category": obj.properties.get("category", ""),
                "is_action_based": obj.properties.get("is_action_based", False),
                "distance": obj.metadata.distance if obj.metadata.distance else 1.0
            })
            
            if len(matches) >= top_k:
                break
        
        if logger:
            logger.log(f"📊 [Weaviate Router] Found {len(matches)} prototype matches")
            for i, match in enumerate(matches[:3]):
                logger.log(f"   {i+1}. {match['agent_id']} ({match['score']:.3f}): {match['text'][:60]}...")
        
        return matches
    
    async def ensure_collection(self):
        """Ensure the prototypes collection exists"""
        self._connect()
        
        if not self.client.collections.exists(self.collection_name):
            self.client.collections.create(
                name=self.collection_name,
                description="High-quality prototypes for agent routing (8-12 per agent)",
                vector_config=wvc.config.Configure.Vectors.self_provided(),
                properties=[
                    wvc.config.Property(
                        name="agent_id",
                        data_type=wvc.config.DataType.TEXT,
                        description="Agent identifier"
                    ),
                    wvc.config.Property(
                        name="prototype_text",
                        data_type=wvc.config.DataType.TEXT,
                        description="Prototype question/phrase"
                    ),
                    wvc.config.Property(
                        name="category",
                        data_type=wvc.config.DataType.TEXT,
                        description="Category name"
                    ),
                    wvc.config.Property(
                        name="is_action_based",
                        data_type=wvc.config.DataType.BOOL,
                        description="Whether this prototype emphasizes action verbs"
                    ),
                    wvc.config.Property(
                        name="priority",
                        data_type=wvc.config.DataType.INT,
                        description="Priority level (higher = more important)"
                    ),
                ]
            )
    
    async def add_prototype(
        self,
        agent_id: str,
        prototype_text: str,
        category: str = "",
        is_action_based: bool = False,
        priority: int = 1
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
                "priority": priority
            },
            vector=embedding
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
                        "priority": proto.get("priority", 1)
                    },
                    vector=embedding
                )
    
    async def clear_collection(self):
        """Clear all prototypes from collection"""
        self._connect()
        
        try:
            self.client.collections.delete(self.collection_name)
        except Exception:
            pass
        
        await self.ensure_collection()
