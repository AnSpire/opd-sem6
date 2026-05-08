from app.models.question import Question, QuestionType, ShortTextMatch


def grade_answers(
    questions: list[Question],
    raw_answers: list[dict],
) -> tuple[list[dict], int]:
    """
    Returns (graded_answers, total_score).
    graded_answers: [{question_id, answer, is_correct, points_awarded}]
    """
    by_id = {q.id: q for q in questions}
    graded: list[dict] = []
    total = 0

    for item in raw_answers:
        qid = item["question_id"]
        answer = item["answer"]
        question = by_id.get(qid)
        if question is None:
            graded.append({"question_id": qid, "answer": answer, "is_correct": False, "points_awarded": 0})
            continue

        correct = question.correct_answer
        is_correct = _check(question, answer, correct)
        points = question.points if is_correct else 0
        total += points
        graded.append({"question_id": qid, "answer": answer, "is_correct": is_correct, "points_awarded": points})

    return graded, total


def _check(question: Question, answer, correct) -> bool:
    match question.type:
        case QuestionType.single:
            expected = correct[0] if isinstance(correct, list) else correct
            return answer == expected
        case QuestionType.multi:
            return set(answer) == set(correct) if isinstance(answer, list) else False
        case QuestionType.bool:
            return bool(answer) == bool(correct)
        case QuestionType.short_text:
            a, c = str(answer), str(correct)
            if question.short_text_match == ShortTextMatch.case_insensitive:
                return a.lower() == c.lower()
            return a == c
    return False
