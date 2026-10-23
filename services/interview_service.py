import json
import sqlite3
from pathlib import Path
from uuid import uuid4

from services.ai_service import generate_text

DATABASE_PATH = Path(__file__).resolve().parents[1] / "interviews.db"


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def _initialize_database() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS interviews (
                session_id TEXT PRIMARY KEY,
                settings TEXT NOT NULL,
                current_question TEXT NOT NULL,
                history TEXT NOT NULL
            )
            """
        )


_initialize_database()


def start_interview(
    role: str,
    experience_level: str,
    interview_type: str,
    difficulty: str,
) -> dict:
    settings = {
        "role": role,
        "experience_level": experience_level,
        "interview_type": interview_type,
        "difficulty": difficulty,
    }

    prompt = f"""
You are a professional mock interviewer.
Create the first interview question for a candidate with these settings:
Role: {role}
Experience: {experience_level}
Interview type: {interview_type}
Difficulty: {difficulty}

Return only one question. Do not add an introduction or answer.
"""
    question = generate_text(prompt).strip()
    session_id = str(uuid4())

    with _connect() as connection:
        connection.execute(
            "INSERT INTO interviews (session_id, settings, current_question, history) VALUES (?, ?, ?, ?)",
            (session_id, json.dumps(settings), question, "[]"),
        )

    return {
        "session_id": session_id,
        "question": question,
        "question_number": 1,
    }


def submit_answer(session_id: str, answer: str, end_interview: bool = False) -> dict:
    with _connect() as connection:
        row = connection.execute(
            "SELECT settings, current_question, history FROM interviews WHERE session_id = ?",
            (session_id,),
        ).fetchone()

    if row is None:
        raise ValueError("Interview session not found. Start an interview and use the exact session_id returned by POST /interview/start.")

    session = {
        "settings": json.loads(row["settings"]),
        "current_question": row["current_question"],
        "history": json.loads(row["history"]),
    }

    current_answer = {
        "question": session["current_question"],
        "answer": answer,
    }
    session["history"].append(current_answer)

    question_number = len(session["history"])

    if end_interview:
        settings = session["settings"]
        transcript = "\n".join(
            f"Question: {item['question']}\nAnswer: {item['answer']}"
            for item in session["history"]
        )

        prompt = f"""
You are evaluating a mock interview for a {settings['role']} candidate.
Experience level: {settings['experience_level']}
Interview type: {settings['interview_type']}
Difficulty: {settings['difficulty']}

Interview transcript:
{transcript}

Give concise, specific feedback with:
- Feedback on the candidate's latest answer
- Overall assessment
- Strengths
- Areas to improve
- Communication feedback
- Technical knowledge and problem-solving feedback
- Three practical tips for the next interview
"""
        feedback = generate_text(prompt).strip()
        with _connect() as connection:
            connection.execute("DELETE FROM interviews WHERE session_id = ?", (session_id,))

        return {
            "done": True,
            "question_number": question_number,
            "final_feedback": feedback,
        }

    settings = session["settings"]
    previous_answers = "\n".join(
        f"Q: {item['question']}\nA: {item['answer']}"
        for item in session["history"]
    )

    prompt = f"""
You are conducting a mock interview for a {settings['role']} candidate.
Experience level: {settings['experience_level']}
Interview type: {settings['interview_type']}
Difficulty: {settings['difficulty']}

Previous questions and answers:
{previous_answers}

Evaluate the candidate's latest answer with 1-2 specific, constructive sentences,
then ask the next single interview question. Adapt the question to the candidate's
answers and selected difficulty. Return exactly these two labeled sections and no
other text:
FEEDBACK: <specific feedback on the latest answer>
NEXT_QUESTION: <one relevant next question>
"""
    generated = generate_text(prompt).strip()
    feedback_text, separator, question_text = generated.partition("NEXT_QUESTION:")
    if not separator or not feedback_text.strip().startswith("FEEDBACK:"):
        raise RuntimeError("Gemini did not return answer feedback and the next question in the expected format")

    answer_feedback = feedback_text.strip()[len("FEEDBACK:"):].strip()
    next_question = question_text.strip()
    if not answer_feedback or not next_question:
        raise RuntimeError("Gemini returned empty answer feedback or next question")

    current_answer["feedback"] = answer_feedback
    session["current_question"] = next_question

    with _connect() as connection:
        connection.execute(
            "UPDATE interviews SET current_question = ?, history = ? WHERE session_id = ?",
            (next_question, json.dumps(session["history"]), session_id),
        )

    return {
        "done": False,
        "question_number": question_number + 1,
        "answer_feedback": answer_feedback,
        "next_question": next_question,
    }
