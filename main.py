import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from pydantic import BaseModel, Field

from routers.interview import router as interview_router

load_dotenv()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500", "http://localhost:5500", "http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(interview_router)

api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key) if api_key else None


class AskRequest(BaseModel):
    prompt: str = Field(min_length=1)


@app.get("/")
def home():
    return {"message": "Hello, ByteForce! 🚀"}


@app.post("/ask")
def ask_gemini(request: AskRequest):
    if client is None:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY is missing from the backend .env file",
        )

    try:
        result = client.interactions.create(
            model="gemini-3.8-flash",
            input=request.prompt,
        )
        return {"answer": result.output_text}
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Gemini request failed. Check the backend terminal for details.",
        ) from exc
