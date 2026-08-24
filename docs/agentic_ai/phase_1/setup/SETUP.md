# Phase 1 — Setup & Development Guide

**Date:** 2026-08-24  
**Status:** COMPLETED

---

## Prerequisites

- Docker + Docker Compose
- Python 3.11+ (for local development)
- Ollama running locally (for LLM) or use mock provider

## Quick Start (Docker)

```bash
# 1. Clone and configure
git clone <repo>
cd StudyAI
cp .env.example .env
# Edit .env with generated secrets

# 2. Start all services
docker compose up -d --build

# 3. Pull Ollama model (first time only)
docker compose exec ollama ollama pull llama3.1:8b

# 4. Run migrations (includes agent tables)
docker compose run --rm api python manage.py migrate

# 5. Access
# API: http://localhost:8000
# Frontend: http://localhost
# Swagger: http://localhost:8000/api/docs/
```

## Local Development (Without Docker)

### Backend

```bash
cd backend

# Create venv
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install pytest pytest-django pytest-mock

# Set environment
export DJANGO_SETTINGS_MODULE=config.settings.dev
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export REDIS_URL=redis://localhost:6379/0

# Run migrations
python manage.py migrate

# Run server
python manage.py runserver 8000
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev
# Runs on http://localhost:5173
```

## Running Tests

### All Agent Tests

```bash
# In Docker (recommended)
docker compose run --rm api sh -c "pip install pytest pytest-django pytest-mock 2>/dev/null && python -m pytest apps/agents/tests/ -v"

# Or locally
cd backend
source .venv/bin/activate
export DJANGO_SETTINGS_MODULE=config.settings.test
python -m pytest apps/agents/tests/ -v
```

### Specific Test Files

```bash
# Tool tests
python -m pytest apps/agents/tests/test_tools.py -v

# With coverage
python -m pytest apps/agents/tests/ --cov=apps.agents --cov-report=term-missing
```

### Full Test Suite (may have pre-existing DB issues)

```bash
docker compose run --rm api sh -c "pip install pytest pytest-django pytest-mock 2>/dev/null && python -m pytest tests/ -v --tb=short -x"
```

## Configuration

### Settings (`backend/config/settings/base.py`)

```python
# Agent Configuration
AGENT_ENABLED = True
AGENT_MAX_ITERATIONS = 5
AGENT_MAX_TOOL_CALLS = 10
AGENT_REQUEST_TIMEOUT_SECONDS = 60
AGENT_PER_TOOL_TIMEOUT_SECONDS = 30
AGENT_PROMPT_VERSION = "agent_orchestrator:v1"

# Per-tool timeout overrides (seconds)
AGENT_TOOL_TIMEOUTS = {
    "search_notes": 15,
    "search_reference_books": 15,
    "get_mastery": 5,
    "verify_evidence": 10,
    "get_document": 5,
    "get_subject_context": 5,
}
```

### Environment Variables (`.env`)

```bash
# Agent
AGENT_ENABLED=true
AGENT_MAX_ITERATIONS=5
AGENT_MAX_TOOL_CALLS=10
AGENT_REQUEST_TIMEOUT_SECONDS=60
AGENT_PER_TOOL_TIMEOUT_SECONDS=30

# LLM Provider (for agent)
LLM_PROVIDER_CHAIN=ollama,mock
OLLAMA_BASE_URL=http://ollama:11434
LLM_MODEL=llama3.1:8b
```

## Adding New Tools

### 1. Create Tool Module

```python
# apps/agents/tools/my_category.py
from apps.agents.tools.base import ToolInput, ToolOutput, ToolMetadata, BaseTool
from pydantic import Field

class MyToolInput(ToolInput):
    param1: str = Field(..., description="Description")
    param2: int = Field(10, ge=1, le=100)

class MyToolOutput(ToolOutput):
    result: str
    count: int

class MyTool(BaseTool):
    metadata = ToolMetadata(
        name="my_tool",
        description="What this tool does for the agent",
        input_schema=MyToolInput,
        output_schema=MyToolOutput,
        requires_auth=True,
        timeout_seconds=30,
        category="my_category",
    )

    def _execute(self, input: MyToolInput, *, user, request_id: str) -> MyToolOutput:
        # Your tool logic here
        profile = Profile.objects.get(user=user)
        # ... do work ...
        return MyToolOutput(result="success", count=42)

# Auto-register
from apps.agents.tools import get_tool_registry
get_tool_registry().register(MyTool())
```

### 2. Import in `apps/agents/tools/__init__.py`

```python
from apps.agents.tools import my_category  # noqa: F401
```

### 3. The tool is now available to the agent

The agent's system prompt will automatically include the new tool's description and schemas.

## Debugging

### Enable Debug Logging

```python
# In settings or via env
LOGGING = {
    "loggers": {
        "apps.agents": {"level": "DEBUG"},
        "apps.agents.tools": {"level": "DEBUG"},
        "apps.agents.services": {"level": "DEBUG"},
    }
}
```

### Inspect Agent Execution Log

```bash
# Via Django shell
docker compose run --rm api python manage.py shell
>>> from apps.agents.models import AgentExecutionLog
>>> log = AgentExecutionLog.objects.latest('created_at')
>>> log.tool_call_sequence
>>> log.iterations
>>> log.outcome
```

### Test Tool Directly

```python
# In Django shell
from apps.agents.tools import get_tool_registry
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.first()
registry = get_tool_registry()

tool = registry.get("search_notes")
result = tool.execute(
    tool.metadata.input_schema(query="test query", top_k=5),
    user=user,
    request_id="debug-123"
)
print(result.model_dump_json(indent=2))
```

### View Prompt Sent to LLM

```python
# In orchestrator or via debug endpoint
from apps.agents.prompts.agent_prompts import build_agent_system_prompt
print(build_agent_system_prompt())
```

## Common Issues

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: apps.agents` | Run `docker compose build api` after adding new files |
| `Tool not found` | Ensure tool module is imported in `apps/agents/tools/__init__.py` |
| `ValidationError` on tool input | Check Pydantic field definitions match what agent sends |
| Agent loops infinitely | Check AGENT_MAX_ITERATIONS, AGENT_MAX_TOOL_CALLS |
| Tool timeout | Increase AGENT_PER_TOOL_TIMEOUT_SECONDS or tool-specific timeout |
| Cross-profile access | Tool should raise Forbidden — check ProfileAuthorizationService |

## Code Style

```bash
# Format
docker compose run --rm api python -m ruff format apps/agents/

# Lint
docker compose run --rm api python -m ruff check apps/agents/

# Type check (if mypy configured)
docker compose run --rm api python -m mypy apps/agents/
```

## IDE Setup (VS Code)

```json
// .vscode/settings.json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/backend/.venv/bin/python",
  "python.testing.pytestEnabled": true,
  "python.testing.pytestArgs": ["apps/agents/tests"],
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.organizeImports": "explicit"
  }
}
```