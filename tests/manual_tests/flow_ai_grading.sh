#!/usr/bin/env bash
# =============================================================================
# Флоу: AI-оценка домашнего задания (полный цикл)
#
# Сценарий:
#   1.  Препод создаёт виджет
#   2.  Препод создаёт задание типа "homework" с rubric-подсказкой
#   3.  Препод задаёт prompt, эталонный ответ и критерии оценки
#   4.  Студент сдаёт домашку текстом
#   5.  Сдача получает статус pending_ai — задача уходит в ARQ-очередь
#   6.  Ждём, пока воркер вызовет Gemini и сменит статус на pending_teacher
#       (polling каждые 2 с, таймаут 60 с)
#   7.  Препод видит сдачу вместе с AI-оценкой и rubric_breakdown
#   8a. Препод принимает AI-оценку (accept_ai=true) → статус graded
#   8b. Альтернатива: препод переопределяет оценку (accept_ai=false)
#   9.  Студент видит финальный результат (grading.ai скрыт)
#
# Требования:
#   - API запущен на localhost:8000
#   - ARQ-воркер запущен (docker compose up worker)
#   - GEMINI_API_KEY задан в .env воркера
#   - MinIO доступен (файлы в этом флоу не используются)
#
# Запуск: bash flow_ai_grading.sh
# =============================================================================

set -euo pipefail

BASE="http://localhost:8000/api/v1"

# Заголовки препода (widget 3, board 30)
T='-H "x-user-id: 1" -H "x-user-role: teacher" -H "x-board-id: 30" -H "x-widget-id: 3"'
# Заголовки студента
S='-H "x-user-id: 2" -H "x-user-role: student" -H "x-board-id: 30" -H "x-widget-id: 3"'

echo "========================================"
echo " Флоу: AI-оценка домашнего задания"
echo "========================================"

# --------------------------------------------------------------------------
# 1. Создать виджет
# --------------------------------------------------------------------------
echo -e "\n[1] Создаём виджет (teacher, board 30)"
curl -s -X POST "$BASE/widgets" \
  -H "x-user-id: 1" -H "x-user-role: teacher" \
  -H "x-board-id: 30" -H "x-widget-id: 3" \
  -H "Content-Type: application/json" \
  -d '{"id": 3, "board_id": 30}' | jq .

# --------------------------------------------------------------------------
# 2. Создать задание типа "homework"
# --------------------------------------------------------------------------
echo -e "\n[2] Создаём задание (homework, max_score=10)"
ASSIGNMENT=$(curl -s -X POST "$BASE/widgets/3/assignments" \
  -H "x-user-id: 1" -H "x-user-role: teacher" \
  -H "x-board-id: 30" -H "x-widget-id: 3" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "homework",
    "title": "Объясните рекурсию",
    "description": "Развёрнутый ответ на тему рекурсии в программировании",
    "max_score": 10,
    "final_score_strategy": "last"
  }')
echo "$ASSIGNMENT" | jq .
ASSIGNMENT_ID=$(echo "$ASSIGNMENT" | jq -r '.assignment.id')
echo ">>> assignment_id = $ASSIGNMENT_ID"

# --------------------------------------------------------------------------
# 3. Задать детали домашки: prompt + эталон + критерии
# --------------------------------------------------------------------------
echo -e "\n[3] Задаём prompt и критерии оценки"
curl -s -X PUT "$BASE/assignments/$ASSIGNMENT_ID/homework" \
  -H "x-user-id: 1" -H "x-user-role: teacher" \
  -H "x-board-id: 30" -H "x-widget-id: 3" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Объясните понятие рекурсии в программировании. Приведите пример рекурсивной функции и опишите базовый случай.",
    "reference_answer": "Рекурсия — вызов функцией самой себя. Базовый случай останавливает рекурсию. Пример: факториал n! = n * (n-1)! при n>1, и 1! = 1 (базовый случай).",
    "grading_criteria": "Точность определения (3 б), наличие примера (4 б), описание базового случая (3 б)",
    "accepted_formats": ["text", "markdown"]
  }' | jq .

# --------------------------------------------------------------------------
# 4. Студент сдаёт домашку текстом
# --------------------------------------------------------------------------
echo -e "\n[4] Студент сдаёт домашку"
SUBMISSION=$(curl -s -X POST "$BASE/assignments/$ASSIGNMENT_ID/submissions" \
  -H "x-user-id: 2" -H "x-user-role: student" \
  -H "x-board-id: 30" -H "x-widget-id: 3" \
  -F "text=Рекурсия — это когда функция вызывает сама себя. Важно иметь базовый случай, иначе будет бесконечный цикл. Например, вычисление факториала: def factorial(n): return 1 if n <= 1 else n * factorial(n-1). Здесь n<=1 — базовый случай.")
echo "$SUBMISSION" | jq '{id, status, attempt_number}'
SUBMISSION_ID=$(echo "$SUBMISSION" | jq -r '.id')
echo ">>> submission_id = $SUBMISSION_ID"

# --------------------------------------------------------------------------
# 5. Проверяем начальный статус — должен быть pending_ai
# --------------------------------------------------------------------------
echo -e "\n[5] Начальный статус сдачи"
curl -s "$BASE/submissions/$SUBMISSION_ID" \
  -H "x-user-id: 2" -H "x-user-role: student" \
  -H "x-board-id: 30" -H "x-widget-id: 3" | jq '{status, "ai_grading": .grading.ai}'

# --------------------------------------------------------------------------
# 6. Ждём, пока воркер обработает задачу (pending_ai → pending_teacher)
#    Polling каждые 2 секунды, максимум 60 секунд
# --------------------------------------------------------------------------
echo -e "\n[6] Ждём AI-оценки (polling статуса, таймаут 60 с)..."
TIMEOUT=60
ELAPSED=0
STATUS="pending_ai"

while [ "$STATUS" = "pending_ai" ] && [ "$ELAPSED" -lt "$TIMEOUT" ]; do
  sleep 2
  ELAPSED=$((ELAPSED + 2))
  STATUS=$(curl -s "$BASE/submissions/$SUBMISSION_ID" \
    -H "x-user-id: 1" -H "x-user-role: teacher" \
    -H "x-board-id: 30" -H "x-widget-id: 3" | jq -r '.status')
  echo "  [${ELAPSED}s] статус: $STATUS"
done

if [ "$STATUS" = "pending_ai" ]; then
  echo "  ТАЙМАУТ: воркер не ответил за ${TIMEOUT}с."
  echo "  Проверьте: docker compose logs worker | tail -20"
  exit 1
fi

echo "  ✓ AI обработал сдачу, статус: $STATUS"

# --------------------------------------------------------------------------
# 7. Препод видит AI-оценку + rubric_breakdown
# --------------------------------------------------------------------------
echo -e "\n[7] Препод смотрит сдачу с AI-результатами"
curl -s "$BASE/submissions/$SUBMISSION_ID" \
  -H "x-user-id: 1" -H "x-user-role: teacher" \
  -H "x-board-id: 30" -H "x-widget-id: 3" | jq '{
    status,
    ai_score: .grading.ai.score,
    ai_feedback: .grading.ai.feedback,
    rubric: .grading.ai.rubric_breakdown
  }'

echo -e "\n--- Студент в этот момент видит только статус (без AI-оценки) ---"
curl -s "$BASE/submissions/$SUBMISSION_ID" \
  -H "x-user-id: 2" -H "x-user-role: student" \
  -H "x-board-id: 30" -H "x-widget-id: 3" | jq '{status, "ai_visible_to_student": .grading.ai, effective_score}'

# --------------------------------------------------------------------------
# 8a. Препод принимает AI-оценку (accept_ai=true)
# --------------------------------------------------------------------------
echo -e "\n[8a] Препод принимает оценку AI (accept_ai=true)"
curl -s -X PATCH "$BASE/submissions/$SUBMISSION_ID/grade" \
  -H "x-user-id: 1" -H "x-user-role: teacher" \
  -H "x-board-id: 30" -H "x-widget-id: 3" \
  -H "Content-Type: application/json" \
  -d '{
    "accept_ai": true
  }' | jq '{status, "final_score": .grading.final.score, "feedback": .grading.final.feedback, "accepted_ai": .grading.final.accepted_ai}'

# --------------------------------------------------------------------------
# 8b. Альтернатива: препод переопределяет оценку (раскомментируйте, если нужно)
#     Предполагает новую сдачу — submission_id должен отличаться
# --------------------------------------------------------------------------
# echo -e "\n[8b] Альтернатива: препод переопределяет оценку"
# curl -s -X PATCH "$BASE/submissions/$SUBMISSION_ID/grade" \
#   -H "x-user-id: 1" -H "x-user-role: teacher" \
#   -H "x-board-id: 30" -H "x-widget-id: 3" \
#   -H "Content-Type: application/json" \
#   -d '{
#     "score": 7,
#     "feedback": "Определение верное, пример хороший, но базовый случай описан поверхностно.",
#     "accept_ai": false
#   }' | jq '{status, "final_score": .grading.final.score, "feedback": .grading.final.feedback, "accepted_ai": .grading.final.accepted_ai}'

# --------------------------------------------------------------------------
# 9. Студент видит финальный результат (grading.ai по-прежнему не видит)
# --------------------------------------------------------------------------
echo -e "\n[9] Студент смотрит финальный результат"
curl -s "$BASE/submissions/$SUBMISSION_ID" \
  -H "x-user-id: 2" -H "x-user-role: student" \
  -H "x-board-id: 30" -H "x-widget-id: 3" | jq '{
    status,
    effective_score,
    "final_score": .grading.final.score,
    "feedback": .grading.final.feedback,
    "ai_hidden": (.grading.ai == null)
  }'

echo -e "\n========================================"
echo " Готово!"
echo "========================================"
