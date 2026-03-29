# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**hostess** is an async Python REST API built on **Starlette** (ASGI) for a RAG/knowledge-base Q&A system. (The README describes a Flask blog — ignore it, it is stale.)

## Running the Server

```bash
# Development (port 7788 matches the test scripts)
uvicorn app:app --port 7788

# Production
uvicorn app:app --workers 4 --host 0.0.0.0 --port 8000
```

## Running the Task Worker

```bash
huey_consumer worker.huey
```

## Running Tests

Tests are manual HTTP scripts in `tests/`. Run them individually while the server is up:

```bash
python tests/task_list.py
```

## Installing Dependencies

No `requirements.txt` exists. Install manually (see `docs/pip.sql` for reference):

```bash
python -m pip install asyncmy httpx sqlalchemy starlette orjson uvicorn loguru cryptography huey PyJWT
```

## Architecture

### Entry Points

- `app.py` — Uvicorn target; calls `create_app()` from `src.main`
- `worker.py` — Huey consumer target; imports all task modules then exposes `src.core.worker.huey`

### Layer Structure

```
src/
  main.py          # App factory: routes, middleware, exception handlers, lifespan
  routes.py        # URL → view mapping (all routes are POST)
  core/            # Infrastructure: DB, config, Huey, JWT utils, response helpers, exceptions
  domains/         # Business logic by domain (items/, users/)
  middleware/      # CORS + JWT AuthenticationMiddleware
  utils/           # orjson wrappers, JWT helpers, datetime helpers
```

### Request Flow

1. CORS middleware (outermost)
2. `JWTAuthBackend` (`src/middleware/guards.py`) — extracts Bearer token, populates `request.user` with `JWTUser(user_id, username, roles)`
3. Starlette route → domain `views.py`
4. Views call domain `service.py`, which calls `repository.py` for DB access
5. `src/core/response.py` `ok()` / `fail()` helpers return orjson-backed responses

### Configuration

`src/core/config.py` — no `.env` file; config is hardcoded. Dev mode is auto-selected when `DEBUG=1` **or** when running on Windows. DB target: `mysql+asyncmy://root:admin@127.0.0.1:3306/hostess`.

### Key Patterns

- **Responses:** always use `ok(data)` or `fail(biz_code)` from `src.core.response`
- **Errors:** raise subclasses of `BusinessError` from `src.core.exceptions`; the exception handlers in `src/core/handlers.py` convert them to JSON automatically
- **Auth guards:** use `@requires('authenticated')` or `@requires('permission:name')` on views
- **Async tasks:** define with `@huey.task()` in a domain's `tasks.py`; import them in `worker.py` to register
- **Business error codes:** defined in `src/core/codes.py` as `BizCode` enum (users 1001–1xxx, items 2001–2xxx, orders 3001–3xxx, payments 5001–5xxx)

### Database

MySQL 8.0+ via SQLAlchemy async (`asyncmy`). Pool: size 20, max overflow 20, recycle 1800s. Schema is in `docs/roles.sql`. Tables cover: users, roles/permissions, knowledge bases, documents, chunks, conversations, query history.

### Task Queue

Huey (`MemoryHuey` — in-process, non-persistent). Redis backend is commented out in `src/core/worker.py`. Switch to Redis for production.
