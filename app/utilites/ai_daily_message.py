# app/ai_utils.py
import openai
from app.config import settings

openai.api_key = settings.OPENAI_API_KEY

def generate_ai_tip():
    prompt = """
    Generate a professional short tip (2–3 sentences) about medical waste management, healthcare logistics, 
    or sustainability. The style should be concise, expert, and relevant to UK healthcare providers.
    """
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=80
    )
    return response.choices[0].message["content"].strip()