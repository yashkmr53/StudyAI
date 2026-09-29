# Phase 10D — Chat Multi-Turn Context Fix

## Status: COMPLETE

**Branch:** `fix/phase-10d-chat-multi-turn-context`

---

## 1. Root Cause

Ask StudyAI was treating every user message as an independent, standalone query. When the user typed "yes" after an assistant response about backpropagation, the LLM received **only** `User: yes` — with no prior conversation context. This caused the model to respond with a generic "what would you like to study?" rather than continuing the discussion.

**Specific gaps identified:**

| Layer | Issue |
|-------|-------|
| **Backend `ChatService.ask()`** | Did not retrieve previous messages before calling the LLM |
| **Backend `answer_generation_node()`** | Built a single-message prompt (`Prompt.user`) without conversation history |
| **Backend `Prompt` dataclass** | Had no `messages` field to carry structured multi-turn history |
| **Backend `route_query_node()`** | Classified contextual follow-ups like "yes" as `general_knowledge` instead of `conversational` |
| **Frontend `ChatPage.tsx`** | Did not persist `activeThreadId` across page reloads (sessionStorage/URL) |

---

## 2. Files Changed

### Backend

| File | Change |
|------|--------|
| `providers/base.py` | Added `messages: list[dict]` field to `Prompt` dataclass |
| `providers/llm/qwen35.py` | Updated `generate()`, `generate_structured()`, `generate_structured_with_image()` to build `SystemMessage/HumanMessage/AIMessage` chain from `prompt.messages` |
| `providers/llm/local.py` | Updated `_generate_with_chat()` to use `prompt.messages` for multi-turn context |
| `providers/llm/mock.py` | Updated `_chat()` to produce contextual responses when conversation history is present |
| `apps/chat/langgraph_nodes.py` | Added `_CONTINUATION_PATTERNS` for detecting follow-ups; updated routing and answer generation |
| `apps/chat/services.py` | Added `get_bounded_history()`; updated `ask()` and `stream()` to persist-first then retrieve history |
| `tests/unit/test_chat_multi_turn.py` | **New** — 7 regression tests |
| `scripts/test_live_chat_multi_turn.py` | **New** — Live verification script |

### Frontend

| File | Change |
|------|--------|
| `components/chat/ChatPage.tsx` | Added `selectThread()` with `sessionStorage` + URL `?session=` persistence; restored thread on reload |
| `tests/e2e/phase10d_acceptance.mjs` | **New** — Browser E2E acceptance test |

---

## 3. How Conversation History Is Now Retrieved

```
ChatService.ask()
  │
  ├── 1. Persist the user message (ChatMessage.objects.create)
  │
  ├── 2. get_bounded_history(session, exclude_msg_id=user_msg.pk)
  │      │
  │      ├── Fetches the most recent 20 messages (configurable: CHAT_MAX_HISTORY_MESSAGES)
  │      ├── Excludes the just-created user message (to avoid duplication)
  │      ├── Orders chronologically
  │      └── Trims oldest messages if total > 12,000 chars (configurable: CHAT_MAX_HISTORY_CHARS)
  │
  ├── 3. Appends current user message to history
  │
  └── 4. Passes history into ChatState → LangGraph
```

The bounded history is a deterministic sliding window — no summarization or complex memory.

---

## 4. How History Is Passed to qwen3.5:4b

In `answer_generation_node()`:

```python
# Build structured messages from conversation history
structured_messages = []
for msg in conversation_history:
    structured_messages.append({
        "role": msg["role"],           # "user" or "assistant"
        "content": msg["content"],
    })

# Append current user query
structured_messages.append({"role": "user", "content": user_request})

# Attach to Prompt
prompt = Prompt(
    name="answer",
    system="...",
    user=flattened_text,               # Backward-compatible flat text
    messages=structured_messages,      # Structured multi-turn (used by providers)
)
```

In `Qwen35Provider.generate()`:

```python
if prompt.messages:
    chat_messages = [SystemMessage(content=prompt.system)]
    for msg in prompt.messages:
        if msg["role"] == "user":
            chat_messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            chat_messages.append(AIMessage(content=msg["content"]))
    result = self._llm.invoke(chat_messages)
```

---

## 5. Chat/Profile Isolation

| Isolation Type | Mechanism |
|---------------|-----------|
| **Cross-chat** | `get_bounded_history()` filters by `session=session` — only messages from the active `ChatSession` are retrieved |
| **Cross-profile** | `ChatSession` is created with `profile=request.user.active_profile`. API views filter sessions by active profile. Messages from another profile's sessions cannot be accessed |
| **Cross-user** | Sessions are scoped to the authenticated user's profile. The API view enforces `request.user` filtering |

### Verified scenarios:
- **Test D**: Two separate chats — messages from Chat B never appear in Chat A's LLM context
- **Test E**: Profile A's private messages are NOT accessible when Profile B sends a request

---

## 6. Tests Added

### Unit Tests (7 tests — all passing)

| Test | Description |
|------|-------------|
| **Test A** | Direct continuation: "yes" after backpropagation response references prior context |
| **Test B** | Contextual follow-up: "Why does it help with overfitting?" after dropout explanation |
| **Test C** | Three-turn conversation: CNNs → filter → example — all turns available |
| **Test D** | Separate chats: CNN chat and database chat remain isolated |
| **Test E** | Profile isolation: Profile A's messages don't leak to Profile B |
| **Test F** | Reload persistence: messages survive simulated page reload |
| **Test G** | Streaming multi-turn: `ChatService.stream()` also preserves context |

```
$ docker exec ... python manage.py test tests.unit.test_chat_multi_turn
Ran 7 tests in 1.086s — OK
```

### Existing Tests (unbroken)

```
$ docker exec ... python manage.py test tests.unit.test_chat_graph
Ran 38 tests in 4.2s — OK

$ cd frontend && npm test
73 tests — all passing
```

### Browser E2E Acceptance Test

`frontend/tests/e2e/phase10d_acceptance.mjs` — Puppeteer-based test covering:
- Authentication and navigation to Ask StudyAI
- 3-turn conversation (backpropagation → "yes" → example)
- Verification that "yes" gets a contextual response (not generic)
- Page reload + message persistence
- Continue conversation after reload
- Chat isolation (Chat A vs Chat B)

### Live Verification with qwen3.5:4b

```
scripts/test_live_chat_multi_turn.py — executed against Docker API container

Turn 1: "What is backpropagation?" → 463-char response about neural network learning
Turn 2: "yes" → 1240-char response continuing the topic with gradients/chain rule
Turn 3: "Can you give an example?" → response with concrete example
Result: 6 messages persisted, contextual continuations confirmed ✅
```

---

## 7. Browser E2E Results

The end-to-end browser test was executed using Puppeteer against the live Docker stack (`frontend`, `api`, `db`, `redis`, `worker`, `minio`, `ollama` with `qwen3.5:4b`):

**Script:** `frontend/tests/e2e/phase10d_acceptance.mjs`  
**Results file:** `frontend/tests/e2e/screenshots/phase10d/results.json`

### Checklist Results (15/15 Passed)

| Check | Expected Behavior | Result |
|---|---|---|
| `authenticated` | Authenticate as `admin@studyai.dev` & activate profile | ✅ PASS |
| `chatPageLoaded` | Navigate to `/ai-classroom/chat` | ✅ PASS |
| `chatACreated` | Create new disposable Chat A | ✅ PASS |
| `turn1Replied` | Send "Explain backpropagation." & receive assistant reply (455 chars) | ✅ PASS |
| `turn2IsContextual` | Send "yes" & receive contextual follow-up (370 chars, not generic) | ✅ PASS |
| `turn3Replied` | Send "Can you give a concrete example with numbers?" (365 chars) | ✅ PASS |
| `allBubblesVisible` | All 6 bubbles visible in current thread (3 user + 3 assistant) | ✅ PASS |
| `messagesPersistedAfterReload` | Refresh page, conversation remains intact (>= 6 bubbles) | ✅ PASS |
| `sessionIdPreserved` | URL `?session=` and sessionStorage maintain exact same chat ID | ✅ PASS |
| `turn4AfterReloadReplied` | Continue after reload: "What about vanishing gradients?" (605 chars) | ✅ PASS |
| `chatBCreated` | Create second chat (Chat B) with new distinct session ID | ✅ PASS |
| `chatBStartsEmpty` | Chat B initializes with 0 message bubbles | ✅ PASS |
| `chatBReplied` | Send "What is a SQL JOIN?" in Chat B & get answer (371 chars) | ✅ PASS |
| `chatAHistoryIntact` | Switch back to Chat A via sidebar; all previous turns restored | ✅ PASS |
| `correctSessionIds` | Network POST requests strictly isolated to respective session IDs | ✅ PASS |

**Metrics:**
- **Checks passed:** 15 / 15 (100%)
- **Console errors:** 0
- **Network requests captured:** 16 chat API calls
- **Screenshots captured:**
  - `01_authenticated.png`
  - `02_chat_page.png`
  - `03_turn1_backprop.png`
  - `04_turn2_yes.png`
  - `05_turn3_example.png`
  - `06_after_reload.png`
  - `07_turn4_after_reload.png`
  - `08_chat_b.png`
  - `09_chat_a_restored.png`

---

## 8. Any Remaining Limitations

1. **Sliding window bound** — History retrieval is capped at 20 messages or 12,000 characters (`CHAT_MAX_HISTORY_MESSAGES` and `CHAT_MAX_HISTORY_CHARS`). In exceptionally long sessions, older conversation context drops off.
2. **Contextual continuation heuristic** — Continuation intent uses a high-precision pattern list and fallback check; queries with entirely ambiguous vocabulary without explicit pronouns may still route through general knowledge retrieval (though they retain full conversation history in the LLM prompt).
3. **Local LLM generation speed** — On local hardware, CPU/GPU inference for `qwen3.5:4b` with streaming responses requires 15–45s per turn depending on system load.

---

PHASE 10D COMPLETE
