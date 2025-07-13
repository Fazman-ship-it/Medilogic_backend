# utils/ai_assistant.py
# app/utilities/ai_assistant.py

import os
from dotenv import load_dotenv
from openai import OpenAI

# ✅ Load environment variables from .env
load_dotenv()

# ✅ Get the API key from environment
api_key = os.getenv("OPENAI_API_KEY")

# ✅ Optional: Debug print to confirm key is loaded
if not api_key:
    raise ValueError("OPENAI_API_KEY is not set. Please check your .env file.")

# ✅ Initialize OpenAI client
client = OpenAI(api_key=api_key)

# ✅ AI Assistant function
def ask_chatgpt(prompt: str) -> str:
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  # or "gpt-4" if you have access
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=300,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"OpenAI Error: {e}"