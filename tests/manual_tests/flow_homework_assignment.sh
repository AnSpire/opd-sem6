#!/usr/bin/env bash
# =============================================================================
# Флоу: Домашнее задание с развёрнутым ответом
#
# Сценарий:
#   1. Препод создаёт виджет на доске
#   2. Препод создаёт задание типа "homework"
#   3. Препод задаёт prompt, критерии и разрешённые форматы
#   4. Студент сдаёт домашку текстом + PDF-файлом
#   5. Сдача уходит в статус pending_ai (ждёт AI-проверки)
#   6. Студент получает ссылку на свой файл (presigned URL)
#   7. Препод смотрит сдачу и выставляет финальную оценку вручную
#      (в MVP AI не запущен, поэтому сразу PATCH /grade с accept_ai=false)
#   8. Студент видит финальный результат
#
# Запуск: bash flow_homework_assignment.sh
# Требования: API запущен на localhost:8000, MinIO доступен
# =============================================================================

set -euo pipefail

BASE="http://localhost:8000/api/v1"

echo "========================================"
echo " Флоу: домашнее задание с файлами"
echo "========================================"

# --------------------------------------------------------------------------
# 1. Создать виджет
# --------------------------------------------------------------------------
echo -e "\n[1] Создаём виджет (teacher, board 20)"
curl -s -X POST "$BASE/widgets" \
  -H "x-user-id: 1" -H "x-user-role: teacher" \
  -H "x-board-id: 20" -H "x-widget-id: 2" \
  -H "Content-Type: application/json" \
  -d '{"id": 2, "board_id": 20}' | jq .

# --------------------------------------------------------------------------
# 2. Создать задание типа "homework" с дедлайном через 7 дней
# --------------------------------------------------------------------------
echo -e "\n[2] Создаём задание типа homework"
DEADLINE=$(date -u -d "+7 days" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null \
           || date -u -v+7d +"%Y-%m-%dT%H:%M:%SZ")  # GNU / BSD date
ASSIGNMENT=$(curl -s -X POST "$BASE/widgets/2/assignments" \
  -H "x-user-id: 1" -H "x-user-role: teacher" \
  -H "x-board-id: 20" -H "x-widget-id: 2" \
  -H "Content-Type: application/json" \
  -d "{
    \"type\": \"homework\",
    \"title\": \"Эссе: алгоритмы сортировки\",
    \"description\": \"Объясните принцип работы merge sort\",
    \"max_score\": 20,
    \"max_attempts\": 2,
    \"allow_late_submissions\": false,
    \"final_score_strategy\": \"last\",
    \"deadline\": \"$DEADLINE\"
  }")
echo "$ASSIGNMENT" | jq .
ASSIGNMENT_ID=$(echo "$ASSIGNMENT" | jq -r '.assignment.id')
echo ">>> assignment_id = $ASSIGNMENT_ID"

# --------------------------------------------------------------------------
# 3. Задать детали домашки: prompt, критерии, разрешённые форматы
# --------------------------------------------------------------------------
echo -e "\n[3] Задаём детали домашки (prompt, критерии, форматы)"
curl -s -X PUT "$BASE/assignments/$ASSIGNMENT_ID/homework" \
  -H "x-user-id: 1" -H "x-user-role: teacher" \
  -H "x-board-id: 20" -H "x-widget-id: 2" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Объясните принцип работы алгоритма merge sort. Опишите сложность по времени и памяти.",
    "reference_answer": "Merge sort делит массив пополам рекурсивно, затем сливает отсортированные части. O(n log n) по времени, O(n) по памяти.",
    "grading_criteria": "Правильность описания алгоритма (10 б), анализ сложности (5 б), примеры (5 б)",
    "accepted_formats": ["text", "markdown", "pdf"]
  }' | jq .

# --------------------------------------------------------------------------
# 4. Студент сдаёт домашку: текст + PDF-файл (multipart)
# --------------------------------------------------------------------------
echo -e "\n[4] Студент сдаёт домашку с текстом и PDF"

# Создаём минимальный PDF-файл для демонстрации
TMPFILE=$(mktemp /tmp/homework_XXXXX.pdf)
printf '%s' '%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj
xref
0 4
0000000000 65535 f
trailer<</Size 4/Root 1 0 R>>
startxref
%%EOF' > "$TMPFILE"

SUBMISSION=$(curl -s -X POST "$BASE/assignments/$ASSIGNMENT_ID/submissions" \
  -H "x-user-id: 2" -H "x-user-role: student" \
  -H "x-board-id: 20" -H "x-widget-id: 2" \
  -F "text=Merge sort — алгоритм «разделяй и властвуй». Делит массив пополам, рекурсивно сортирует каждую половину и сливает результаты." \
  -F "files=@$TMPFILE;type=application/pdf")
rm -f "$TMPFILE"

echo "$SUBMISSION" | jq '{id, status, attempt_number, is_late, payload_text: .payload.text, attachments: .payload.attachments}'
SUBMISSION_ID=$(echo "$SUBMISSION" | jq -r '.id')
echo ">>> submission_id = $SUBMISSION_ID"

# --------------------------------------------------------------------------
# 5. Проверяем статус — должен быть pending_ai (AI ещё не оценил)
# --------------------------------------------------------------------------
echo -e "\n[5] Статус сдачи — ожидаем pending_ai"
curl -s "$BASE/submissions/$SUBMISSION_ID" \
  -H "x-user-id: 2" -H "x-user-role: student" \
  -H "x-board-id: 20" -H "x-widget-id: 2" | jq '{status, effective_score}'

# --------------------------------------------------------------------------
# 6. Студент запрашивает presigned URL для своего PDF (вложение 0)
# --------------------------------------------------------------------------
echo -e "\n[6] Студент получает ссылку на свой PDF (presigned URL, TTL 5 мин)"
curl -s "$BASE/attachments/$SUBMISSION_ID/0" \
  -H "x-user-id: 2" -H "x-user-role: student" \
  -H "x-board-id: 20" -H "x-widget-id: 2" | jq .

# --------------------------------------------------------------------------
# 7. Препод смотрит все сдачи по заданию
# --------------------------------------------------------------------------
echo -e "\n[7] Препод просматривает сдачи по заданию"
curl -s "$BASE/assignments/$ASSIGNMENT_ID/submissions" \
  -H "x-user-id: 1" -H "x-user-role: teacher" \
  -H "x-board-id: 20" -H "x-widget-id: 2" | jq '[.[] | {id, student_user_id, status, ai: .grading.ai}]'

# --------------------------------------------------------------------------
# 8. Препод выставляет финальную оценку вручную (accept_ai=false)
#    (в реальном флоу — после того как AI выставил оценку и статус pending_teacher)
# --------------------------------------------------------------------------
echo -e "\n[8] Препод выставляет финальную оценку: 16/20"
curl -s -X PATCH "$BASE/submissions/$SUBMISSION_ID/grade" \
  -H "x-user-id: 1" -H "x-user-role: teacher" \
  -H "x-board-id: 20" -H "x-widget-id: 2" \
  -H "Content-Type: application/json" \
  -d '{
    "score": 16,
    "feedback": "Хорошее объяснение алгоритма. Сложность описана верно, но не хватает псевдокода или примера на конкретных числах.",
    "accept_ai": false
  }' | jq '{status, "final_score": .grading.final.score, "feedback": .grading.final.feedback}' \
  || echo "(PATCH /grade будет реализован в Этапе 6)"

# --------------------------------------------------------------------------
# 9. Студент смотрит финальный результат
# --------------------------------------------------------------------------
echo -e "\n[9] Студент смотрит свой результат после проверки"
curl -s "$BASE/submissions/$SUBMISSION_ID" \
  -H "x-user-id: 2" -H "x-user-role: student" \
  -H "x-board-id: 20" -H "x-widget-id: 2" | jq '{status, effective_score, "final": .grading.final}'

echo -e "\n========================================"
echo " Готово!"
echo "========================================"
