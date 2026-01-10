import random 
from app.utilites.email_utilites import send_email
from app.models import Trip

def generate_delivery_pin(length: int = 6) -> str:
    """
    Generate a numeric PIN (e.g. 6 digits) for delivery confirmation.
    """
    start = 10 ** (length - 1)
    end = (10 ** length) - 1
    return str(random.randint(start, end))