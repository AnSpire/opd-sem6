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




## 11. Что НЕ входит в MVP

- Точечные назначения заданий конкретным ученикам.
- Снятие баллов за опоздание.
- Подсказки от AI ученикам.
- Статусы задания `draft/published/closed`.
- Сложные типы вопросов.
- Уведомления.
- CI/CD и деплой.

## 12. План работ

**~~Этап 0 — каркас~~ ✅ ГОТОВО.**
Реализовано: `docker-compose.yml` (api, worker, postgres, mongo, redis, minio), `Dockerfile` (targets api/worker), FastAPI-скелет (`app/main.py`, `app/config.py`, `app/deps.py`), подключения к БД (`app/db/postgres.py`, `app/db/mongo.py`), эндпоинты `GET /api/v1/healthz` и `GET /api/v1/readyz`, ARQ WorkerSettings-заглушка, дымовые тесты (2 passed). Вся структура директорий из ТЗ создана (`models/`, `schemas/`, `services/`, `repositories/`, `core/`, `api/v1/`).
Ключевые решения: контекст пользователя — кастомные заголовки `X-User-Id`, `X-User-Role`, `X-Board-Id`, `X-Widget-Id`.

**~~Этап 1 — виджеты и контекст~~ ✅ ГОТОВО.**
Реализовано: SQLAlchemy-модели `Widget`, `Assignment`, `Question`, `HomeworkDetails`, `StatsModule` с `TimestampMixin`; Alembic-миграция применена (5 таблиц в БД); `app/services/widgets.py` — идемпотентный upsert по `(board_id, creator_user_id)`, get_or_404, delete; `app/core/access.py` — `require_teacher`, `require_widget_owner`; роутер `app/api/v1/widgets.py` — `POST /widgets`, `GET /widgets/{id}`, `POST /widgets/{id}/info`, `DELETE /widgets/{id}`.

**~~Этап 2 — задания + widget:updated~~ ✅ ГОТОВО.**
Реализовано: `app/schemas/assignment.py` (`AssignmentCreate/Update/Out`, `AssignmentPreview`, `WidgetConfigOut`, `AssignmentWithConfigOut`, `ConfigOut`); `app/services/assignments.py` — полный CRUD; `app/repositories/snapshots.py` — `upsert_snapshot` с `$inc version`; `app/services/widget_config.py` — `build_config` + `emit_widget_updated`; роутер `app/api/v1/assignments.py` — все 5 эндпоинтов; `tests/test_assignments.py` (23 теста, все зелёные). Исправлен баг `connectionTimeoutMS` → `connectTimeoutMS` в `conftest.py`.

**~~Этап 3 — тесты~~ ✅ ГОТОВО.**
Реализовано: `app/schemas/question.py`, `app/services/questions.py`, роутер `app/api/v1/questions.py` — CRUD вопросов, `correct_answer` скрыт для student; `app/repositories/submissions.py` — полный репозиторий с MongoDB-индексами; `app/services/auto_grader.py` — авто-грейдинг single/multi/bool/short_text; `app/schemas/submission.py`; `app/api/v1/submissions.py` — POST/GET сабмишенов для тестов, дедлайны, max_attempts, final_score_strategy (last/best/average); `tests/test_questions.py` (15 тестов), `tests/test_submissions_test.py` (17 тестов). Итого 68 тестов — все зелёные.

**Этап 4 — домашки + файлы (2 дня).**
- `app/schemas/homework.py` — `HomeworkDetailsCreate/Update/Out`; `app/api/v1/homework.py` — `PUT /assignments/{id}/homework`, `GET /assignments/{id}/homework`.
- `app/services/storage.py` — обёртка над MinIO: `upload_object(bucket, key, data, content_type)`, `delete_object(key)`, `presigned_get_url(key, ttl=300)`; создание бакета при старте если не существует.
- `app/api/v1/submissions.py` (дополнение) — `POST /assignments/{id}/submissions` для типа `homework`: multipart/form-data, приём до 5 файлов ≤ 10 МБ, загрузка в MinIO по схеме `submissions/{widget_id}/{submission_id}/{uuid}_{filename}`, статус → `pending_ai`.
- `app/api/v1/attachments.py` — `GET /attachments/{submission_id}/{attachment_index}`: проверка доступа, возврат presigned URL (TTL 5 мин).
- Проверка дедлайна при сабмишне: `deadline` + `allow_late_submissions` → `is_late=true` или 409.

**Этап 5 — AI-grader (2–3 дня).**
- `app/services/proxy_client.py` — тонкий `httpx.AsyncClient` с `proxies=settings.proxy_url`; используется для всех исходящих запросов.
- `app/services/ai_grader.py` — вызов Gemini 2.5 Flash через `google-genai` SDK + прокси: формирование промпта (текст + файлы multimodal), structured output по JSON-схеме `{score, feedback, rubric_breakdown}`, temperature 0.2.
- `app/repositories/ai_logs.py` — `create_log(submission_id, request, response, latency_ms, status, error)`.
- `app/workers/arq_worker.py` — задача `grade_submission(ctx, submission_id)`: загружаем сабмишен, вызываем `ai_grader`, пишем результат в `grading.ai`, статус → `pending_teacher`; при ошибке парсинга/таймауте — статус `pending_teacher` без AI-данных, лог с error.
- Регистрация задачи в `WorkerSettings.functions`; при создании homework-сабмишена ставим задачу в очередь через `arq.create_pool`.

**Этап 6 — интерфейс препода (1 день).**
- `app/schemas/submission.py` — `SubmissionOut` с двумя проекциями: для teacher (включает `grading.ai`) и для student (только `grading.final` после утверждения, статус `pending_teacher` → «на проверке»).
- `PATCH /submissions/{id}/grade` — тело `{score?, feedback?, accept_ai: bool}`: если `accept_ai=true` — копируем AI-оценку в `final`; иначе берём переданные `score`/`feedback`; статус → `graded`.
- `GET /assignments/{id}/submissions` — teacher видит все, student только свои (`student_user_id == user.user_id`).
- `GET /submissions/{id}` — проверка доступа: teacher-владелец виджета или student-автор сабмишена.

**Этап 7 — StatService (1 день).**
- `app/services/stats.py` — `register_module()`: `POST /api/stats/module/create` через прокси, сохранение `module_id`/`token` в таблицу `stats_module`; идемпотентно (если запись есть — пропуск).
- ARQ крон-задача `send_metrics()` (каждые N минут): агрегация по активным виджетам (`widgetId`, `assignmentsCount`, `submissionsCount`, `gradedCount`, `averageScore`, `lastActivityAt`), `PUT /api/stats/module/metrics`.
- Обработка ответов StatService: 401 → перерегистрация (`register_module()`); 429 → `asyncio.sleep(Retry-After)`; 404 → пропуск виджета.
- Запуск `register_module()` при старте api через lifespan (после проверки соединений).

**Этап 8 — тесты и доводка (2 дня).**
- Интеграционные тесты (pytest + `AsyncClient`) ключевых сценариев: создание виджета → задание → сабмишен теста → авто-грейдинг; домашка → `pending_ai` → grade препода.
- Проверка изоляции student/teacher: student не получает `correct_answer`, не видит чужие сабмишены, не видит AI-оценку.
- OpenAPI: теги, `summary`, примеры схем для основных эндпоинтов.
- `README.md` — инструкция запуска (`docker compose up --build`), переменные окружения, примеры curl-запросов.
- Финальный прогон `pytest` и `docker compose up` smoke-проверка всего стека.

# Исправления в тестовом окружении

## 1. Раздельные конфиги для тестов и контейнеров

**Проблема:** один `.env` использовался и контейнерами, и тестами. Внутри Docker нужны имена сервисов (`postgres:5432`, `mongo:27017`), а с хоста — `localhost` с проброшенными портами (`localhost:5433`, `localhost:27018`). Тесты зависали, потому что пытались подключиться к недоступным адресам.

**Решение:** создан отдельный `.env.test` с хостовыми адресами и проброшенными портами.

## 2. load_dotenv строго до импортов app.*

**Проблема:** `pydantic-settings` инстанцирует `Settings()` в момент импорта `app.config`. Если `load_dotenv` стоит после — `.env.test` не применяется, настройки берутся из `.env`.

**Решение:** в `conftest.py` `load_dotenv` перенесён в самый верх, до любых импортов из `app.*`:

```python
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env.test", override=True)

from app.config import settings  # только после
```

## 3. authSource=admin в MONGO_URI

**Проблема:** root-пользователь Mongo живёт в БД `admin`. Без `?authSource=admin` аутентификация молча зависала при обращении к другим БД.

**Решение:** добавлен параметр в URI:
MONGO_URI=mongodb://mongo:mongo@localhost:27018/?authSource=admin
## 4. Миграции против тестовой БД

**Проблема:** тестовая БД была пустой, таблицы не существовали — все тесты падали с `relation "widgets" does not exist`.

**Решение:** перед первым запуском тестов применены миграции:

```bash
set -a; source .env.test; set +a
uv run alembic upgrade head
```

## 5. Event loop scope

**Проблема:** фикстуры были session-scoped, а тесты запускались в function-scoped loop. Соединения asyncpg и Motor привязывались к session-loop, тесты исполнялись в новом function-loop — отсюда `RuntimeError: Task got Future attached to a different loop`.

**Решение:** в `pyproject.toml` выровнены оба scope:

```toml
[tool.pytest.ini_options]
asyncio_default_fixture_loop_scope = "session"
asyncio_default_test_loop_scope = "session"
```

## 6. Таймауты подключения

**Проблема:** asyncpg и Motor по умолчанию не имеют коротких таймаутов — недоступный сервис вызывал молчаливое зависание вместо внятной ошибки.

**Решение:** явные таймауты в `conftest.py`:

```python
mongo.client = AsyncIOMotorClient(
    settings.mongo_uri,
    serverSelectionTimeoutMS=3000,
    connectTimeoutMS=3000,
)

conn = await asyncpg.connect(_pg_dsn(), timeout=3)
```