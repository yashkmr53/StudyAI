# Testing — Phase 10

**Status:** CI pipeline with coverage gates; all new tests passing

---

## Test Structure

### Backend Tests
```
backend/
├── tests/                          # Existing API tests
│   ├── api/
│   │   ├── test_ai_classroom.py    # 9 tests
│   │   ├── test_documents.py       # 28 tests
│   │   └── ...
│   └── unit/
│       └── test_shared.py
├── apps/
│   ├── notebooks/tests/
│   │   └── test_notebooks.py       # 17 tests (NEW)
│   ├── ai_classroom/tests/
│   │   └── test_tag_rename.py      # 6 tests (NEW)
│   └── questions/tests/
│       └── test_document_questions.py  # 4 tests (NEW)
```

### Frontend Tests
```
frontend/
├── tests/
│   └── smoke.test.ts               # Existing
├── src/
│   └── services/storage/
│       └── outbox.test.ts          # NEW (to be added)
```

---

## Running Tests

### Backend
```bash
# All tests
cd backend && DJANGO_SETTINGS_MODULE=config.settings.test python -m pytest

# Specific module
DJANGO_SETTINGS_MODULE=config.settings.test python -m pytest apps/notebooks/tests/ -v

# With coverage
cd backend && coverage run -m pytest && coverage report --fail-under=80
```

### Frontend
```bash
cd frontend
npm test              # vitest run
npm run coverage      # vitest run --coverage
```

---

## Coverage Gates (CI)

| Target | Threshold | Tool |
|--------|-----------|------|
| Backend | ≥ 80% | `coverage.py` |
| Frontend | ≥ 70% | `@vitest/coverage-v8` |

### CI Configuration
```yaml
# Backend
coverage run -m pytest
coverage xml
coverage report --fail-under=80

# Frontend
npm run coverage -- --reporter=lcov
```

---

## Test Categories

### Unit Tests
- Model methods
- Service functions
- Utility functions
- Serializers

### Integration Tests
- API endpoint behavior
- Authentication/authorization
- Database transactions
- Celery task execution

### RLS Tests
- Owner isolation (user A cannot see user B's data)
- Cross-profile access attempts return 404

### Security Tests
- CORS headers present
- CSRF validation
- Rate limiting (429 responses)
- Budget enforcement (429 with details)
- Prompt injection directive in logs
- Data redaction counts

---

## New Tests Added (Phase 10)

### Notebooks (17 tests)
| Test | Description |
|------|-------------|
| `test_create_notebook` | Create with profile + subject |
| `test_create_notebook_without_subject` | Create without subject |
| `test_list_notebooks` | List user's notebooks |
| `test_retrieve_notebook` | Get single notebook |
| `test_update_notebook` | Patch title/description |
| `test_delete_notebook` | Delete notebook |
| `test_create_page` | Add page to notebook |
| `test_list_pages` | List notebook pages |
| `test_update_page_canvas_state` | Patch canvas_state |
| `test_delete_page` | Delete page |
| `test_append_strokes` | Add stroke lines |
| `test_list_lines` | List page lines |
| `test_alice_cannot_see_bob_notebook` | RLS: 404 for other user |
| `test_alice_cannot_list_bob_notebooks` | RLS: list only own |
| `test_alice_cannot_create_page_in_bob_notebook` | RLS: 404 |
| `test_alice_cannot_update_bob_notebook` | RLS: 404 |
| `test_alice_cannot_delete_bob_notebook` | RLS: 404 |

### Document Questions (4 tests)
| Test | Description |
|------|-------------|
| `test_list_document_questions` | Questions for document |
| `test_list_questions_for_nonexistent_document` | 404 |
| `test_list_questions_for_other_user_document` | RLS: 404 |
| `test_empty_questions_list` | Empty result |

### Tag Rename (6 tests)
| Test | Description |
|------|-------------|
| `test_rename_tag` | Valid rename |
| `test_rename_tag_same_name` | Idempotent |
| `test_rename_tag_empty_name` | 422 |
| `test_rename_tag_too_long` | 422 |
| `test_rename_nonexistent_tag` | 404 |
| `test_rename_tag_other_user` | RLS: 404 |

---

## Test Commands Reference

```bash
# Backend
cd backend
DJANGO_SETTINGS_MODULE=config.settings.test python -m pytest apps/notebooks/tests/ -v
DJANGO_SETTINGS_MODULE=config.settings.test python -m pytest apps/ai_classroom/tests/ -v
DJANGO_SETTINGS_MODULE=config.settings.test python -m pytest apps/questions/tests/ -v
DJANGO_SETTINGS_MODULE=config.settings.test python -m pytest tests/api/ -v

# With coverage
cd backend
coverage run -m pytest
coverage report --fail-under=80
coverage html  # detailed report

# Frontend
cd frontend
npm test
npm run coverage

# CI simulation
cd backend && DJANGO_SETTINGS_MODULE=config.settings.test python -m pytest --tb=short
cd frontend && npm run coverage
```

---

## Test Data Management

### Fixtures
- Django `TestCase` provides transaction rollback
- Each test creates own data in `setUp()`
- No shared fixtures needed

### RLS Test Pattern
```python
class MyRLSTests(TransactionTestCase):
    reset_sequences = True
    
    def setUp(self):
        self.alice = User.objects.create_user(...)
        self.alice_profile = Profile.objects.create(...)
        self.bob = User.objects.create_user(...)
        self.bob_profile = Profile.objects.create(...)
        # Each user gets their own subject
        self.alice_subject = Subject.objects.create(profile=self.alice_profile, ...)
        self.bob_subject = Subject.objects.create(profile=self.bob_profile, ...)
```

---

## Related Documentation

- `docs/phase_10/architecture/TRACEABILITY.md` — Test-to-gap mapping
- `docs/phase_6/operations/TESTING.md` — Base testing spec
- `.github/workflows/ci.yml` — CI pipeline config