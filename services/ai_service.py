import os

from dotenv import load_dotenv
from google import genai

load_dotenv()


def generate_text(prompt: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing from the .env file")

    client = genai.Client(api_key=api_key)
    result = client.interactions.create(
        model="gemini-3.5-flash-lite",
        input=prompt,
        generation_config={
            "thinking_level": "low",
            "max_output_tokens": 800,
        },
        timeout=90,
    )
    text = result.output_text
    if not text:
        raise RuntimeError("Gemini returned an empty response")

    return text.strip()
