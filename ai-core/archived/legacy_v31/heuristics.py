"""
Heuristic Gate - Fast pattern-based triage

This is Node A in the RouterSubgraph. It provides:
1. Entry-ambiguous phrase detection (who can I talk to, need help, etc.)
2. Equipment checkout guardrails (must have action verbs)
3. Out-of-scope early rejection
4. Fast-path routing for clear patterns
"""

import re
from typing import Optional, Dict, Any, List
from dataclasses import dataclass


@dataclass
class HeuristicResult:
    """Result from heuristic gate"""
    matched: bool
    agent_id: Optional[str] = None
    confidence: str = "high"  # high, medium, low
    reason: Optional[str] = None
    force_triage: bool = False  # Force LLM triage instead of direct route
    block_agents: List[str] = None  # Agents to block from consideration
    
    def __post_init__(self):
        if self.block_agents is None:
            self.block_agents = []


class HeuristicGate:
    """
    Fast heuristic-based routing gate.
    
    This runs BEFORE vector search to catch:
    - Clear patterns that don't need semantic search
    - Ambiguous entry phrases that need triage
    - Out-of-scope queries
    - Equipment checkout guardrails
    """
    
    # Action verbs required for equipment checkout
    CHECKOUT_ACTION_VERBS = [
        'borrow', 'checkout', 'check out', 'rent', 'loan', 'reserve',
        'get', 'obtain', 'pick up', 'availability', 'available'
    ]
    
    # Entry-ambiguous phrases (need triage, not direct routing)
    ENTRY_AMBIGUOUS_PATTERNS = [
        r'\bwho\s+(can|could|should|do)\s+i\s+(talk|speak|contact)\b',
        r'\bwho\s+do\s+i\s+contact\b',
        r'\bneed\s+help\s+(with)?\b',
        r'\b(have\s+a\s+)?(problem|issue)\s+(with)?\b',
        r'\b(not\s+working|doesn\'t\s+work|won\'t\s+work)\b',
        r'\bcan\s+someone\s+help\b',
        r'\bi\s+need\s+assistance\b',
    ]
    
    # Out-of-scope patterns
    OUT_OF_SCOPE_PATTERNS = {
        'homework': [
            r'\b(what\'?s|what\s*is)\s*the\s*answer\s*to\b.*\b(question|problem|homework)\b',
            r'\b(answer|solve|solution)\s*(to|for)?\s*(question|problem)\s*\d+\b',
            r'\bhelp\s*(me)?\s*(with|on)?\s*(my)?\s*homework\b',
        ],
        'tech_support': [
            r'\b(wifi|internet|canvas|email|login|password)\b.*\b(issue|problem|broken|not\s*working|fix|down)\b',
            r'\b(my|a)\s*(computer|laptop|phone|device)\b.*\b(broken|not\s*working|crashed|frozen|slow|virus|issue|problem)\b',
            r'\b(fix|repair|troubleshoot)\s*(my|a)?\s*(computer|laptop|phone|device)\b',
        ],
        'general_university': [
            r'\b(admissions?|tuition|financial\s*aid|housing|dorm|dining|parking)\b',
            r'\b(register|enroll|drop)\s+(for|in)?\s*(class|course)\b',
            r'\bcampus\s+(life|events?|activities)\b',
        ]
    }
    
    def __init__(self):
        """Initialize heuristic gate with configurable patterns"""
        pass
    
    def check(self, query: str, logger=None) -> HeuristicResult:
        """
        Run heuristic checks on query.
        
        Args:
            query: User's question
            logger: Optional logger
            
        Returns:
            HeuristicResult with routing decision
        """
        query_lower = query.lower()
        
        # 1. Check for out-of-scope patterns
        oos_result = self._check_out_of_scope(query_lower)
        if oos_result.matched:
            if logger:
                logger.log(f"🚫 [Heuristic Gate] Out-of-scope: {oos_result.reason}")
            return oos_result
        
        # 2. Check for entry-ambiguous phrases
        ambiguous_result = self._check_entry_ambiguous(query_lower)
        if ambiguous_result.matched:
            if logger:
                logger.log(f"⚠️ [Heuristic Gate] Entry-ambiguous phrase detected: {ambiguous_result.reason}")
            return ambiguous_result
        
        # 3. Check equipment checkout guardrail
        checkout_result = self._check_equipment_checkout_guardrail(query_lower)
        if checkout_result.matched:
            if logger:
                logger.log(f"🛡️ [Heuristic Gate] Equipment checkout guardrail: {checkout_result.reason}")
            return checkout_result
        
        # 4. Check for clear fast-path patterns
        fastpath_result = self._check_fastpath_patterns(query_lower)
        if fastpath_result.matched:
            if logger:
                logger.log(f"⚡ [Heuristic Gate] Fast-path match: {fastpath_result.agent_id}")
            return fastpath_result
        
        # No heuristic match - proceed to vector search
        if logger:
            logger.log("✅ [Heuristic Gate] No heuristic match, proceeding to vector search")
        
        return HeuristicResult(matched=False)
    
    def _check_out_of_scope(self, query_lower: str) -> HeuristicResult:
        """Check if query is out-of-scope"""
        for scope_type, patterns in self.OUT_OF_SCOPE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    return HeuristicResult(
                        matched=True,
                        agent_id="out_of_scope",
                        confidence="high",
                        reason=f"Out-of-scope: {scope_type}"
                    )
        return HeuristicResult(matched=False)
    
    def _check_entry_ambiguous(self, query_lower: str) -> HeuristicResult:
        """
        Check for entry-ambiguous phrases that need triage.
        
        These are phrases like "who can I talk to for my computer problems"
        that could mean many things and should NOT be directly routed.
        """
        for pattern in self.ENTRY_AMBIGUOUS_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                # Check if it's about equipment checkout (has action verbs)
                has_checkout_action = any(
                    verb in query_lower for verb in self.CHECKOUT_ACTION_VERBS
                )
                
                if not has_checkout_action:
                    # Entry-ambiguous + no checkout action = force triage
                    return HeuristicResult(
                        matched=True,
                        force_triage=True,
                        confidence="low",
                        reason="Entry-ambiguous phrase without clear action"
                    )
        
        return HeuristicResult(matched=False)
    
    def _check_equipment_checkout_guardrail(self, query_lower: str) -> HeuristicResult:
        """
        Equipment checkout guardrail: Block routing to equipment_checkout
        unless query contains explicit action verbs.
        
        This prevents "computer problems" from being routed to "borrow laptop".
        """
        # Keywords that might trigger equipment checkout
        equipment_keywords = [
            'computer', 'laptop', 'chromebook', 'pc', 'macbook',
            'charger', 'adapter', 'camera', 'equipment', 'device',
            'ipad', 'tablet', 'calculator', 'headphone', 'tripod'
        ]
        
        # Check if query mentions equipment
        has_equipment_keyword = any(kw in query_lower for kw in equipment_keywords)
        
        if has_equipment_keyword:
            # Check if query has checkout action verbs
            has_checkout_action = any(
                verb in query_lower for verb in self.CHECKOUT_ACTION_VERBS
            )
            
            # Check for problem/issue keywords (anti-checkout signals)
            problem_keywords = ['problem', 'issue', 'help', 'not working', "doesn't work", 'broken', 'fix']
            has_problem_keyword = any(kw in query_lower for kw in problem_keywords)
            
            if has_problem_keyword and not has_checkout_action:
                # Equipment + problem + no action = block equipment_checkout
                return HeuristicResult(
                    matched=True,
                    force_triage=True,
                    block_agents=['equipment_checkout'],
                    confidence="low",
                    reason="Equipment mentioned with problem/issue but no checkout action"
                )
        
        return HeuristicResult(matched=False)
    
    def _check_fastpath_patterns(self, query_lower: str) -> HeuristicResult:
        """
        Check for clear patterns that can be fast-routed without vector search.
        
        These are high-confidence patterns that don't need semantic similarity.
        """
        # Library hours patterns
        hours_patterns = [
            r'\b(library|king|art|rentschler|wertz|makerspace|maker\s*space|special\s*collections?|havighurst|hamilton|middletown|gardner)\s+(hours?|open|close|closing|opening)\b',
            r'\b(hours?|open|close|closing|opening)\b.*\b(library|king|art|rentschler|wertz|makerspace|maker\s*space|special\s*collections?|havighurst|hamilton|middletown|gardner)\b',
            r'\bwhat\s+time\s+does\s+.+\s+(open|close)\b',
            r'\blibrary\s+schedule\b',
            r'\bmakerspace\b.*\b(hours?|open|close|when|schedule)\b',
            r'\b(hours?|open|close|when|schedule)\b.*\bmakerspace\b',
        ]
        for pattern in hours_patterns:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return HeuristicResult(
                    matched=True,
                    agent_id="libcal_hours",
                    confidence="high",
                    reason="Clear hours query pattern"
                )
        
        # Subject librarian patterns (very specific)
        librarian_patterns = [
            r'\b(subject|liaison)\s+librarian\b',
            r'\blibrarian\s+for\s+\w+\b',
            r'\bwho\s+is\s+the\s+\w+\s+librarian\b',
        ]
        for pattern in librarian_patterns:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return HeuristicResult(
                    matched=True,
                    agent_id="subject_librarian",
                    confidence="high",
                    reason="Clear subject librarian query"
                )
        
        # Ticket submission request (explicit - takes priority over general human help)
        ticket_patterns = [
            r'\b(put|submit|create|open|file|leave|send)\s+(in|a)?\s*ticket\b',
            r'\bticket\s+(in|for)\s+(help|support)\b',
            r'\b(leave|send)\s+(a\s+)?ticket\b',
            r'\bhow\s+(do|can)\s+i\s+(submit|put|create|open|file|leave|send)\s+(a\s+)?ticket\b',
            r'\bi\s+want\s+to\s+(put|submit|create|open|file|leave|send)\s+(a\s+)?ticket\b',
        ]
        for pattern in ticket_patterns:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return HeuristicResult(
                    matched=True,
                    agent_id="ticket_request",
                    confidence="high",
                    reason="Explicit ticket submission request"
                )
        
        # Human help request (explicit)
        human_patterns = [
            r'\btalk\s+to\s+(a\s+)?(librarian|human|person|staff)\b',
            r'\bspeak\s+(with|to)\s+(a\s+)?(librarian|human|person)\b',
            r'\bconnect\s+me\s+(to|with)\s+(a\s+)?(librarian|human)\b',
            r'\bhuman\s+help\b',
        ]
        for pattern in human_patterns:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return HeuristicResult(
                    matched=True,
                    agent_id="libchat_handoff",
                    confidence="high",
                    reason="Explicit human help request"
                )
        
        return HeuristicResult(matched=False)
