"""
Margin Decision - Confidence-based early stopping

This is Node C in the RouterSubgraph. It analyzes the margin between
top-1 and top-2 candidates to decide:
- High confidence: Direct route
- Medium confidence: Route with monitoring
- Low confidence: Escalate to LLM triage
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class MarginConfig:
    """Configuration for margin thresholds"""
    # Direct routing thresholds (optimized to reduce over-clarification)
    direct_score_threshold: float = 0.65  # Minimum top-1 score for direct route (lowered from 0.75)
    direct_margin_threshold: float = 0.15  # Minimum margin for direct route (lowered from 0.20)
    
    # Low confidence thresholds (trigger triage)
    lowconf_score_threshold: float = 0.50  # Below this = low confidence (lowered from 0.60)
    lowconf_margin_threshold: float = 0.08  # Below this = low confidence (lowered from 0.10)
    
    # Clarification thresholds (only for truly ambiguous cases)
    clarify_margin_threshold: float = 0.03  # Very close = need clarification (lowered from 0.05)


@dataclass
class MarginResult:
    """Result from margin decision"""
    decision: str  # "direct_route", "llm_triage", "clarify"
    confidence: str  # "high", "medium", "low"
    top_agent: str
    top_score: float
    margin: Optional[float] = None
    second_agent: Optional[str] = None
    second_score: Optional[float] = None
    reason: str = ""


class MarginDecision:
    """
    Margin-based decision maker for routing confidence.
    
    Analyzes the gap between top-1 and top-2 candidates to determine
    if we can route directly or need LLM triage/clarification.
    """
    
    def __init__(self, config: Optional[MarginConfig] = None):
        """
        Initialize margin decision maker.
        
        Args:
            config: Optional custom configuration
        """
        self.config = config or MarginConfig()
    
    def decide(
        self,
        candidates: List[Dict[str, Any]],
        logger=None
    ) -> MarginResult:
        """
        Make routing decision based on candidate scores and margins.
        
        Args:
            candidates: List of candidates from Weaviate search
                Each dict should have: agent_id, score, text
            logger: Optional logger
            
        Returns:
            MarginResult with routing decision
        """
        if not candidates:
            if logger:
                logger.log("⚠️ [Margin Decision] No candidates provided")
            return MarginResult(
                decision="llm_triage",
                confidence="low",
                top_agent="unknown",
                top_score=0.0,
                reason="No candidates found"
            )
        
        # Aggregate scores by agent_id
        agent_scores = {}
        agent_texts = {}
        for cand in candidates:
            agent_id = cand["agent_id"]
            score = cand["score"]
            text = cand.get("text", "")
            
            if agent_id not in agent_scores:
                agent_scores[agent_id] = []
                agent_texts[agent_id] = []
            
            agent_scores[agent_id].append(score)
            agent_texts[agent_id].append(text)
        
        # Calculate average scores for each agent
        agent_avg_scores = {
            agent: sum(scores) / len(scores)
            for agent, scores in agent_scores.items()
        }
        
        # Sort by average score
        sorted_agents = sorted(
            agent_avg_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        if not sorted_agents:
            return MarginResult(
                decision="llm_triage",
                confidence="low",
                top_agent="unknown",
                top_score=0.0,
                reason="No valid agents"
            )
        
        top_agent, top_score = sorted_agents[0]
        
        # Single candidate case
        if len(sorted_agents) == 1:
            if top_score >= self.config.direct_score_threshold:
                confidence = "high"
                decision = "direct_route"
                reason = f"Single candidate with high score ({top_score:.3f})"
            elif top_score >= self.config.lowconf_score_threshold:
                confidence = "medium"
                decision = "direct_route"
                reason = f"Single candidate with medium score ({top_score:.3f})"
            else:
                confidence = "low"
                decision = "llm_triage"
                reason = f"Single candidate with low score ({top_score:.3f})"
            
            if logger:
                logger.log(f"📊 [Margin Decision] {decision} - {reason}")
            
            return MarginResult(
                decision=decision,
                confidence=confidence,
                top_agent=top_agent,
                top_score=top_score,
                reason=reason
            )
        
        # Multiple candidates - calculate margin
        second_agent, second_score = sorted_agents[1]
        margin = top_score - second_score
        margin_pct = margin / top_score if top_score > 0 else 0
        
        if logger:
            logger.log(f"📊 [Margin Decision] Top-1: {top_agent} ({top_score:.3f}) | "
                      f"Top-2: {second_agent} ({second_score:.3f}) | "
                      f"Margin: {margin:.3f} ({margin_pct:.1%})")
        
        # Decision logic
        decision = "direct_route"
        confidence = "medium"
        reason = ""
        
        # High confidence: good score + good margin
        if (top_score >= self.config.direct_score_threshold and
            margin >= self.config.direct_margin_threshold):
            confidence = "high"
            decision = "direct_route"
            reason = f"High score ({top_score:.3f}) with good margin ({margin:.3f})"
        
        # Medium confidence: decent score + decent margin
        elif (top_score >= self.config.lowconf_score_threshold and
              margin >= self.config.lowconf_margin_threshold):
            confidence = "medium"
            decision = "direct_route"
            reason = f"Medium score ({top_score:.3f}) with acceptable margin ({margin:.3f})"
        
        # Very close scores: need clarification
        elif margin < self.config.clarify_margin_threshold:
            confidence = "low"
            decision = "clarify"
            reason = f"Very close scores ({top_score:.3f} vs {second_score:.3f}), margin too small ({margin:.3f})"
        
        # Low confidence: escalate to LLM
        else:
            confidence = "low"
            decision = "llm_triage"
            reason = f"Low score ({top_score:.3f}) or small margin ({margin:.3f})"
        
        if logger:
            logger.log(f"✅ [Margin Decision] {decision} ({confidence}) - {reason}")
        
        return MarginResult(
            decision=decision,
            confidence=confidence,
            top_agent=top_agent,
            top_score=top_score,
            margin=margin,
            second_agent=second_agent,
            second_score=second_score,
            reason=reason
        )
    
    def update_config(self, **kwargs):
        """
        Update configuration thresholds.
        
        Example:
            margin_decision.update_config(
                direct_score_threshold=0.80,
                direct_margin_threshold=0.25
            )
        """
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
