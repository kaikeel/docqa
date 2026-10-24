# Technical spec — PF-20261025-docqa (Kaikeel DocQA) v0.1.0

Tác giả: sol-architect · Ngày: 2026-10-25 (bổ sung chat + widget cùng ngày) · Trạng thái: SHAPE ·
Scope gốc: `PROJECT.md` (AC1–AC8)

## Tóm tắt giải pháp

Một package Python nhỏ (`docqa`) chạy local, không cần dịch vụ ngoài ngoài Claude API:

1. **Ingest**: đọc `.md`/`.txt`/`.pdf` trong một thư mục → tách chunk ~800 ký tự, chồng lấn ~150 →
   lưu vào **một file SQLite** (bảng `chunks` + bảng ảo FTS5 `chunks_fts`).
2. **Retrieve**: BM25 bằng hàm `bm25()` của SQLite FTS5, sau một interface `Retriever` (thay bằng vector
   search sau này mà không đụng service). Có **ngưỡng điểm**: không chunk nào vượt ngưỡng → `found=false`,
   **không gọi LLM** (ADR 0002).
3. **Answer**: gửi các chunk cho Claude dưới dạng `document` block văn bản thuần, bật `citations` — trích dẫn
   do API trả về (đoạn trích nguyên văn + chỉ số document), ta chỉ map về file nguồn, không tự parse (ADR 0003).
4. **Giao diện**: CLI (`docqa ingest|ask|eval`) và API FastAPI (`POST /ingest`, `POST /ask`, `POST /chat`,
   `GET /health`, `GET /`).
   - **Chat nhiều lượt stateless** (`POST /chat`, ADR 0004): client gửi cả lịch sử `messages[{role, content}]`,
     server không lưu phiên. Lịch sử đi vào request Claude dạng text thuần; document block chỉ nằm ở lượt user
     cuối. Truy vấn retriever dựng **tất định, không gọi LLM** từ câu hỏi mới nhất + câu hỏi user ngay trước
     (ADR 0005).
   - **Widget mẫu** (`GET /`, ADR 0006): một file HTML tự chứa, không framework/CDN, chỉ ghi dữ liệu vào DOM
     bằng `textContent`, CSP chặt dùng hash cho script/style inline.
5. **Eval**: `docqa eval examples/eval.jsonl --retrieval-only` đo hit@k không cần API key; chế độ đầy đủ
   (có key) đo thêm tỉ lệ câu trả lời có trích dẫn.

Không có web UI đầy đủ (chỉ widget mẫu), không lưu phiên chat phía server, không vector DB/embeddings, không
auth, không OCR, không deploy (xem Out of scope).

### Ràng buộc kỹ thuật đã chốt

- **Python 3.12** (`/opt/homebrew/bin/python3.12`), quản lý bằng **uv 0.6.3** (`/opt/homebrew/bin/uv`, CI ghim
  cùng bản), có `uv.lock` commit.
- Package `docqa`, layout `src/docqa/`, CLI entry point `docqa` (`[project.scripts] docqa = "docqa.cli:app"`).
- Phụ thuộc runtime tối thiểu, pin chính xác trong `pyproject.toml` (đã resolve ở T1):

  | Gói | Pin | Vai trò | Vòng tech-radar |
  |---|---|---|---|
  | `anthropic` | `==2.3.0` | Gọi Claude (SDK chính thức) | Adopt |
  | `fastapi` | `==0.162.0` | HTTP API (+ pydantic đi kèm) | Adopt |
  | `uvicorn` | `==0.54.0` | ASGI server | (đi kèm FastAPI) |
  | `pypdf` | `==6.21.2` | Trích text PDF (BSD, thuần Python) | ngoài radar — xem dưới |
  | `typer` | `==0.27.3` | CLI | ngoài radar — xem dưới |

  Dev: `ruff==0.17.2`, `mypy==2.4.0`, `pytest==9.1.1`, `pytest-cov==7.1.0`, `httpx==0.28.1` (cho
  `fastapi.testclient`; SDK `anthropic` dùng `httpx2` riêng, không xung đột). `sqlite3` là thư viện chuẩn
  (SQLite = Adopt); FTS5 có sẵn trong bản SQLite của CPython chính thức/Homebrew/`python:3.12-slim` — T4 có test
  kiểm `fts5` khả dụng. Widget **không thêm phụ thuộc nào** (HTML/CSS/JS thuần, `importlib.resources`, `hashlib`).

- **Lý do dùng công cụ ngoài vòng Adopt/Trial**:
  - `uv`: công cụ quản lý môi trường/lock (không phải phụ thuộc runtime); nhanh, lock tái lập được, giúp đạt
    AC6 (≤ 10 phút từ máy sạch). License MIT/Apache-2.0.
  - `pypdf`: thư viện trích text PDF phổ biến, thuần Python, BSD, không cần binary hệ thống → Docker image nhỏ.
  - `typer`: CLI có type hint, help tự sinh, phổ biến (MIT), cùng tác giả FastAPI.
  - `ruff`, `mypy`, `pytest`: bắt buộc theo `coding-standards.md`.
  - Không dùng Playwright (Trial) cho widget: AC8 chỉ yêu cầu kiểm `textContent`/không `innerHTML`, làm được
    bằng test tĩnh + TestClient; kiểm bằng trình duyệt thật nằm trong checklist G3 của CEO.

## Kiến trúc (sơ đồ / thành phần)

```
      ┌──────────── cli.py (typer) ─────────────┐   ┌────────── api.py (FastAPI) ───────────┐
      │ docqa ingest | ask | eval               │   │ POST /ingest /ask /chat · GET /health  │
      └───────────────────┬─────────────────────┘   │ GET / → static/index.html (+ CSP)      │
                          │                         └──────────────────┬─────────────────────┘
                          └───────────────┬────────────────────────────┘
                                   service.py (DocQAService) ──── chat.py (validate_history,
                   ┌───────────────────┼────────────────────────┐       retrieval_queries)
              ingest.py           retriever.py                 llm.py
       (load + chunk + store)   Retriever (Protocol)        AnswerModel (Protocol)
                   │            └─ FTS5Retriever            ├─ ClaudeAnswerModel → anthropic SDK
                   │                    │                   └─ FakeAnswerModel (test)
                   └──────── store.py (SQLite + FTS5) ──────┘
                                   eval.py (dùng service/retriever)
           config.py (Settings từ env) · models.py (dataclass) · errors.py
```

### Module trong `src/docqa/`

| Module | Trách nhiệm | API chính |
|---|---|---|
| `models.py` | Dataclass bất biến (`frozen=True`) | `Chunk`, `Citation`, `Answer`, `IngestReport`, `ChatTurn` (mới) |
| `errors.py` | Lỗi miền, thông điệp rõ cho người dùng | `DocQAError` ← `IngestError`, `ChatHistoryError` (mới), `AnswerError` ← `LLMAuthError`, `LLMRateLimitError`, `LLMUnavailableError`, `LLMRefusalError`, `LLMIncompleteError` (mới) |
| `config.py` | Đọc env một chỗ | `Settings.from_env() -> Settings` (thêm `chat_max_messages`, `chat_max_chars`) |
| `ingest.py` | Loader theo đuôi file + chunker + ghi store | `load_file(path) -> list[Page]`, `chunk_text(text, size=800, overlap=150) -> list[Span]`, `ingest_dir(store, root) -> IngestReport` |
| `store.py` | Schema SQLite, kết nối, CRUD | `Store(path)`, `Store.replace_document(...)`, `Store.chunk_count()` |
| `retriever.py` | Tìm kiếm | `class Retriever(Protocol): def search(self, query: str, k: int) -> list[Chunk]`; `FTS5Retriever(store, min_score)`; hằng `STOPWORDS`, hàm `content_tokens(text) -> list[str]` (dùng chung với `chat.py`) |
| `llm.py` | Sinh câu trả lời có trích dẫn | `class AnswerModel(Protocol): def answer(self, question: str, chunks: list[Chunk], history: Sequence[ChatTurn] = ()) -> Answer`; `ClaudeAnswerModel(client_factory, model, effort)`; `FakeAnswerModel` |
| `chat.py` | Logic chat thuần, không I/O | `validate_history(messages, max_messages, max_chars) -> None` (raise `ChatHistoryError`); `retrieval_queries(messages) -> list[str]` |
| `service.py` | Gộp luồng | `DocQAService(store, retriever, model_factory, settings)`: `.ingest(dir)`, `.ask(question, k)`, `.chat(messages, k)` |
| `api.py` | FastAPI app | `app`, dependency `get_service()` (override được trong test); `GET /` trả widget + header bảo mật |
| `static/index.html` | Widget chat mẫu (package data, đọc một lần bằng `importlib.resources.files("docqa")`) | — |
| `cli.py` | Typer app | `app` |
| `eval.py` | Đánh giá | `load_cases(path)`, `run_retrieval_eval(retriever, cases, k) -> EvalReport`, `run_full_eval(service, cases, k)` |

### Luồng `ask`

1. `chunks = retriever.search(question, k)` (đã lọc theo ngưỡng).
2. `chunks == []` → trả `Answer(text=NOT_FOUND_TEXT, citations=[], found=False)` — **model không được khởi tạo,
   không gọi API** (AC2). `NOT_FOUND_TEXT = "Not found in the provided documents."`
3. Ngược lại → `model.answer(question, chunks)`. `found = len(citations) > 0` (Claude nói không có trong tài
   liệu và không trích dẫn → `found=False`, giữ nguyên văn câu trả lời).

Client Anthropic được tạo **lười** (`model_factory`) chỉ khi cần gọi API → `ingest`, `eval --retrieval-only`
và nhánh not-found chạy được khi không có `ANTHROPIC_API_KEY`.

### Luồng `chat` (ADR 0004, 0005)

Input: `messages: list[ChatTurn]` (lịch sử đầy đủ do client gửi, lượt cuối là câu hỏi mới).

1. `validate_history(messages, settings.chat_max_messages, settings.chat_max_chars)` — vi phạm → raise
   `ChatHistoryError` (API trả **422**). Quy tắc (kiểm theo thứ tự, thông điệp nêu rõ quy tắc nào bị vi phạm):
   - `1 ≤ len(messages) ≤ chat_max_messages` (mặc định 20 = 10 lượt hỏi–đáp);
   - mỗi `content` sau `strip()` dài `1..chat_max_chars` ký tự (mặc định 2000, bằng giới hạn của `/ask`);
   - `role` xen kẽ, bắt đầu **và** kết thúc bằng `user` (API Claude yêu cầu message đầu là `user`; lượt cuối là
     câu hỏi cần trả lời).
   Pydantic chỉ kiểm hình dạng (`role ∈ {"user","assistant"}`, `content: str`, có trường `messages`); giới hạn
   cấu hình được kiểm trong `chat.py` để đọc từ env và test được không cần HTTP.
2. `queries = retrieval_queries(messages)` (thuần, tất định — ADR 0005):
   - `latest` = content lượt user cuối; `previous` = content lượt **user** ngay trước đó (bỏ qua lượt
     assistant), có thể không có.
   - Không có `previous` → `[latest]`.
   - `latest` chứa **từ tham chiếu** (token thuộc `REFERENCE_WORDS = {"it", "its", "this", "that", "these",
     "those", "they", "them", "their", "other", "another", "one", "ones", "same", "else", "former", "latter"}`)
     → `[latest + "\n" + previous]` (câu nối tiếp, phải dùng ngữ cảnh).
   - Ngược lại → `[latest, latest + "\n" + previous]` (thử câu độc lập trước; rỗng mới ghép ngữ cảnh).
   - `REFERENCE_WORDS ⊂ STOPWORDS` của retriever (test khẳng định) → các từ này không bao giờ tự khớp tài liệu.
3. Lần lượt `chunks = retriever.search(q, k)` cho từng `q`; dừng ở kết quả không rỗng đầu tiên.
4. `chunks == []` → `Answer(NOT_FOUND_TEXT, [], False)`, **model_factory không được gọi** (như AC2).
5. Ngược lại → `model.answer(latest, chunks, history=messages[:-1])`; `found = len(citations) > 0`.

Lý do chỉ dùng **một** câu hỏi user trước (không dùng câu trả lời assistant, không dùng cả lịch sử): giữ chủ đề
không trôi, nội dung assistant do client gửi lên (không đáng tin, dài, nhiều từ chung chung), và kết quả dễ dự
đoán/test. Giới hạn đã biết (ghi README): câu nối tiếp **không** có từ tham chiếu nhưng tự nó vẫn khớp tài liệu
(vd "And the price?" sau câu hỏi về gói Pro) được tìm như câu độc lập, có thể lấy nhầm mục khác; câu có từ tham
chiếu (vd "How much does it cost?") luôn được ghép ngữ cảnh. Viết lại truy vấn bằng LLM bị loại (ADR 0005).

### Retriever `FTS5Retriever`

- **Làm sạch truy vấn** (tránh lỗi cú pháp FTS5 và injection toán tử): tách token bằng regex `\w+` (Unicode),
  hạ chữ thường, bỏ stopword tiếng Anh (danh sách nhỏ cố định trong module, ~60 từ, **gồm toàn bộ
  `REFERENCE_WORDS`**), bỏ token < 2 ký tự, bọc mỗi token trong dấu nháy kép, nối bằng ` OR `. Không còn token →
  trả `[]`. Bước tách/lọc token là hàm công khai `content_tokens(text)` để `chat.py` dùng lại.
- SQL: `SELECT c.*, -bm25(chunks_fts) AS score FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid
  WHERE chunks_fts MATCH ? ORDER BY score DESC LIMIT ?` (FTS5 `bm25()` trả số âm, càng nhỏ càng khớp →
  đổi dấu để "lớn hơn = tốt hơn").
- **Ngưỡng**: giữ chunk có `score >= min_score` (`DOCQA_MIN_SCORE`, mặc định hiệu chỉnh ở T11 trên bộ mẫu
  sao cho hit@3 ≥ 0.8 và mọi câu "unanswerable" trong `eval.jsonl` ra `found=false`; giá trị ghi vào README).
- Tokenizer FTS5: `unicode61 remove_diacritics 2` (chịu được tiếng Việt không dấu/có dấu cơ bản).

### `ClaudeAnswerModel` (ràng buộc đã chốt — làm đúng nguyên văn)

Đã đối chiếu ngày 2026-10-25 với tài liệu skill `claude-api` (Python README: Error Handling, Multi-Turn, Stop
Reasons, Refusal Fallbacks; `shared/model-migration.md` mục Claude Opus 5 → New API features và Migrating to
Claude Opus 5.5; `shared/api-version-migration.md` mục 2026-10-21) và với SDK đã cài (`anthropic==2.3.0`):
`client.beta.messages.create` có tham số `fallbacks: Iterable[BetaFallbackParam] | Literal["default"]`, beta
`"server-side-fallback-2026-07-01"` có trong `AnthropicBetaParam`, **không còn** tham số `temperature`/`top_p`/
`top_k`, và SDK gửi `anthropic-version: 2026-10-21` mặc định. → Câu hỏi mở Q5 đã đóng: dùng được nguyên văn.

- `client = anthropic.Anthropic()` — SDK tự đọc `ANTHROPIC_API_KEY` từ môi trường; không hardcode, không log key.
- Model mặc định `claude-opus-5-5` (đúng chuỗi, không hậu tố ngày), đổi qua `DOCQA_MODEL`.
- **Effort luôn gửi tường minh**: `output_config={"effort": settings.effort}`, mặc định `low` (`DOCQA_EFFORT`).
  Lý do: trên Opus 5.5 thinking **luôn bật**, effort là núm điều khiển duy nhất; mặc định API là `medium` nếu
  bỏ trống — Q&A ngắn trên tài liệu cho sẵn dùng `low` để giảm độ trễ/chi phí.
- `max_tokens=8192` (hằng trong `llm.py`; trước là 4096): thinking tính vào `max_tokens` dù không trả text,
  nên cần dư cho cả thinking lẫn câu trả lời.
- Gọi:
  ```python
  client.beta.messages.create(
      model=settings.model,
      max_tokens=8192,
      betas=["server-side-fallback-2026-07-01"],
      fallbacks="default",
      output_config={"effort": settings.effort},
      system=SYSTEM_PROMPT,
      messages=[
          *({"role": t.role, "content": t.content} for t in history),  # rỗng với /ask
          {"role": "user", "content": [*document_blocks, {"type": "text", "text": question}]},
      ],
  )
  ```
  Dạng `fallbacks="default"` **phải** đi với header `server-side-fallback-2026-07-01` (dạng mảng dùng
  `-2026-06-01`; ghép chéo → 400). Fallback chỉ kích hoạt khi bị từ chối theo chính sách; rate limit/overload/5xx
  trả nguyên như cũ.
- **Cấm gửi**: `temperature`, `top_p`, `top_k` (API 2026-10-21 trả 400 với mọi giá trị), `thinking` (kể cả
  `{"type": "disabled"}` hay `budget_tokens` — 400 trên Opus 5.5), prefill assistant (lượt cuối luôn là `user`),
  `tool_choice`/`tools` (không dùng tool), `output_config.format` (structured outputs không dùng chung được với
  citations). Test T7/T15 khẳng định các khoá này vắng mặt.
- **Lịch sử chat** (ADR 0004): mỗi lượt cũ gửi đúng `{"role": ..., "content": "<chuỗi>"}` — **không** document
  block trong lượt `assistant`, **không** `citations` trên text của lượt `user` (cả hai trả 400 ở API
  2026-10-21). Document block **chỉ** có ở lượt user cuối. Lịch sử là text thuần do client gửi nên không có
  thinking block nào được replay → quy tắc "preserved thinking"/prefix binding của Opus 5.5 không áp dụng.
- Mỗi chunk → một document block, **tất cả** đều bật citations, đặt **trước** text block câu hỏi:
  `{"type": "document", "source": {"type": "text", "media_type": "text/plain", "data": chunk.text},
  "title": f"{chunk.source}#{chunk.id}", "citations": {"enabled": True}}`.
- `SYSTEM_PROMPT` (tiếng Anh, hằng cố định): chỉ trả lời dựa trên các document trong tin nhắn user cuối; các
  lượt trước chỉ là ngữ cảnh hội thoại, không phải nguồn sự thật; nếu tài liệu không có thông tin thì nói rõ là
  không tìm thấy trong tài liệu; ngắn gọn. Không có câu "hãy viết lập luận ra" (tránh `reasoning_extraction`).
- Đọc phản hồi (theo `type`, không theo vị trí — response có thể có block `thinking` rỗng và block `fallback`):
  1. Kiểm `response.stop_reason` **trước**. `"refusal"` → raise `LLMRefusalError(category)` với
     `category = response.stop_details.category if response.stop_details else None` (`stop_details` có thể
     `None`; chỉ rẽ nhánh theo `stop_reason`). `"refusal"` ở response cuối nghĩa là cả chuỗi fallback đều từ chối.
  2. Lặp `response.content`, chỉ đọc block `type == "text"`; nối `block.text` thành câu trả lời. Bỏ qua
     `thinking`, `fallback` và mọi loại block khác.
  3. `"max_tokens"`: có text → dùng, log cảnh báo; **không có text** → raise `LLMIncompleteError`.
  4. Block text có `citations`: mỗi phần tử `type == "char_location"` có `cited_text`, `document_index`,
     `document_title` → `Citation(source=chunks[document_index].source, quote=cited_text,
     chunk_id=chunks[document_index].id)`. Loại trùng theo `(chunk_id, quote)`. `document_index` ngoài phạm
     vi → bỏ qua + log cảnh báo.
  5. `response.model != settings.model` (được fallback phục vụ) → log INFO tên model; không đổi kết quả.
- Bắt lỗi theo thứ tự cụ thể → chung, đổi sang lỗi miền (không lộ key/nội dung nhạy cảm trong message):
  `anthropic.AuthenticationError`, `anthropic.PermissionDeniedError` → `LLMAuthError`;
  `anthropic.RateLimitError` → `LLMRateLimitError`; `anthropic.APIStatusError` (gồm 400/404/5xx/overloaded) →
  `LLMUnavailableError(status_code)` + log `request_id` nếu có; `anthropic.APIConnectionError` (gồm
  `APITimeoutError`) → `LLMUnavailableError()`. Giữ retry mặc định của SDK (2 lần), không tự viết retry.
- Không HTTP thô, không shim OpenAI.

### `FakeAnswerModel`

Ghi lại mọi lời gọi vào `self.calls: list[tuple[str, list[Chunk], tuple[ChatTurn, ...]]]`; trả `Answer` tất
định trích dẫn chunk đầu (`quote` = 60 ký tự đầu). Dùng trong test để chứng minh AC2 (`fake.calls == []`), AC8
(lịch sử được chuyển đúng) và test API/CLI.

## Data model

### Dataclass (`models.py`)

```python
@dataclass(frozen=True)
class Chunk:
    id: int            # chunks.id
    source: str        # đường dẫn tương đối so với thư mục ingest, vd "pricing.md"
    chunk_index: int   # thứ tự trong file
    start_char: int    # vị trí trong văn bản đã trích (theo trang với PDF)
    end_char: int
    page: int | None   # số trang (1-based) với PDF, None với md/txt
    text: str
    score: float = 0.0 # -bm25, lớn hơn = khớp hơn

@dataclass(frozen=True)
class Citation:
    source: str
    quote: str
    chunk_id: int

@dataclass(frozen=True)
class Answer:
    text: str
    citations: list[Citation]
    found: bool

@dataclass(frozen=True)
class IngestReport:
    documents: int
    chunks: int
    skipped: list[str]  # file lỗi/rỗng/không hỗ trợ, kèm lý do ngắn

@dataclass(frozen=True)
class ChatTurn:              # mới (chat)
    role: Literal["user", "assistant"]
    content: str
```

Chat không có bảng SQLite nào: server không lưu phiên (out of scope).

### SQLite (`store.py`, một file, mặc định `./docqa.db`, đổi qua `DOCQA_DB`)

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY,
    source      TEXT NOT NULL UNIQUE,      -- đường dẫn tương đối
    sha256      TEXT NOT NULL,             -- bỏ qua nếu không đổi khi ingest lại
    ingested_at TEXT NOT NULL              -- ISO-8601 UTC
);

CREATE TABLE IF NOT EXISTS chunks (
    id          INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    start_char  INTEGER NOT NULL,
    end_char    INTEGER NOT NULL,
    page        INTEGER,
    text        TEXT NOT NULL,
    UNIQUE (document_id, chunk_index)
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, content='chunks', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

-- Trigger đồng bộ external-content FTS5
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
```

- Ingest lại cùng `source`: cùng `sha256` → bỏ qua; khác → xoá document (cascade chunks, trigger dọn FTS) rồi
  chèn lại, trong **một transaction**. File đã biến mất khỏi thư mục không bị xoá ở v0.1 (ghi trong README).
- Chunker: cửa sổ 800 ký tự, bước 650 (chồng 150); nếu được thì lùi điểm cắt về khoảng trắng gần nhất trong
  100 ký tự cuối để không cắt giữa từ; bỏ chunk rỗng/chỉ khoảng trắng. Chuẩn hoá xuống dòng `\r\n` → `\n`.
- PDF: `pypdf.PdfReader`, chunk **từng trang** (lưu `page`); trang không có text (PDF scan) → bỏ qua, ghi vào
  `skipped` nếu cả file rỗng ("no extractable text — OCR not supported").
- Đọc text với UTF-8 (`errors="replace"`); bỏ qua file ẩn và đuôi không hỗ trợ; duyệt đệ quy, thứ tự sắp xếp
  tất định.

## API / giao diện

### Cấu hình (biến môi trường — ghi đủ trong `.env.example` và README)

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Chỉ cần cho `ask`/`chat` có bằng chứng và `eval` đầy đủ. SDK tự đọc. |
| `DOCQA_MODEL` | `claude-opus-5-5` | Model Claude |
| `DOCQA_EFFORT` | `low` | `output_config.effort` (`low`/`medium`/`high`/`xhigh`/`max`; API mặc định `medium` nếu bỏ trống — ta luôn gửi) |
| `DOCQA_DB` | `./docqa.db` | File SQLite |
| `DOCQA_TOP_K` | `5` | Số chunk đưa vào LLM |
| `DOCQA_MIN_SCORE` | hiệu chỉnh ở T11 | Ngưỡng `-bm25` để coi là có bằng chứng |
| `DOCQA_INGEST_ROOT` | thư mục làm việc | API chỉ cho ingest thư mục **bên trong** gốc này |
| `DOCQA_CHAT_MAX_MESSAGES` | `20` | Số message tối đa trong một request `/chat` (≥ 1, số nguyên) |
| `DOCQA_CHAT_MAX_CHARS` | `2000` | Độ dài tối đa mỗi message `/chat` (ký tự, sau `strip()`) |

Không đọc `.env` tự động bằng thư viện (không thêm `python-dotenv`, Q3); README hướng dẫn `export`/`--env-file`
của Docker.

### CLI (`docqa`)

| Lệnh | Hành vi | Exit code |
|---|---|---|
| `docqa ingest <dir> [--db PATH]` | In `Ingested N documents, M chunks; skipped: ...` | 0; 1 nếu dir không tồn tại |
| `docqa ask "<question>" [--k N] [--db PATH] [--json]` | In câu trả lời + danh sách `[n] source — "quote"`; `--json` in đúng schema của `/ask` | 0 (cả khi not found); 2 khi lỗi LLM (thông điệp rõ ra stderr, vd "ANTHROPIC_API_KEY is missing or invalid") |
| `docqa eval <file.jsonl> [--retrieval-only] [--k 3] [--db PATH]` | In `hit@k`, số case; chế độ đầy đủ in thêm `citation_rate`, `not_found_accuracy` | 0; 1 nếu file sai định dạng |

Không có lệnh CLI cho chat (scope chỉ yêu cầu `POST /chat` + widget).

### HTTP API (FastAPI, chạy `uvicorn docqa.api:app`)

| Endpoint | Request | Response 200 | Lỗi |
|---|---|---|---|
| `GET /health` | — | `{"status": "ok"}` | — |
| `GET /` | — | Widget HTML (`text/html; charset=utf-8`) + header bảo mật (xem Widget) | — |
| `POST /ingest` | `{"path": "examples/docs"}` | `{"documents": int, "chunks": int, "skipped": [str]}` | 400 path ngoài `DOCQA_INGEST_ROOT` hoặc không tồn tại |
| `POST /ask` | `{"question": str (1..2000 ký tự), "k": int (1..20, tuỳ chọn)}` | `{"answer": str, "citations": [{"source": str, "quote": str}], "found": bool}` | 422 validate; 429 `LLMRateLimitError`; 502 `LLMAuthError`/`LLMUnavailableError`/`LLMRefusalError`/`LLMIncompleteError` với `{"detail": {"code": "...", "message": "..."}}` |
| `POST /chat` | `{"messages": [{"role": "user"\|"assistant", "content": str}], "k": int (1..20, tuỳ chọn)}` | **Cùng schema** với `/ask`: `{"answer", "citations": [{"source", "quote"}], "found"}` | 422 hình dạng sai (pydantic) **hoặc** vi phạm `validate_history` → `{"detail": {"code": "chat_history_invalid", "message": "..."}}`; 429/502 như `/ask` |

Request/response là model pydantic (đi kèm FastAPI); model request đặt `extra="forbid"`. Service lấy qua
`Depends(get_service)` để test override bằng `FakeAnswerModel` + DB tạm. Ví dụ `/chat`:

```json
{"messages": [
  {"role": "user", "content": "What does the Starter plan include?"},
  {"role": "assistant", "content": "The Starter plan includes ..."},
  {"role": "user", "content": "And what about the other one?"}
]}
```

Client tự giữ lịch sử và gửi lại câu trả lời assistant dạng **text thuần** (không gửi citations). Không bật CORS
(widget cùng origin). Không có rate limit/auth (không deploy — out of scope; ghi README).

### Widget (`src/docqa/static/index.html`, ADR 0006)

- **Một file** HTML có `<style>` và `<script>` inline duy nhất mỗi loại; không framework, không CDN, không font/
  ảnh ngoài, không thuộc tính `on*=` inline (gắn sự kiện bằng `addEventListener`).
- Hành vi: form nhập câu hỏi → đẩy `{role: "user", content}` vào mảng `messages` trong bộ nhớ trang →
  `fetch("/chat", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({messages})})`
  → hiển thị `answer`; dưới mỗi câu trả lời là danh sách trích dẫn `source — "quote"`; `found=false` hiển thị kiểu
  "not found". Câu trả lời được đẩy lại vào `messages` dạng `{role: "assistant", content: answer}`. Client chỉ giữ
  **20** message gần nhất (cắt cặp cũ nhất, đảm bảo message đầu vẫn là `user`); lỗi 4xx/5xx hiển thị
  `detail.message` (hoặc thông điệp chung). Nút gửi bị khoá khi đang chờ. Làm mới trang = phiên mới.
- **An toàn DOM**: mọi dữ liệu từ API/người dùng ghi bằng `document.createElement` + `textContent`; **cấm**
  `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `new Function`, `setTimeout(string)`.
- **Phục vụ**: `api.py` đọc file một lần lúc import qua `importlib.resources.files("docqa").joinpath("static/index.html")`,
  tính `sha256` (base64) của nội dung `<script>` và `<style>` inline, trả `HTMLResponse` với header:
  - `Content-Security-Policy: default-src 'none'; script-src 'sha256-<S>'; style-src 'sha256-<C>'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'`
    (không `'unsafe-inline'`, không `'unsafe-eval'`);
  - `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`.
- File là package data của wheel (hatchling gồm mọi file trong `src/docqa/`); Docker image có sẵn.
- README có mục "Embedding the widget": copy file / đặt sau cùng origin với API; nhúng khác origin cần bật CORS và
  nới `frame-ancestors` — không làm ở v0.1.

### Định dạng `examples/eval.jsonl`

Mỗi dòng: `{"question": str, "expected_sources": [str], "answerable": bool}`.
`hit@k` = tỉ lệ case `answerable=true` có ít nhất một chunk trong top-k với `source ∈ expected_sources`.
Bộ mẫu: ≥ 10 câu answerable + ≥ 3 câu unanswerable (thực tế 18 + 4), viết trên `examples/docs/` (10 file tự
viết, công khai được, chủ đề hư cấu "Kaikeel Handbook Lite": 6 `.md`, 3 `.txt`, 1 `.pdf` 2 trang sinh bằng
`scripts/make_sample_pdf.py`). PDF còn được phủ bằng fixture nhỏ trong `tests/fixtures/`. Tài liệu mẫu có **hai
mục cùng loại nằm ở hai file khác nhau**: gói hỗ trợ Starter (`support-plan-starter.md`) và Pro
(`support-plan-pro.txt`) để dựng kịch bản câu nối tiếp cho AC8.
(BUILD T5: tăng từ 3–5 lên 10 file theo chỉ đạo khi giao BUILD — 6–10 file gồm 1 PDF — để eval có ý nghĩa hơn.)

## Kế hoạch test (map với tiêu chí nghiệm thu)

Công cụ: `pytest` + `pytest-cov`, `fastapi.testclient`, `typer.testing.CliRunner`. Mọi test dùng DB SQLite
trong `tmp_path`. `tests/conftest.py` có fixture `autouse` xoá `ANTHROPIC_API_KEY` và monkeypatch
`anthropic.Anthropic` để **raise nếu bị khởi tạo** → test nào vô tình gọi API thật sẽ đỏ.
Ngưỡng: `--cov=docqa --cov-fail-under=80` (cấu hình trong `pyproject.toml`).

Theo Q1 (PROJECT.md): agent **không** gọi API thật. Mọi kiểm chứng của agent là tự động/offline; các bước cần key
gom vào **checklist G3 cho CEO** (TASKS.md, mục "Checklist G3 — CEO tự chạy").

| AC | Kiểm chứng tự động (CI, agent) | Checklist G3 (CEO, key của CEO) |
|---|---|---|
| AC1 | `test_service.py::test_ask_returns_citation_from_expected_file` (ingest `examples/docs` + `FakeAnswerModel`, citation `source` đúng file); `test_llm.py` dựng response giả đủ dạng (block `thinking` rỗng + `fallback` + text có `citations` `char_location`) → `Citation.source` map đúng qua `document_index`; khẳng định request có document block bật citations đặt trước câu hỏi, model/`max_tokens`/betas/fallbacks/output_config đúng, không có khoá cấm. | Mục 2: `docqa ingest examples/docs && docqa ask "<câu trong bộ mẫu>"` → ≥ 1 trích dẫn đúng file. |
| AC2 | `test_service.py::test_not_found_does_not_call_model` (câu hỏi ngoài tài liệu → `found=False`, `NOT_FOUND_TEXT`, `fake.calls == []`, `model_factory` không được gọi); `test_retriever.py` (truy vấn chỉ có stopword/ký tự đặc biệt → `[]`; dưới ngưỡng → `[]`; không lỗi cú pháp FTS5 với `"`, `*`, `NEAR`, `AND`). | — |
| AC3 | `test_api.py`: `GET /health` → 200 `{"status":"ok"}`; `POST /ask` → đúng schema cả nhánh found và not found; `POST /ingest` ngoài root → 400; `LLMRateLimitError` → 429, `LLMAuthError`/`LLMRefusalError`/`LLMIncompleteError` → 502. | — |
| AC4 | `test_eval.py::test_sample_hit_at_3` (ingest `examples/docs`, `run_retrieval_eval(k=3) >= 0.8`, không key); `test_cli.py::test_eval_retrieval_only`; CI chạy thật `uv run docqa eval examples/eval.jsonl --retrieval-only --k 3`. | — |
| AC5 | CI: `ruff check`, `ruff format --check`, `mypy src` (strict), `pytest --cov-fail-under=80`; env `ANTHROPIC_API_KEY=""`; fixture chặn khởi tạo client. | — |
| AC6 | CI job `docker build`; T13 (agent): clone sạch → làm theo README phần không cần key (uv sync, ingest, eval, pytest, docker build/run, `curl /health`, `curl /`), bấm giờ. | Mục 1–4: bấm giờ từ clone tới câu trả lời đầu tiên ≤ 10 phút (uv) + lối Docker. |
| AC7 | `test_config.py`: không có giá trị mặc định cho key; `ClaudeAnswerModel` không nhận key qua tham số; log không chứa key (caplog). | Security gate của `sec-devops` (gitleaks, review) → `SECURITY_REPORT.md` PASS. |
| AC8 | `test_chat.py`: `retrieval_queries` (1 lượt → `[latest]`; có từ tham chiếu → `[latest+previous]`; câu độc lập → `[latest, latest+previous]`; chỉ dùng user ngay trước, bỏ qua assistant; `REFERENCE_WORDS ⊂ STOPWORDS`); `validate_history` (vượt `max_messages`, content rỗng/vượt `max_chars`, bắt đầu/kết thúc bằng assistant, hai user liên tiếp → `ChatHistoryError`). `test_service.py` trên `examples/docs`, 2 kịch bản của T5: (a) `test_chat_followup_same_item` — q1 về mục X (file A), follow-up "How much does it cost?" → `service.chat([q1, a1, followup])` trả citation từ file A và `fake.calls[0]` nhận `history == (q1, a1)`; (b) `test_chat_followup_other_item` — follow-up "And what about the other one?" một mình → retriever `[]`, qua `service.chat` → chunk đưa vào model gồm cả file A và file B; `test_chat_not_found_does_not_call_model`. `test_llm.py::test_chat_request_shape`: lượt cũ là `{"role", "content": str}`, document block chỉ ở lượt user cuối, không `citations`/document trong lượt cũ. `test_api.py`: `POST /chat` đúng schema cả 2 nhánh; số message > `DOCQA_CHAT_MAX_MESSAGES` → 422; message > `DOCQA_CHAT_MAX_CHARS` → 422; kết thúc bằng assistant → 422; role lạ/thiếu trường → 422. `test_widget.py`: `GET /` 200 `text/html`; CSP không có `unsafe-inline`/`unsafe-eval`, chứa đúng hash sha256 của script/style inline, `connect-src 'self'`; file không chứa `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval(`, `new Function`, thuộc tính `on*=`, URL `http(s)://` trong `src`/`href`; có `textContent` và `fetch("/chat"`; mọi id dùng trong `getElementById` tồn tại trong HTML (parse bằng `html.parser` chuẩn). | Mục 3: mở `http://localhost:8000/`, hỏi 2 lượt (câu thứ hai "And what about the other one?") → Claude trả lời về đúng mục còn lại, trích dẫn file B hiển thị dưới câu trả lời. |

Test đơn vị khác: `test_ingest.py` (chunk size/overlap/biên khoảng trắng, md/txt/pdf, file rỗng, đuôi không hỗ
trợ, ingest lại idempotent, đổi nội dung → thay chunk, FTS đồng bộ sau xoá), `test_store.py` (schema, có FTS5),
`test_config.py` (đọc `DOCQA_CHAT_*`, giá trị không hợp lệ → `DocQAError`).

## Triển khai

- **Local**: `uv sync` → `uv run docqa ingest examples/docs` → `export ANTHROPIC_API_KEY=...` →
  `uv run docqa ask "..."`; API + widget: `uv run uvicorn docqa.api:app --port 8000` rồi mở
  `http://localhost:8000/`.
- **Docker**: `Dockerfile` một stage trên `python:3.12-slim`, copy binary `uv` từ image chính thức
  `ghcr.io/astral-sh/uv` (pin tag `0.6.3`), `uv sync --frozen --no-dev`, chạy user không phải root, `EXPOSE 8000`,
  `CMD ["uvicorn", "docqa.api:app", "--host", "0.0.0.0", "--port", "8000"]`. `examples/` được copy vào image
  để demo; DB ở `/data/docqa.db` (`DOCQA_DB`), mount volume để giữ. Key truyền bằng `--env-file .env` hoặc
  `-e ANTHROPIC_API_KEY`, không bake vào image. `.dockerignore` loại `.env`, `.venv`, `*.db`, `.git`.
- **CI** (`.github/workflows/ci.yml`): GitHub Actions, `astral-sh/setup-uv` ghim `version: "0.6.3"`,
  `uv sync --locked`, lint/format/type/test + eval retrieval-only; job build Docker chạy khi có `Dockerfile`.
  Không secret, không gọi API.
- **Release**: sau QA + Security gate PASS → `CHANGELOG.md` mục `[0.1.0]`, tag `v0.1.0`. Push lên repo private
  `kaikeel/docqa` theo Q4; public repo cần CEO duyệt (Milestone 2).
- Không deploy production (out of scope).
