
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.utilites.ai_assistant import ask_chatgpt
from app.schemas import ChatRequest, ChatResponse
from app.database import get_db
from app.dependencies import require_role  
from app.utilites.logging import log_activity
from app import models
router = APIRouter(prefix="/ai", tags=["AI Assistant"])

@router.post("/ask", response_model=ChatResponse)
def ask_ai(
    chat: ChatRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role("admin", "driver", "client")) 
):
    #  Step 1: Get AI response
    reply = ask_chatgpt(chat.prompt)
    if reply.startswith("Error:"):
        raise HTTPException(status_code=500, detail=reply)

    # Step 2: Log the query (multi-tenant aware)
    log_activity(
        db=db,
        user_id=user.id,
        organisation_id=user.organization_id,
        action="ai_assistant_query",
        details=f"Prompt: '{chat.prompt}' → Response: '{reply[:120]}...'"  # truncate long response
    )

    #  Step 3: Return response
    return {"question": chat.prompt, "answer": reply}