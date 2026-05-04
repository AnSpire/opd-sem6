Принял. Переписываю ТЗ целиком с учётом entry-point модели, Mongo для submissions и твоих уточнений.

---

# ТЗ. Backend ed-tech модуля для виджет-системы (v2)

## 1. Назначение

Backend для npm-виджета `homework-widget`, встраиваемого в доски сервиса. Виджет — это **entry-point** в отдельное веб-приложение (SPA), внутри которого живут все задания преподавателя для конкретной доски и все ответы учеников этой доски.

Поддерживаются два типа заданий:
- **Тесты** — с автопроверкой по эталонным ответам.
- **Домашки с развёрнутым ответом** — текст / markdown / картинки / pdf, предварительно оцениваются LLM, финальную оценку утверждает преподаватель.

**Скоуп заданий**: связка `(creator_user_id, board_id)`, физически выражается через `widget_id`. Один преподаватель = один виджет на доске = один пул заданий. Все ученики этой доски видят все задания этого виджета (точечных назначений в MVP нет).

## 2. Стек

- Python 3.12, FastAPI, Pydantic v2
- PostgreSQL 16 — конфигурация (виджеты, задания, вопросы, токены)
- MongoDB 7 — активность (сабмишены, AI-логи, снапшоты конфигов)
- Redis 7 — очередь задач + кэш
- SQLAlchemy 2.0 async, Alembic — для PG
- Motor (async PyMongo) — для Mongo
- ARQ — воркер на Redis (AI-оценка, отправка метрик, рассылка `widget:updated`-снапшотов)
- httpx async — для прокси-модуля и Gemini API
- google-genai SDK — Gemini 2.5 Flash через прокси
- MinIO — S3-совместимое хранилище файлов
- Docker + docker-compose — сервисы: api, worker, postgres, mongo, redis, minio
- pytest + pytest-asyncio + httpx AsyncClient — тесты

## 3. Внешние интеграции

**Прокси-модуль.** Все исходящие HTTP-запросы (StatService, Gemini API) идут через локальный прокси по схеме `ProxyOptions`. Адрес — из переменной окружения. Реализуем тонкий клиент-обёртку.

**Контекст пользователя.** **источник правды для контекста виджета** = `WidgetInfo`, который фронт присылает через `setInfo`. Авторизацию по конкретному запросу делаем доверием к фронту.

**StatService.** Регистрация модуля при старте, периодическая отправка метрик. Учитываем rate-limit 12/час.

**Gemini 2.5 Flash.** Для оценки развёрнутых ответов через прокси. Structured output (JSON schema). Multimodal (картинки + pdf).

## 4. Роли

- `teacher` — управляет виджетом, создаёт задания, проверяет и утверждает оценки.
- `student` — видит задания виджета, отправляет ответы, видит только свою финальную оценку (AI-оценку не видит).

## 5. Модели данных

### 5.1 PostgreSQL

**`widgets`** — entry-point на доске, минимум полей.
- `id` (PK, приходит с фронта)
- `board_id`
- `creator_user_id`
- `created_at`, `updated_at`
- Уникальный индекс: `(board_id, creator_user_id)` — гарантия «один препод = один виджет на доске».

**`assignments`** — задания, главная сущность.
- `id` (PK, serial)
- `widget_id` (FK → widgets.id, ON DELETE CASCADE)
- `creator_user_id` — дублируем для удобства фильтров и аудита
- `type` — `homework` | `test`
- `title`, `description`
- `deadline` (timestamptz, nullable)
- `allow_late_submissions` (bool, default false)
- `max_attempts` (int, nullable; null = неограниченно)
- `final_score_strategy` — `last` | `best` | `average` (default `best`)
- `max_score` (int)
- `created_at`, `updated_at`
- Индексы: `(widget_id, created_at desc)` — для превью «последние 3 задания» и списков.

**`questions`** — для тестов.
- `id`, `assignment_id` (FK, cascade)
- `order`, `text`
- `type` — `single` | `multi` | `bool` | `short_text`
- `options` (jsonb, nullable)
- `correct_answer` (jsonb)
- `points` (int)
- `short_text_match` — `exact` | `case_insensitive`

**`homework_details`** — для домашек, 1:1 с assignment.
- `assignment_id` (PK, FK, cascade)
- `prompt` (text)
- `reference_answer` (text, nullable)
- `grading_criteria` (text, nullable)
- `accepted_formats` — массив из `text` | `markdown` | `image` | `pdf`

**`stats_module`** — данные регистрации в StatService (одна строка).
- `module_id`, `module_name`, `token`, `token_expired`, `is_enabled`, `created_at`, `updated_at`

### 5.2 MongoDB

**`submissions`** — попытка ученика, единый документ.

```json
{
  "_id": ObjectId,
  "assignment_id": 42,
  "widget_id": 7,
  "board_id": 12,
  "student_user_id": 100,
  "type": "homework" | "test",
  "attempt_number": 1,
  "submitted_at": ISODate,
  "is_late": false,
  "status": "pending_ai" | "pending_teacher" | "auto_graded" | "graded",

  "payload": {
    // type=test:
    "answers": [
      {"question_id": 1, "answer": [...], "is_correct": true, "points_awarded": 5}
    ]
    // type=homework:
    // "text": "...", "markdown": "...",
    // "attachments": [
    //   {"kind": "image"|"pdf", "s3_key": "...", "filename": "...", "mime": "...", "size": 12345}
    // ]
  },

  "grading": {
    "ai": {
      "score": 7,
      "max_score": 10,
      "feedback": "...",
      "rubric_breakdown": [...],
      "graded_at": ISODate,
      "log_id": ObjectId
    } | null,
    "final": {
      "score": 8,
      "feedback": "...",
      "teacher_user_id": 5,
      "graded_at": ISODate,
      "accepted_ai": false
    } | null
  }
}
```

Индексы:
- Уникальный: `{assignment_id: 1, student_user_id: 1, attempt_number: 1}`
- `{assignment_id: 1, status: 1}` — для списков на проверку
- `{student_user_id: 1, submitted_at: -1}` — для «мои сдачи»
- `{widget_id: 1, submitted_at: -1}` — для агрегатов виджета

**`ai_logs`** — каждый вызов Gemini.

```json
{
  "_id": ObjectId,
  "submission_id": ObjectId,
  "assignment_id": 42,
  "widget_id": 7,
  "request": {"prompt": "...", "model": "...", "schema": {...}},
  "response": {"raw": "...", "parsed": {...}, "tokens_in": 0, "tokens_out": 0},
  "latency_ms": 1200,
  "status": "ok" | "parse_error" | "timeout" | "api_error",
  "error": null,
  "created_at": ISODate
}
```

**`widget_config_snapshots`** — то, что отправляется фронту в `widget:updated`.

```json
{
  "_id": ObjectId,
  "widget_id": 7,
  "version": 12,
  "config": {
    "assignmentsCount": 5,
    "preview": [
      {"id": 42, "title": "...", "type": "homework", "deadline": ..., "createdAt": ...},
      ...  // последние 3
    ]
  },
  "reason": "assignment_created" | "assignment_updated" | "assignment_deleted" | "widget_created",
  "emitted_at": ISODate
}
```

## 6. Функциональные требования

### 6.1 Управление виджетом
- При первом обращении к виджету (или явном создании от фронта) — апсерт записи в `widgets`. Защита от дублей по `(board_id, creator_user_id)`.
- `setInfo` от фронта обновляет контекст виджета.
- Удаление виджета (фронт зовёт `DELETE`) — каскадно сносит все assignments, questions, homework_details. Сабмишены в Mongo помечаются `widget_deleted_at` и остаются (для будущей аналитики); файлы в MinIO удаляются. AI-логи остаются.

### 6.2 События `widget:updated`
- Триггеры: создание виджета, создание/обновление/удаление задания.
- Сервис собирает свежий `config` (count + последние 3 задания), пишет снапшот в Mongo, возвращает `config` в HTTP-ответе соответствующего эндпоинта. Фронт сам диспатчит CustomEvent.
- Бамп `version` — монотонный счётчик на виджет (через FindOneAndUpdate с `$inc`).

### 6.3 Управление заданиями
- CRUD заданий внутри виджета. Только `teacher`, и только владелец виджета.
- Параметры (deadline, allow_late, max_attempts, final_score_strategy) задаются на каждое задание.
- Удаление задания — каскад: questions, homework_details, файлы сабмишенов в MinIO. Сабмишены в Mongo помечаются `assignment_deleted_at`.

### 6.4 Тесты
- CRUD вопросов внутри задания (только `teacher`).
- Типы: `single`, `multi`, `bool`, `short_text`.
- Сабмишн ученика → авто-проверка → `final_score`, `status = auto_graded` сразу. Без AI и учителя.

### 6.5 Домашки с развёрнутым ответом
- Препод задаёт `prompt`, опц. `reference_answer`, опц. `grading_criteria`, выбирает `accepted_formats`.
- Ученик отправляет: `text` или `markdown` + до 5 файлов (картинки / pdf), каждый ≤ 10 МБ.
- Сабмишн → `pending_ai` → задача в ARQ → AI-оценка → `pending_teacher` → препод утверждает → `graded`.
- Препод видит AI-оценку и комментарий. Может: «согласиться» (final копирует AI) либо переписать score+feedback.
- Ученик до утверждения видит только статус «на проверке». После — финальную оценку и комментарий учителя. AI-оценка ученику недоступна.

### 6.6 Дедлайны и опоздания
- При сабмишне сравниваем с `assignment.deadline`. Позже + `allow_late=true` → принимаем, `is_late=true`. Позже + `allow_late=false` → 409.
- Снятие баллов за опоздание в MVP не реализуем.

### 6.7 Пересдачи
- Каждая попытка — отдельный документ с инкрементом `attempt_number`. До отправки проверяем лимит (`max_attempts`).
- `final_score_strategy` определяет показанный итоговый балл — рассчитывается на лету при отдаче.

### 6.8 Метрики в StatService
- При старте api — проверка `stats_module`. Если пусто — `POST /api/stats/module/create`, сохранение токена.
- Периодическая ARQ-задача (каждые N минут): по каждому активному виджету — `{widgetId, assignmentsCount, submissionsCount, gradedCount, averageScore, lastActivityAt}` → `PUT /api/stats/module/metrics` (через прокси).
- Обработка: 401 → лог + перерегистрация; 429 → уважаем `Retry-After`; 404 → пропускаем.

## 7. REST API

Префикс `/api/v1`. Роли и контекст — из `WidgetInfo` / заголовков (см. п. 3).

**Виджеты**
- `POST /widgets` — создать или вернуть существующий. Идемпотентно по `(board_id, creator_user_id)`. Тело: `{id, board_id}`.
- `POST /widgets/{id}/info` — `setInfo`-эндпоинт, обновляет контекст.
- `GET /widgets/{id}` — meta + текущий `config`.
- `DELETE /widgets/{id}` — удаление с каскадом.

**Задания**
- `POST /widgets/{id}/assignments` (teacher) — создать. Возвращает обновлённый `config`.
- `GET /widgets/{id}/assignments` — список. Для student — без `correct_answer` в вопросах.
- `GET /assignments/{id}` — детали.
- `PATCH /assignments/{id}` (teacher) — изменить. Возвращает обновлённый `config`.
- `DELETE /assignments/{id}` (teacher) — удалить. Возвращает обновлённый `config`.

**Вопросы (для тестов)**
- `POST /assignments/{id}/questions` (teacher)
- `GET /assignments/{id}/questions`
- `PATCH /questions/{id}` (teacher)
- `DELETE /questions/{id}` (teacher)

**Домашки**
- `PUT /assignments/{id}/homework` (teacher) — set/update.
- `GET /assignments/{id}/homework`

**Сабмишены**
- `POST /assignments/{id}/submissions` (student) — multipart/form-data.
- `GET /assignments/{id}/submissions` — teacher все, student только свои.
- `GET /submissions/{id}` — с проверкой доступа.
- `PATCH /submissions/{id}/grade` (teacher) — `{score?, feedback?, accept_ai: bool}`.

**Файлы**
- `GET /attachments/{submission_id}/{attachment_index}` — presigned URL (TTL 5 мин).

**Здоровье**
- `GET /healthz`, `GET /readyz`.

## 8. Фоновые задачи (ARQ)

- `grade_submission(submission_id)` — AI-grader.
- `send_metrics()` — крон, агрегаты в StatService.
- `register_stats_module()` — при старте, идемпотентно.
- `emit_widget_updated_snapshot(widget_id, reason)` — синхронно вызывается из сервиса виджетов (или асинхронно, если нужно дебаунсить — обсудим на реализации).

## 9. AI-grader

Промпт-шаблон (RU, structured output, temperature 0.2):

```
Ты — эксперт-проверяющий. Оцени ответ ученика на задание.

Задание: {prompt}
Эталонный ответ (если есть): {reference_answer}
Критерии оценки: {grading_criteria}
Максимальный балл: {max_score}

Ответ ученика:
{student_text_or_markdown}
[приложенные файлы передаются multimodal]

Верни строго JSON по схеме:
{
  "score": <число 0..max_score>,
  "feedback": "<комментарий для учителя на русском>",
  "rubric_breakdown": [
    {"criterion": "...", "points": N, "max_points": M, "comment": "..."}
  ]
}
```

При парс-ошибке/таймауте → статус `pending_teacher` без AI-данных + запись в `ai_logs` с error. Учитель проверит вручную.

## 10. Файлы

MinIO bucket `homework-attachments`. Ключи: `submissions/{widget_id}/{submission_id}/{uuid}_{filename}`. Загрузка — multipart через api. Отдача — presigned URL. Каскадное удаление при удалении сабмишна / задания / виджета.

## 11. Структура проекта

```
homework-widget-backend/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── alembic/
├── app/
│   ├── main.py
│   ├── config.py                # pydantic-settings
│   ├── deps.py                  # current_user, db sessions
│   ├── api/v1/
│   │   ├── widgets.py
│   │   ├── assignments.py
│   │   ├── questions.py
│   │   ├── homework.py
│   │   ├── submissions.py
│   │   └── attachments.py
│   ├── models/                  # SQLAlchemy
│   ├── schemas/                 # Pydantic v2
│   ├── services/
│   │   ├── widgets.py
│   │   ├── assignments.py
│   │   ├── auto_grader.py
│   │   ├── ai_grader.py
│   │   ├── widget_config.py     # сборка config-снапшотов + emit
│   │   ├── stats.py
│   │   ├── proxy_client.py
│   │   └── storage.py           # MinIO
│   ├── repositories/
│   │   ├── submissions.py       # Mongo
│   │   ├── ai_logs.py           # Mongo
│   │   └── snapshots.py         # Mongo
│   ├── workers/arq_worker.py
│   ├── db/
│   │   ├── postgres.py
│   │   └── mongo.py
│   └── core/
│       └── access.py            # проверки роли/владельца
└── tests/
```

## 12. Что НЕ входит в MVP

- Точечные назначения заданий конкретным ученикам.
- Снятие баллов за опоздание.
- Подсказки от AI ученикам.
- Статусы задания `draft/published/closed`.
- Сложные типы вопросов.
- Уведомления.
- CI/CD и деплой.

## 13. План работ

**Этап 0 — каркас (1 день).** docker-compose (api, worker, postgres, mongo, redis, minio), FastAPI скелет, подключения ко всем БД, healthz/readyz, базовый pytest.

**Этап 1 — виджеты и контекст (1–2 дня).** SQLAlchemy-модели widgets/assignments/questions/homework_details, миграции Alembic, идемпотентное создание виджета, `setInfo`, удаление с каскадом, контекст пользователя.

**Этап 2 — задания + widget:updated (2 дня).** CRUD assignments, сервис сборки config + снапшотов в Mongo, инкремент version, возврат `config` из соответствующих эндпоинтов.

**Этап 3 — тесты (2 дня).** CRUD вопросов, репозиторий submissions в Mongo, авто-проверка, попытки, стратегии финальной оценки.

**Этап 4 — домашки + файлы (2 дня).** Эндпоинты homework, multipart-приём, MinIO storage, presigned URL, дедлайны и `is_late`.

**Этап 5 — AI-grader (2–3 дня).** ARQ воркер, Gemini через прокси, structured output, multimodal для картинок/pdf, `ai_logs` в Mongo, обработка ошибок.

**Этап 6 — интерфейс препода (1 день).** `PATCH /submissions/{id}/grade`, фильтрация полей для student/teacher, проверки владения.

**Этап 7 — StatService (1 день).** Регистрация модуля, периодическая отправка агрегатов через прокси, обработка 401/404/429.

**Этап 8 — тесты и доводка (2 дня).** Юнит и интеграционные тесты ключевых сценариев, OpenAPI описание, README с инструкцией запуска.

Итого: ~14 рабочих дней.

---

Глянь — особенно по разделам 5 (модели), 6.2 (триггеры `widget:updated`) и 7 (API). Если всё ок — фиксируем и можем начинать с этапа 0.