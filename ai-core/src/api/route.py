"""
FastAPI /route endpoint for advanced routing

This endpoint provides the new routing system with clarification support.
"""

from fastapi import APIRouter, HTTPException
from typing import Union
from src.router.schemas import RouteRequest, RouteResponse, ClarifyResponse
from src.router.router_subgraph import route_query
from src.utils.logger import AgentLogger

router = APIRouter(prefix="/route", tags=["routing"])


@router.post("", response_model=Union[RouteResponse, ClarifyResponse])
async def route_endpoint(request: RouteRequest):
    """
    Route a user query to the appropriate agent.
    
    Returns either:
    - RouteResponse: Confirmed route with agent_id
    - ClarifyResponse: Clarification needed with button options
    
    Example request:
    ```json
    {
        "query": "who can I talk to for my computer problems",
        "route_hint": null
    }
    ```
    
    Example response (clarify):
    ```json
    {
        "mode": "clarify",
        "confidence": "low",
        "clarifying_question": "What kind of computer help do you need?",
        "options": [
            {"label": "My own computer/software", "value": "out_of_scope"},
            {"label": "Library databases / VPN access", "value": "google_site"},
            {"label": "Borrow a laptop/equipment", "value": "equipment_checkout"},
            {"label": "None of these (type more details)", "value": "other"}
        ]
    }
    ```
    
    Example response (route):
    ```json
    {
        "mode": "vector",
        "agent_id": "equipment_checkout",
        "confidence": "high",
        "reason": "Clear checkout action detected",
        "candidates": [...]
    }
    ```
    """
    logger = AgentLogger()
    
    try:
        logger.log(f"🎯 [Route API] Routing query: {request.query}")
        if request.route_hint:
            logger.log(f"   Route hint: {request.route_hint}")
        
        result = await route_query(
            query=request.query,
            route_hint=request.route_hint,
            logger=logger
        )
        
        logger.log(f"✅ [Route API] Result mode: {result.get('mode')}")
        
        return result
        
    except Exception as e:
        logger.log(f"❌ [Route API] Error: {str(e)}")
        import traceback
        logger.log(f"   Traceback: {traceback.format_exc()}")
        
        raise HTTPException(
            status_code=500,
            detail=f"Routing error: {str(e)}"
        )


@router.get("/health")
async def route_health():
    """Health check for routing system"""
    return {
        "status": "healthy",
        "service": "router",
        "version": "2.0"
    }
