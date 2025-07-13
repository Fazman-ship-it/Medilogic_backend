from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Legal"])

@router.get("/privacy-policy", response_class=HTMLResponse)
def privacy_policy():
    return """
    <h1>Privacy Policy</h1>
    <p>This is the privacy policy for Medilogic...</p>
    """

@router.get("/terms-of-service", response_class=HTMLResponse)
def terms_of_service():
    return """
    <h1>Terms of Service</h1>
    <p>These terms govern your use of Medilogic...</p>
    """