# homework-widget-backend

Backend для npm-виджета `homework-widget`. Поддерживает два типа заданий: **тесты** (автопроверка) и **домашки** (AI-оценка через Gemini + утверждение преподавателем).

## Стек

- **FastAPI** + SQLAlchemy 2.0 async (PostgreSQL) + Motor (MongoDB)
- **ARQ** — фоновые задачи (AI-grader, метрики StatService)
- **MinIO** — хранилище файлов (вложения к домашкам)
- **Gemini 2.5 Flash** — AI-оценка развёрнутых ответов
- **Docker Compose** — полный стек одной командой

## Быстрый старт

```bash
cp .env.example .env
# Заполни GEMINI_API_KEY (и STATS_SERVICE_URL если нужно)

docker compose up --build
```

API будет доступен на `http://localhost:8000`.  
Интерактивная документация: `http://localhost:8000/docs`

### Применение миграций

При первом запуске или после изменений схемы:

```bash
docker compose exec api alembic upgrade head
```

## Переменные окружения

| Переменная | Описание | Пример |
|---|---|---|
| `POSTGRES_DSN` | URI подключения к PostgreSQL | `postgresql+asyncpg://user:pass@postgres:5432/homework` |
| `MONGO_URI` | URI подключения к MongoDB | `mongodb://mongo:mongo@mongo:27017/?authSource=admin` |
| `MONGO_DB` | Имя базы MongoDB | `homework` |
| `REDIS_URL` | URI Redis | `redis://redis:6379/0` |
| `MINIO_ENDPOINT` | Адрес MinIO | `minio:9000` |
| `MINIO_ACCESS_KEY` | Ключ доступа MinIO | `minioadmin` |
| `MINIO_SECRET_KEY` | Секрет MinIO | `minioadmin` |
| `MINIO_BUCKET` | Имя бакета | `homework-attachments` |
| `GEMINI_API_KEY` | API-ключ Google Gemini | `AIza...` |
| `PROXY_URL` | HTTP-прокси для исходящих запросов (опц.) | `http://proxy:8080` |
| `STATS_SERVICE_URL` | URL StatService (опц.) | `http://stats:3000` |
| `STATS_MODULE_NAME` | Имя модуля в StatService | `homework-widget` |

## Запуск тестов

Тесты запускаются с хоста и подключаются к запущенным сервисам через `.env.test`.

```bash
# 1. Запусти сервисы (если не запущены)
docker compose up -d postgres mongo redis minio

# 2. Применить миграции к тестовой БД
set -a; source .env.test; set +a
uv run alembic upgrade head

# 3. Запустить тесты
uv run pytest
```

Текущее покрытие: **115 тестов**.

## Ручное тестирование

В `tests/manual_tests/` лежат bash-скрипты с curl-запросами для проверки основных флоу:

| Скрипт | Сценарий |
|---|---|
| `flow_test_assignment.sh` | Тест с автопроверкой (single-choice вопрос) |
| `flow_homework_assignment.sh` | Домашка с файлом, ручная оценка препода |
| `flow_ai_grading.sh` | Полный цикл AI-оценки (требует воркер + Gemini API key) |

```bash
bash tests/manual_tests/flow_ai_grading.sh
```

## Роли и авторизация

Контекст пользователя передаётся через HTTP-заголовки (доверие к фронту):

| Заголовок | Описание |
|---|---|
| `X-User-Id` | ID пользователя |
| `X-User-Role` | `teacher` или `student` |
| `X-Board-Id` | ID доски |
| `X-Widget-Id` | ID виджета |

## Архитектура

```
api (FastAPI)          worker (ARQ)
├── /api/v1/           ├── grade_submission()   — AI-оценка домашек
│   ├── widgets            └── Gemini 2.5 Flash
│   ├── assignments    └── run_send_metrics()   — крон 10 мин, StatService
│   ├── questions
│   ├── homework       PostgreSQL (конфигурация)
│   ├── submissions    ├── widgets, assignments, questions
│   └── attachments    ├── homework_details, stats_module
│                      MongoDB (активность)
└── lifespan           ├── submissions, ai_logs
    ├── register_module()   └── widget_config_snapshots
    └── ensure_bucket()    MinIO (файлы вложений)
```
