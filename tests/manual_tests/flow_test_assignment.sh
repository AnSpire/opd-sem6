#!/usr/bin/env bash
# =============================================================================
# Флоу: Тест с автопроверкой
#
# Сценарий:
#   1. Препод создаёт виджет на доске
#   2. Препод создаёт задание типа "test"
#   3. Препод добавляет вопрос с вариантами ответа
#   4. Студент сдаёт тест (один правильный ответ, один неправильный)
#   5. Препод смотрит все сдачи
#   6. Студент смотрит свой результат
#
# Запуск: bash flow_test_assignment.sh
# Требования: API запущен на localhost:8000
# =============================================================================

set -euo pipefail

BASE="http://localhost:8000/api/v1"

# Заголовки препода (user_id=1, board_id=10)
T_HDR='-H "x-user-id: 1" -H "x-user-role: teacher" -H "x-board-id: 10" -H "x-widget-id: 1"'
# Заголовки студента (user_id=2, board_id=10)
S_HDR='-H "x-user-id: 2" -H "x-user-role: student" -H "x-board-id: 10" -H "x-widget-id: 1"'

echo "========================================"
echo " Флоу: тест с автопроверкой"
echo "========================================"

# --------------------------------------------------------------------------
# 1. Создать виджет (идемпотентно — можно вызывать повторно)
# --------------------------------------------------------------------------
echo -e "\n[1] Создаём виджет (teacher, board 10)"
curl -s -X POST "$BASE/widgets" \
  -H "x-user-id: 1" -H "x-user-role: teacher" \
  -H "x-board-id: 10" -H "x-widget-id: 1" \
  -H "Content-Type: application/json" \
  -d '{"id": 1, "board_id": 10}' | jq .

# --------------------------------------------------------------------------
# 2. Создать задание типа "test"
# --------------------------------------------------------------------------
echo -e "\n[2] Создаём задание типа test"
ASSIGNMENT=$(curl -s -X POST "$BASE/widgets/1/assignments" \
  -H "x-user-id: 1" -H "x-user-role: teacher" \
  -H "x-board-id: 10" -H "x-widget-id: 1" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "test",
    "title": "Тест по Python",
    "description": "Базовые вопросы по синтаксису Python",
    "max_score": 10,
    "max_attempts": 3,
    "final_score_strategy": "best"
  }')
echo "$ASSIGNMENT" | jq .
ASSIGNMENT_ID=$(echo "$ASSIGNMENT" | jq -r '.assignment.id')
echo ">>> assignment_id = $ASSIGNMENT_ID"

# --------------------------------------------------------------------------
# 3. Добавить вопрос с вариантами ответа (тип single)
# --------------------------------------------------------------------------
echo -e "\n[3] Добавляем вопрос (single-choice, 5 баллов)"
QUESTION=$(curl -s -X POST "$BASE/assignments/$ASSIGNMENT_ID/questions" \
  -H "x-user-id: 1" -H "x-user-role: teacher" \
  -H "x-board-id: 10" -H "x-widget-id: 1" \
  -H "Content-Type: application/json" \
  -d '{
    "order": 1,
    "text": "Что выведет print(type(1 / 2))?",
    "type": "single",
    "options": ["<class \"int\">", "<class \"float\">", "<class \"str\">"],
    "correct_answer": ["<class \"float\">"],
    "points": 5
  }')
echo "$QUESTION" | jq .
QUESTION_ID=$(echo "$QUESTION" | jq -r '.id')
echo ">>> question_id = $QUESTION_ID"

# --------------------------------------------------------------------------
# 4a. Студент сдаёт тест с ПРАВИЛЬНЫМ ответом
# --------------------------------------------------------------------------
echo -e "\n[4a] Студент сдаёт тест — правильный ответ"
curl -s -X POST "$BASE/assignments/$ASSIGNMENT_ID/submissions" \
  -H "x-user-id: 2" -H "x-user-role: student" \
  -H "x-board-id: 10" -H "x-widget-id: 1" \
  -H "Content-Type: application/json" \
  -d "{\"answers\": [{\"question_id\": $QUESTION_ID, \"answer\": \"<class \\\"float\\\">\"}]}" | jq '{
    status, attempt_number, effective_score,
    is_correct: .payload.answers[0].is_correct,
    points_awarded: .payload.answers[0].points_awarded
  }'

# --------------------------------------------------------------------------
# 4b. Студент сдаёт тест с НЕПРАВИЛЬНЫМ ответом (попытка 2)
# --------------------------------------------------------------------------
echo -e "\n[4b] Студент сдаёт тест — неправильный ответ (попытка 2)"
curl -s -X POST "$BASE/assignments/$ASSIGNMENT_ID/submissions" \
  -H "x-user-id: 2" -H "x-user-role: student" \
  -H "x-board-id: 10" -H "x-widget-id: 1" \
  -H "Content-Type: application/json" \
  -d "{\"answers\": [{\"question_id\": $QUESTION_ID, \"answer\": \"<class \\\"int\\\">\"}]}" | jq '{
    status, attempt_number, effective_score,
    is_correct: .payload.answers[0].is_correct,
    points_awarded: .payload.answers[0].points_awarded
  }'

# --------------------------------------------------------------------------
# 5. Препод смотрит все сдачи (видит обе попытки студента)
# --------------------------------------------------------------------------
echo -e "\n[5] Препод просматривает все сдачи по заданию"
curl -s "$BASE/assignments/$ASSIGNMENT_ID/submissions" \
  -H "x-user-id: 1" -H "x-user-role: teacher" \
  -H "x-board-id: 10" -H "x-widget-id: 1" | jq '[.[] | {attempt_number, status, effective_score}]'

# --------------------------------------------------------------------------
# 6. Студент смотрит свои сдачи (стратегия best → показывает лучший результат)
# --------------------------------------------------------------------------
echo -e "\n[6] Студент смотрит свои сдачи (effective_score = best из попыток)"
curl -s "$BASE/assignments/$ASSIGNMENT_ID/submissions" \
  -H "x-user-id: 2" -H "x-user-role: student" \
  -H "x-board-id: 10" -H "x-widget-id: 1" | jq '[.[] | {attempt_number, status, effective_score}]'

echo -e "\n========================================"
echo " Готово!"
echo "========================================"
