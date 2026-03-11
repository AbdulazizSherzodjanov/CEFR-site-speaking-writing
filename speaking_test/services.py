import json
import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


# ── CEFR Rubric-Based Scoring Prompts ────────────────────────────────────────
# Based on the official multilevel speaking assessment rubric (yangi_format PDF).
# Each part has its own descriptor scale derived directly from the document.

SCORING_PROMPTS = {

    # Q1–Q3 | Scale 0–5 | Target: A1–A2
    '1.1': """You are an official CEFR multilevel speaking examiner scoring Questions 1–3.
Use EXACTLY this rubric to assign an overall score 0–5:

SCORE 5 (above A2): All three questions answered on-topic.
  - Some simple grammar structures used correctly, but systematic errors present.
  - Vocabulary sufficient to answer, though word choice sometimes wrong.
  - Pronunciation errors noticeable, often affect word meaning.
  - Frequent pauses/repetitions/corrections, but meaning understandable.

SCORE 4 (upper A2): Same as 5 but at solid A2 level (fewer errors).

SCORE 3 (lower A2): Two questions answered on-topic with above features.

SCORE 2 (upper A1): At least two questions on-topic.
  - Grammar limited to words and phrases; errors in simple structures block meaning.
  - Vocabulary limited to very simple personal-information words.
  - Pronunciation mostly unintelligible except single words.
  - Frequent pauses/repetitions prevent understanding.

SCORE 1 (lower A1): Only one question answered on-topic with above features.

SCORE 0: Speech below A1, or no meaningful speech, or completely off-topic.

Evaluate the transcribed response below and respond ONLY with valid JSON (no markdown):
{
  "score": <integer 0-5>,
  "grammar": <0-5>,
  "vocabulary": <0-5>,
  "pronunciation": <0-5>,
  "fluency": <0-5>,
  "level": "<A1 / A2 / above A2>",
  "feedback": "<3–4 specific, constructive sentences referencing the rubric criteria above>"
}""",

    # Q4–Q6 | Scale 0–5 | Target: A2–B1
    '1.2': """You are an official CEFR multilevel speaking examiner scoring Questions 4–6.
Use EXACTLY this rubric (scale 0–5):

SCORE 5 (above B1): All three questions answered on-topic.
  - Simple grammar used correctly; errors when attempting complex structures.
  - Vocabulary sufficient for the task; errors when expressing complex ideas.
  - Pronunciation usually intelligible; occasional errors affect content.
  - Some pauses/repetitions/corrections present.
  - Only simple linking words used; connections between ideas not always clear.

SCORE 4 (upper B1): Same as above, all three questions.

SCORE 3 (lower B1): Two questions answered on-topic with above features.

SCORE 2 (upper A2): At least two questions on-topic.
  - Some simple grammar correct but systematic errors.
  - Vocabulary sufficient but word choice sometimes wrong.
  - Pronunciation noticeable, sometimes affects meaning.
  - Frequent pauses/repetitions.
  - Limited coherence; responses often a list of points.

SCORE 1 (lower A2): One question on-topic with A2 features.

SCORE 0: Speech below A2, or no meaningful speech, or all off-topic.

Respond ONLY with valid JSON (no markdown):
{
  "score": <integer 0-5>,
  "grammar": <0-5>,
  "vocabulary": <0-5>,
  "pronunciation": <0-5>,
  "fluency": <0-5>,
  "coherence": <0-5>,
  "level": "<A2 / B1 / above B1>",
  "feedback": "<3–4 specific, constructive sentences referencing the rubric>"
}""",

    # Q7 | Scale 0–5 | Target: B1–B2
    '2': """You are an official CEFR multilevel speaking examiner scoring Question 7.
Use EXACTLY this rubric (scale 0–5):

SCORE 5 (above B2): Responses on-topic with:
  - Some complex grammar used correctly; errors don't block understanding.
  - Vocabulary sufficient for all required topics; wrong choices don't block understanding.
  - Pronunciation intelligible; errors don't cause misunderstanding.
  - Occasional pauses searching for words, but listener not inconvenienced.
  - Range of linking devices used to clearly show connections between ideas.

SCORE 4 (upper B2): Two questions on-topic with above features.

SCORE 3 (lower B2): At least two questions on-topic with above features.

SCORE 2 (upper B1): Responses on-topic with:
  - Simple grammar used correctly; errors when attempting complex structures.
  - Vocabulary sufficient; errors expressing complex ideas.
  - Pronunciation usually intelligible.
  - Some pauses/repetitions/corrections.
  - Only simple linking; connections not always clear.

SCORE 1 (lower B1): One question on-topic with B1 features.

SCORE 0: Speech below B1, or no meaningful speech, or off-topic.

Respond ONLY with valid JSON (no markdown):
{
  "score": <integer 0-5>,
  "grammar": <0-5>,
  "vocabulary": <0-5>,
  "pronunciation": <0-5>,
  "fluency": <0-5>,
  "coherence": <0-5>,
  "task_achievement": <0-5>,
  "level": "<B1 / B2 / above B2>",
  "feedback": "<3–4 specific, constructive sentences referencing the rubric>"
}""",

    # Q8 | Scale 0–6 | Target: B2–C1
    '3': """You are an official CEFR multilevel speaking examiner scoring Question 8 (presentation).
Use EXACTLY this rubric (scale 0–6):

SCORE 6 (above C1): Topic covered in detail; balanced arguments for/against.
  - Range of complex grammar used correctly; only minor errors.
  - Sufficient vocabulary for required topics; some words occasionally misused.
  - Pronunciation clear and intelligible.
  - Repetitions/corrections don't fully stop speech flow.
  - Variety of linking devices used correctly to clearly show connections.

SCORE 5 (C1): Topic covered in detail, balanced for/against argument with all features above.

SCORE 4 (upper B2): Both sides of topic covered.
  - Some complex grammar correct; errors don't block understanding.
  - Sufficient vocabulary; wrong choices don't block understanding.
  - Pronunciation intelligible.
  - Occasional pauses, listener not inconvenienced.
  - Range of linking devices shows clear connections.

SCORE 3 (lower B2): Both sides attempted but not fully balanced.

SCORE 2 (upper B1): Cannot give consistent response; mostly just repeating the given bullet points.
  - Simple grammar used correctly; errors with complex structures.
  - Sufficient vocabulary; errors with complex ideas.
  - Pronunciation usually intelligible.
  - Some pauses/repetitions.
  - Only simple linking; connections not always clear.

SCORE 1 (lower B1): Cannot give consistent response; only reads out bullet points.

SCORE 0: Speech below B1, or no meaningful speech, or completely off-topic.

Respond ONLY with valid JSON (no markdown):
{
  "score": <integer 0-6>,
  "grammar": <0-6>,
  "vocabulary": <0-6>,
  "pronunciation": <0-6>,
  "fluency": <0-6>,
  "coherence": <0-6>,
  "argument_quality": <0-6>,
  "level": "<B1 / B2 / C1 / above C1>",
  "feedback": "<4–5 specific, constructive sentences referencing the rubric above>"
}""",
}


def transcribe_audio(audio_file_path):
    try:
        with open(audio_file_path, 'rb') as f:
            response = requests.post(
                'https://api.openai.com/v1/audio/transcriptions',
                headers={'Authorization': f'Bearer {settings.OPENAI_API_KEY}'},
                files={'file': (audio_file_path.split('/')[-1], f, 'audio/webm')},
                data={'model': 'whisper-1', 'language': 'en'},
                timeout=30
            )
        if response.status_code == 200:
            return response.json().get('text', '')
        logger.error(f"Whisper error: {response.status_code} {response.text}")
        return ''
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return ''


def score_response(transcription, question_text, part_number):
    if not transcription or not transcription.strip():
        return {
            'score': 0, 'grammar': 0, 'vocabulary': 0,
            'pronunciation': 0, 'fluency': 0,
            'feedback': 'No speech detected. The student did not provide a response.',
            'level': 'A1'
        }

    # For Full Test, part_number may be an int 1–8; map to rubric key
    part_str = str(part_number)
    if part_str not in SCORING_PROMPTS:
        # Full test: questions 1–3 → 1.1, 4–6 → 1.2, 7 → 2, 8 → 3
        try:
            n = int(part_str)
            if n <= 3:    part_str = '1.1'
            elif n <= 6:  part_str = '1.2'
            elif n == 7:  part_str = '2'
            else:         part_str = '3'
        except Exception:
            part_str = '1.1'

    system_prompt = SCORING_PROMPTS[part_str]
    user_message  = (
        f"Question asked: {question_text}\n\n"
        f"Student's spoken response (transcribed): {transcription}\n\n"
        f"Score this response strictly according to the rubric."
    )

    try:
        response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {settings.OPENAI_API_KEY}',
                'Content-Type': 'application/json'
            },
            json={
                'model': 'gpt-4o-mini',
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user',   'content': user_message}
                ],
                'max_tokens': 600,
                'temperature': 0.2,   # low temp = more consistent scoring
            },
            timeout=30
        )

        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content'].strip()
            # Strip any accidental markdown code fences
            if '```' in content:
                content = content.split('```')[1]
                if content.lower().startswith('json'):
                    content = content[4:]
            return json.loads(content)
        else:
            logger.error(f"GPT API error {response.status_code}: {response.text[:200]}")
            return {'score': None, 'feedback': 'AI scoring temporarily unavailable.', 'error': True}

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error in scoring: {e}")
        return {'score': None, 'feedback': 'Could not parse AI score response.', 'error': True}
    except Exception as e:
        logger.error(f"Scoring error: {e}")
        return {'score': None, 'feedback': 'AI scoring temporarily unavailable.', 'error': True}


def send_telegram_results(session):
    if not session.teacher or not session.teacher.telegram_id:
        logger.warning(f"No Telegram ID for teacher of session {session.id}")
        return False

    token    = settings.TELEGRAM_BOT_TOKEN
    chat_id  = session.teacher.telegram_id
    base_url = f'https://api.telegram.org/bot{token}'
    responses = session.responses.order_by('question_number')

    score_text = f"{session.total_score:.1f}" if session.total_score else "N/A"
    duration   = ''
    if session.completed_at and session.started_at:
        mins     = (session.completed_at - session.started_at).total_seconds() / 60
        duration = f" ({mins:.1f} min)"

    part_label = 'Full Test' if session.part == 'full' else f'Part {session.part}'
    max_score  = '6' if session.part == '3' else '5'

    # Build outsider candidate info line
    if session.session_type == 'outsider' and session.outsider_candidate_id:
        candidate_line = f"🪪 *Candidate ID:* {session.outsider_candidate_id}\n"
    else:
        candidate_line = ""

    message = (
        f"🎯 *CEFR Speaking Test Result*\n\n"
        f"👤 *Student:* {session.full_name}\n"
        f"{candidate_line}"
        f"📚 *Part:* {part_label}\n"
        f"⭐ *Total Score:* {score_text}\n"
        f"📅 *Date:* {session.started_at.strftime('%Y-%m-%d %H:%M')}{duration}\n"
        f"📊 *Type:* {session.get_session_type_display()}\n\n"
        f"*Question Scores:*"
    )

    for resp in responses:
        score_str = f"{resp.score:.1f}" if resp.score is not None else "N/A"
        message  += f"\n• Q{resp.question_number}: *{score_str}/{max_score}*"
        if resp.score_breakdown and resp.score_breakdown.get('level'):
            message += f" [{resp.score_breakdown['level']}]"
        if resp.feedback:
            short = resp.feedback[:120] + '…' if len(resp.feedback) > 120 else resp.feedback
            message += f"\n  _{short}_"

    try:
        requests.post(f'{base_url}/sendMessage', json={
            'chat_id': chat_id, 'text': message, 'parse_mode': 'Markdown'
        }, timeout=10)

        for resp in responses:
            if resp.audio_file:
                try:
                    with open(resp.audio_file.path, 'rb') as audio:
                        score_str = f"{resp.score:.1f}" if resp.score is not None else "N/A"
                        caption   = (
                            f"🎤 Q{resp.question_number} — {session.full_name}\n"
                            f"Score: {score_str}/{max_score}"
                            + (f" [{resp.score_breakdown.get('level','')}]" if resp.score_breakdown else '')
                            + f"\n📝 {resp.transcription[:200] if resp.transcription else 'No transcript'}"
                        )
                        requests.post(
                            f'{base_url}/sendAudio',
                            data={'chat_id': chat_id, 'caption': caption},
                            files={'audio': audio},
                            timeout=30
                        )
                except Exception as e:
                    logger.error(f"Audio send error Q{resp.question_number}: {e}")

        session.telegram_sent = True
        session.save(update_fields=['telegram_sent'])
        return True

    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False


# ── Raw score → Rating score conversion (from official table) ────────────────
# Xom ballar → Reyting ballari  (multilevel format)
RAW_TO_RATING = {
    21: 75, 20.5: 73, 20: 71, 19.5: 69, 19: 67, 18.5: 65, 18: 64,
    17.5: 63, 17: 61, 16.5: 59, 16: 57, 15.5: 56, 15: 54, 14.5: 52,
    14: 51, 13.5: 50, 13: 49, 12.5: 47, 12: 46, 11.5: 45, 11: 43,
    10.5: 42, 10: 40, 9.5: 39, 9: 38, 8.5: 37, 8: 35, 7.5: 33,
    7: 32, 6.5: 30, 6: 29, 5.5: 27, 5: 26, 4.5: 24, 4: 23,
    3.5: 21, 3: 19, 2.5: 17, 2: 15, 1.5: 13, 1: 11, 0.5: 10, 0: 0,
}

def raw_to_rating(raw_score):
    """Convert raw speaking score to official rating score."""
    if raw_score is None:
        return None
    # Round to nearest 0.5
    rounded = round(raw_score * 2) / 2
    return RAW_TO_RATING.get(rounded, None)
