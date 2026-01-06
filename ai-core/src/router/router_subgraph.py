"""
RouterSubgraph - LangGraph-based routing pipeline

This implements the 4-node routing pipeline:
- Node A: Heuristic Gate (fast pattern matching)
- Node B: Weaviate Prototypes (semantic similarity)
- Node C: Margin Decision (confidence analysis)
- Node D: LLM Triage (clarification/arbitration)

The subgraph outputs either:
1. A confirmed route (agent_id + confidence)
2. A clarification request (question + button options)
"""

from typing import Dict, Any, List
from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict

from .heuristics import HeuristicGate
from .weaviate_router import WeaviateRouter
from .margin import MarginDecision, MarginConfig
from .llm_triage import LLMTriage


class RouterState(TypedDict, total=False):
    """State for router subgraph"""
    query: str
    route_hint: str  # Explicit hint from user clarification
    
    # Heuristic results
    heuristic_matched: bool
    heuristic_agent: str
    heuristic_confidence: str
    force_triage: bool
    blocked_agents: List[str]
    
    # Weaviate results
    candidates: List[Dict[str, Any]]
    
    # Margin results
    margin_decision: str  # "direct_route", "llm_triage", "clarify"
    margin_confidence: str
    top_agent: str
    top_score: float
    margin: float
    
    # LLM results
    llm_agent: str
    llm_confidence: float
    llm_reasoning: str
    
    # Clarification
    needs_clarification: bool
    clarifying_question: str
    clarification_options: List[Dict[str, Any]]
    
    # Final output
    final_agent_id: str
    final_confidence: str
    final_mode: str  # "heuristic", "vector", "llm_judge"
    final_reason: str
    
    # Logging
    _logger: Any


class RouterSubgraph:
    """
    Multi-stage routing subgraph.
    
    Flow:
    1. Check route_hint (if user already clarified) → END
    2. Heuristic Gate → if matched, route or triage
    3. Weaviate Search → get top candidates
    4. Margin Decision → decide if confident enough
    5. LLM Triage → clarify or arbitrate if needed
    """
    
    def __init__(self, margin_config: MarginConfig = None):
        """Initialize router subgraph"""
        self.heuristic_gate = HeuristicGate()
        self.weaviate_router = WeaviateRouter()
        self.margin_decision = MarginDecision(margin_config or MarginConfig())
        self.llm_triage = LLMTriage()
        
        # Build graph
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph routing pipeline"""
        workflow = StateGraph(RouterState)
        
        # Add nodes
        workflow.add_node("check_hint", self._check_hint_node)
        workflow.add_node("heuristic_gate", self._heuristic_gate_node)
        workflow.add_node("weaviate_search", self._weaviate_search_node)
        workflow.add_node("margin_decision", self._margin_decision_node)
        workflow.add_node("llm_triage", self._llm_triage_node)
        workflow.add_node("finalize", self._finalize_node)
        
        # Set entry point
        workflow.set_entry_point("check_hint")
        
        # Add edges with conditional routing
        workflow.add_conditional_edges(
            "check_hint",
            self._route_after_hint,
            {
                "use_hint": "finalize",
                "continue": "heuristic_gate"
            }
        )
        
        workflow.add_conditional_edges(
            "heuristic_gate",
            self._route_after_heuristic,
            {
                "matched": "finalize",
                "force_triage": "llm_triage",
                "continue": "weaviate_search"
            }
        )
        
        workflow.add_edge("weaviate_search", "margin_decision")
        
        workflow.add_conditional_edges(
            "margin_decision",
            self._route_after_margin,
            {
                "direct_route": "finalize",
                "llm_triage": "llm_triage",
                "clarify": "llm_triage"
            }
        )
        
        workflow.add_edge("llm_triage", "finalize")
        workflow.add_edge("finalize", END)
        
        return workflow.compile()
    
    async def _check_hint_node(self, state: RouterState) -> RouterState:
        """Node: Check if user provided explicit route_hint"""
        logger = state.get("_logger")
        route_hint = state.get("route_hint")
        
        if route_hint and route_hint != "other":
            if logger:
                logger.log(f"🎯 [Router] Using explicit route_hint: {route_hint}")
            
            state["final_agent_id"] = route_hint
            state["final_confidence"] = "high"
            state["final_mode"] = "heuristic"
            state["final_reason"] = "User clarification"
        
        return state
    
    def _route_after_hint(self, state: RouterState) -> str:
        """Routing: After checking hint"""
        if state.get("final_agent_id"):
            return "use_hint"
        return "continue"
    
    async def _heuristic_gate_node(self, state: RouterState) -> RouterState:
        """Node A: Heuristic Gate"""
        logger = state.get("_logger")
        query = state["query"]
        
        result = self.heuristic_gate.check(query, logger)
        
        state["heuristic_matched"] = result.matched
        state["heuristic_agent"] = result.agent_id
        state["heuristic_confidence"] = result.confidence
        state["force_triage"] = result.force_triage
        state["blocked_agents"] = result.block_agents
        
        return state
    
    def _route_after_heuristic(self, state: RouterState) -> str:
        """Routing: After heuristic gate"""
        if state.get("force_triage"):
            return "force_triage"
        elif state.get("heuristic_matched"):
            return "matched"
        return "continue"
    
    async def _weaviate_search_node(self, state: RouterState) -> RouterState:
        """Node B: Weaviate Prototype Search"""
        logger = state.get("_logger")
        query = state["query"]
        blocked_agents = state.get("blocked_agents", [])
        
        candidates = await self.weaviate_router.search_prototypes(
            query=query,
            top_k=5,
            blocked_agents=blocked_agents,
            logger=logger
        )
        
        state["candidates"] = candidates
        
        return state
    
    async def _margin_decision_node(self, state: RouterState) -> RouterState:
        """Node C: Margin Decision"""
        logger = state.get("_logger")
        candidates = state.get("candidates", [])
        
        result = self.margin_decision.decide(candidates, logger)
        
        state["margin_decision"] = result.decision
        state["margin_confidence"] = result.confidence
        state["top_agent"] = result.top_agent
        state["top_score"] = result.top_score
        state["margin"] = result.margin
        
        return state
    
    def _route_after_margin(self, state: RouterState) -> str:
        """Routing: After margin decision"""
        decision = state.get("margin_decision", "llm_triage")
        return decision
    
    async def _llm_triage_node(self, state: RouterState) -> RouterState:
        """Node D: LLM Triage"""
        logger = state.get("_logger")
        query = state["query"]
        candidates = state.get("candidates", [])
        margin_decision = state.get("margin_decision", "llm_triage")
        
        if margin_decision == "clarify":
            # Generate clarification
            clarification = await self.llm_triage.generate_clarification(
                query=query,
                candidates=candidates,
                logger=logger
            )
            
            state["needs_clarification"] = True
            state["clarifying_question"] = clarification["clarifying_question"]
            state["clarification_options"] = clarification["options"]
        else:
            # Arbitrate
            arbitration = await self.llm_triage.arbitrate(
                query=query,
                candidates=candidates,
                logger=logger
            )
            
            state["llm_agent"] = arbitration["agent_id"]
            state["llm_confidence"] = arbitration["confidence"]
            state["llm_reasoning"] = arbitration["reasoning"]
        
        return state
    
    async def _finalize_node(self, state: RouterState) -> RouterState:
        """Finalize routing decision"""
        logger = state.get("_logger")
        
        # Check if clarification is needed
        if state.get("needs_clarification"):
            if logger:
                logger.log("❓ [Router] Clarification needed")
            return state
        
        # Determine final agent and mode
        if state.get("final_agent_id"):
            # Already set by hint
            pass
        elif state.get("heuristic_matched") and not state.get("force_triage"):
            state["final_agent_id"] = state["heuristic_agent"]
            state["final_confidence"] = state["heuristic_confidence"]
            state["final_mode"] = "heuristic"
            state["final_reason"] = "Heuristic pattern match"
        elif state.get("llm_agent"):
            state["final_agent_id"] = state["llm_agent"]
            state["final_confidence"] = "medium" if state["llm_confidence"] >= 0.7 else "low"
            state["final_mode"] = "llm_judge"
            state["final_reason"] = state.get("llm_reasoning", "LLM arbitration")
        elif state.get("top_agent"):
            state["final_agent_id"] = state["top_agent"]
            state["final_confidence"] = state.get("margin_confidence", "medium")
            state["final_mode"] = "vector"
            state["final_reason"] = f"Vector match (score: {state.get('top_score', 0):.3f})"
        else:
            # Fallback
            state["final_agent_id"] = "google_site"
            state["final_confidence"] = "low"
            state["final_mode"] = "vector"
            state["final_reason"] = "Fallback to general search"
        
        if logger:
            logger.log(f"✅ [Router] Final route: {state['final_agent_id']} "
                      f"({state['final_confidence']}, {state['final_mode']})")
        
        return state
    
    async def route(
        self,
        query: str,
        route_hint: str = None,
        logger=None
    ) -> Dict[str, Any]:
        """
        Route a query through the pipeline.
        
        Args:
            query: User's question
            route_hint: Optional explicit route from clarification
            logger: Optional logger
            
        Returns:
            Dict with routing result or clarification request
        """
        initial_state = {
            "query": query,
            "route_hint": route_hint,
            "_logger": logger
        }
        
        result = await self.graph.ainvoke(initial_state)
        
        # Format output
        if result.get("needs_clarification"):
            return {
                "mode": "clarify",
                "confidence": "low",
                "clarifying_question": result["clarifying_question"],
                "options": result["clarification_options"]
            }
        else:
            return {
                "mode": result["final_mode"],
                "agent_id": result["final_agent_id"],
                "confidence": result["final_confidence"],
                "reason": result.get("final_reason"),
                "candidates": [
                    {
                        "agent_id": c["agent_id"],
                        "score": c["score"],
                        "text": c.get("text", "")
                    }
                    for c in result.get("candidates", [])[:3]
                ]
            }


# Global instance
_router_instance = None

async def route_query(
    query: str,
    route_hint: str = None,
    logger=None
) -> Dict[str, Any]:
    """
    Convenience function to route a query.
    
    Args:
        query: User's question
        route_hint: Optional explicit route from clarification
        logger: Optional logger
        
    Returns:
        Routing result or clarification request
    """
    global _router_instance
    if _router_instance is None:
        _router_instance = RouterSubgraph()
    
    return await _router_instance.route(query, route_hint, logger)
