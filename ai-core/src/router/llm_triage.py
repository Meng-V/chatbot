"""
LLM Triage - o4-mini-based clarification and arbitration

This is Node D in the RouterSubgraph. It uses o4-mini to:
1. Generate clarification questions with button options
2. Arbitrate between close candidates
3. Output short, structured JSON (no long rewrites)
"""

import os
from typing import List, Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage


class LLMTriage:
    """
    LLM-based triage for ambiguous routing decisions.
    
    Uses o4-mini to generate structured clarification or arbitration.
    CRITICAL: Outputs SHORT JSON only, no long rewrites.
    """
    
    # Agent ID to user-friendly label mapping
    AGENT_LABELS = {
        "equipment_checkout": "Borrow equipment (laptops, chargers, cameras, etc.)",
        "libcal_hours": "Library hours or room reservations",
        "subject_librarian": "Find a subject librarian or research guide",
        "libguide": "Course guides or research resources",
        "google_site": "Library policies, services, or website info",
        "libchat_handoff": "Talk to a librarian",
        "out_of_scope": "This is not a library question",
    }
    
    def __init__(self):
        """Initialize LLM triage with o4-mini"""
        api_key = os.getenv("OPENAI_API_KEY", "")
        # Use o4-mini as specified (no temperature parameter)
        self.llm = ChatOpenAI(model="o4-mini", api_key=api_key)
    
    async def generate_clarification(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        logger=None
    ) -> Dict[str, Any]:
        """
        Generate clarification question with button options.
        
        Args:
            query: User's original question
            candidates: Top candidate agents with scores
            logger: Optional logger
            
        Returns:
            Dict with:
                - clarifying_question: str
                - options: List[Dict] with label, value, description
        """
        if logger:
            logger.log(f"🤖 [LLM Triage] Generating clarification for: {query}")
        
        # Get top 2-3 candidates
        top_candidates = candidates[:3]
        
        # Build candidate descriptions
        candidate_desc = []
        for i, cand in enumerate(top_candidates):
            agent_id = cand["agent_id"]
            label = self.AGENT_LABELS.get(agent_id, agent_id)
            candidate_desc.append(f"{i+1}. {agent_id}: {label}")
        
        candidates_text = "\n".join(candidate_desc)
        
        prompt = f"""User's question: "{query}"

The system found multiple possible interpretations:
{candidates_text}

Generate a SHORT clarification question and 3-5 button options to help the user clarify their intent.

CRITICAL RULES:
1. Do NOT add words the user didn't say (e.g., don't add "borrow" if they said "computer problems")
2. Keep the question SHORT (1 sentence max)
3. Each option should be CLEAR and DISTINCT
4. ALWAYS include "None of these (type more details)" as the last option

Output ONLY this JSON format (no other text):
{{
  "question": "Short clarifying question?",
  "options": [
    {{"label": "Option 1 description", "value": "agent_id_1"}},
    {{"label": "Option 2 description", "value": "agent_id_2"}},
    {{"label": "None of these (type more details)", "value": "other"}}
  ]
}}"""

        messages = [
            SystemMessage(content="You are a question clarification assistant. Output SHORT JSON only."),
            HumanMessage(content=prompt)
        ]
        
        try:
            response = await self.llm.ainvoke(messages)
            content = response.content.strip()
            
            # Parse JSON
            import json
            # Remove markdown code blocks if present
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()
            
            result = json.loads(content)
            
            if logger:
                logger.log(f"✅ [LLM Triage] Generated clarification with {len(result.get('options', []))} options")
            
            return {
                "clarifying_question": result.get("question", "What are you looking for?"),
                "options": result.get("options", [])
            }
            
        except Exception as e:
            if logger:
                logger.log(f"⚠️ [LLM Triage] Error generating clarification: {str(e)}")
            
            # Fallback: generate simple options from candidates
            options = []
            for cand in top_candidates:
                agent_id = cand["agent_id"]
                label = self.AGENT_LABELS.get(agent_id, agent_id)
                options.append({
                    "label": label,
                    "value": agent_id
                })
            
            options.append({
                "label": "None of these (type more details)",
                "value": "other"
            })
            
            return {
                "clarifying_question": "What are you looking for?",
                "options": options
            }
    
    async def arbitrate(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        logger=None
    ) -> Dict[str, Any]:
        """
        Arbitrate between close candidates using LLM.
        
        Args:
            query: User's original question
            candidates: Top candidate agents with scores
            logger: Optional logger
            
        Returns:
            Dict with:
                - agent_id: str (chosen agent)
                - confidence: float (0-1)
                - reasoning: str (brief explanation)
        """
        if logger:
            logger.log(f"🤖 [LLM Triage] Arbitrating between candidates for: {query}")
        
        # Get top 2 candidates
        top_candidates = candidates[:2]
        
        if len(top_candidates) < 2:
            # Not enough candidates to arbitrate
            if top_candidates:
                return {
                    "agent_id": top_candidates[0]["agent_id"],
                    "confidence": 0.7,
                    "reasoning": "Only one candidate available"
                }
            else:
                return {
                    "agent_id": "google_site",
                    "confidence": 0.5,
                    "reasoning": "No candidates found, defaulting to general search"
                }
        
        cand1 = top_candidates[0]
        cand2 = top_candidates[1]
        
        label1 = self.AGENT_LABELS.get(cand1["agent_id"], cand1["agent_id"])
        label2 = self.AGENT_LABELS.get(cand2["agent_id"], cand2["agent_id"])
        
        prompt = f"""User's question: "{query}"

Two possible interpretations:
1. {cand1["agent_id"]} ({cand1["score"]:.3f}): {label1}
   Example: {cand1.get("text", "")[:80]}
   
2. {cand2["agent_id"]} ({cand2["score"]:.3f}): {label2}
   Example: {cand2.get("text", "")[:80]}

Which interpretation BEST matches the user's intent?

CRITICAL RULES:
1. Be DECISIVE - choose the best match
2. Do NOT add words the user didn't say
3. Consider the user's exact phrasing

Output ONLY this JSON format (no other text):
{{
  "chosen_agent": "agent_id",
  "confidence": 0.8,
  "reasoning": "Brief reason (1 sentence max)"
}}"""

        messages = [
            SystemMessage(content="You are a routing arbitrator. Output SHORT JSON only."),
            HumanMessage(content=prompt)
        ]
        
        try:
            response = await self.llm.ainvoke(messages)
            content = response.content.strip()
            
            # Parse JSON
            import json
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()
            
            result = json.loads(content)
            
            agent_id = result.get("chosen_agent", cand1["agent_id"])
            confidence = result.get("confidence", 0.7)
            reasoning = result.get("reasoning", "LLM arbitration")
            
            if logger:
                logger.log(f"✅ [LLM Triage] Chose: {agent_id} (confidence: {confidence:.2f})")
                logger.log(f"   Reasoning: {reasoning}")
            
            return {
                "agent_id": agent_id,
                "confidence": confidence,
                "reasoning": reasoning
            }
            
        except Exception as e:
            if logger:
                logger.log(f"⚠️ [LLM Triage] Error in arbitration: {str(e)}")
            
            # Fallback to top candidate
            return {
                "agent_id": cand1["agent_id"],
                "confidence": 0.7,
                "reasoning": f"Arbitration error, defaulted to top candidate"
            }
