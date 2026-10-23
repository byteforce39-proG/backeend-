import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.interview_service import start_interview, submit_answer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/interview", tags=["Interview"])


class StartInterviewRequest(BaseModel):
    role: str = Field(min_length=1, description="Target job role, for example Backend Developer")
    experience_level: str = Field(min_length=1, description="Candidate level, for example Fresher")
    interview_type: str = Field(min_length=1, description="For example Technical or Behavioral")
    difficulty: str = Field(min_length=1, description="For example Beginner, Intermediate, or Advanced")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "role": "Backend Developer",
                    "experience_level": "Fresher",
                    "interview_type": "Technical",
                    "difficulty": "Beginner",
                }
            ]
        }
    }


class SubmitAnswerRequest(BaseModel):
    session_id: str = Field(
        min_length=1,
        description="Copy the session_id from a successful POST /interview/start response.",
    )
    answer: str = Field(min_length=1, description="Your answer to the current interview question")
    end_interview: bool = Field(
        default=False,
        description="Set true when the candidate chooses to finish and receive overall feedback.",
    )


@router.post("/start", description="Start a personalized interview. Save the returned session_id for every answer.")
def create_interview(request: StartInterviewRequest):
    try:
        return start_interview(
            role=request.role.strip(),
            experience_level=request.experience_level.strip(),
            interview_type=request.interview_type.strip(),
            difficulty=request.difficulty.strip(),
        )
    except Exception as exc:
        logger.exception("Failed to start interview")
        raise HTTPException(
            status_code=502,
            detail="Could not generate the interview question. Check the backend terminal.",
        ) from exc


@router.post("/answer", description="Submit an answer for AI feedback and the next adaptive question. Set end_interview=true to finish and get overall feedback.")
def answer_interview(request: SubmitAnswerRequest):
    try:
        return submit_answer(
            request.session_id.strip(),
            request.answer.strip(),
            end_interview=request.end_interview,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to process interview answer")
        raise HTTPException(
            status_code=502,
            detail="Could not process the answer. Check the backend terminal.",
        ) from exc
