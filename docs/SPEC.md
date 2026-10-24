# Technical spec — PF-20261025-docqa (Kaikeel DocQA) v0.1.0

Tác giả: sol-architect · Ngày: 2026-10-25 · Trạng thái: SHAPE · Scope gốc: `PROJECT.md` (AC1–AC7)

## Tóm tắt giải pháp

Một package Python nhỏ (`docqa`) chạy local, không cần dịch vụ ngoài ngoài Claude API:

1. **Ingest**: đọc `.md`/`.txt`/`.pdf` trong một thư mục → tách chunk ~800 ký tự, chồng lấn ~150 →
   lưu vào **một file SQLite** (bảng `chunks` + bảng ảo FTS5 `chunks_fts`).
2. **Retrieve**: BM25 bằng hàm `bm25()` của SQLite FTS5, sau một interface `Retriever` (thay bằng vector
   search sau này mà không đụng service). Có **ngưỡng điểm**: không chunk nào vượt ngưỡng → `found=false`,
   **không gọi LLM** (ADR 0002).
3. **Answer**: gửi các chunk cho Claude dưới dạng `document` block văn bản thuần, bật `citations` — trích dẫn
   do API trả về (đoạn trích nguyên văn + chỉ số document), ta chỉ map về file nguồn, không tự parse (ADR 0003).
4. **Giao diện**: CLI (`docqa ingest|ask|eval`) và API FastAPI (`POST /ingest`, `POST /ask`, `GET /health`).
5. **Eval**: `docqa eval examples/eval.jsonl --retrieval-only` đo hit@k không cần API key; chế độ đầy đủ
   (có key) đo thêm tỉ lệ câu trả lời có trích dẫn.

Không có web UI, không vector DB/embeddings, không auth, không OCR, không deploy (xem Out of scope).

### Ràng buộc kỹ thuật đã chốt

- **Python 3.12** (`/opt/homebrew/bin/python3.12`), quản lý bằng **uv** (`/opt/homebrew/bin/uv`), có `uv.lock` commit.
- Package `docqa`, layout `src/docqa/`, CLI entry point `docqa` (`[project.scripts] docqa = "docqa.cli:app"`).
- Phụ thuộc runtime tối thiểu, pin chính xác trong `pyproject.toml` (giá trị dưới là bản mới nhất trên PyPI
  ngày 2026-10-25; T1 xác nhận resolve được, nếu phải hạ bản thì ghi lý do trong commit):

  | Gói | Pin | Vai trò | Vòng tech-radar |
  |---|---|---|---|
  | `anthropic` | `==2.3.0` | Gọi Claude (SDK chính thức) | Adopt |
  | `fastapi` | `==0.162.0` | HTTP API | Adopt |
  | `uvicorn` | `==0.54.0` | ASGI server | (đi kèm FastAPI) |
  | `pypdf` | `==6.21.2` | Trích text PDF (BSD, thuần Python) | ngoài radar — xem dưới |
  | `typer` | `==0.27.3` | CLI | ngoài radar — xem dưới |

  Dev: `ruff==0.17.2`, `mypy==2.4.0`, `pytest==9.1.1`, `pytest-cov==7.1.0`, `httpx==0.28.1` (cho
  `fastapi.testclient`). `sqlite3` là thư viện chuẩn (SQLite = Adopt); FTS5 có sẵn trong bản SQLite của
  CPython chính thức/Homebrew/`python:3.12-slim` — T4 có test kiểm `fts5` khả dụng.

- **Lý do dùng công cụ ngoài vòng Adopt/Trial**:
  - `uv`: công cụ quản lý môi trường/lock (không phải phụ thuộc runtime); nhanh, lock tái lập được, giúp đạt
    AC6 (≤ 10 phút từ máy sạch). License MIT/Apache-2.0.
  - `pypdf`: thư viện trích text PDF phổ biến, thuần Python, BSD, không cần binary hệ thống → Docker image nhỏ.
  - `typer`: CLI có type hint, help tự sinh, phổ biến (MIT), cùng tác giả FastAPI. Gọn hơn argparse cho 3 lệnh
    có option; nếu T9 thấy argparse gọn hơn thì được đổi (không đổi giao diện lệnh).
  - `ruff`, `mypy`, `pytest`: bắt buộc theo `coding-standards.md`.

## Kiến trúc (sơ đồ / thành phần)

```
            ┌──────────── cli.py (typer) ─────────────┐   ┌──── api.py (FastAPI) ────┐
            │ docqa ingest | ask | eval               │   │ POST /ingest /ask, GET /health │
            └───────────────────┬─────────────────────┘   └──────────────┬─────────────┘
                                └──────────────┬───────────────────────────┘
                                         service.py (DocQAService)
                         ┌───────────────────┼────────────────────────┐
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
| `models.py` | Dataclass bất biến (`frozen=True`) | `Chunk`, `Citation`, `Answer`, `IngestReport` |
| `errors.py` | Lỗi miền, thông điệp rõ cho người dùng | `DocQAError` ← `IngestError`, `AnswerError` ← `LLMAuthError`, `LLMRateLimitError`, `LLMUnavailableError`, `LLMRefusalError` |
| `config.py` | Đọc env một chỗ | `Settings.from_env() -> Settings` |
| `ingest.py` | Loader theo đuôi file + chunker + ghi store | `load_file(path) -> list[Page]`, `chunk_text(text, size=800, overlap=150) -> list[Span]`, `ingest_dir(store, root) -> IngestReport` |
| `store.py` | Schema SQLite, kết nối, CRUD | `Store(path)`, `Store.replace_document(...)`, `Store.chunk_count()` |
| `retriever.py` | Tìm kiếm | `class Retriever(Protocol): def search(self, query: str, k: int) -> list[Chunk]`; `FTS5Retriever(store, min_score)` |
| `llm.py` | Sinh câu trả lời có trích dẫn | `class AnswerModel(Protocol): def answer(self, question: str, chunks: list[Chunk]) -> Answer`; `ClaudeAnswerModel(client_factory, model, effort)`; `FakeAnswerModel` |
| `service.py` | Gộp luồng | `DocQAService(store, retriever, model_factory)`: `.ingest(dir)`, `.ask(question, k)` |
| `api.py` | FastAPI app | `app`, dependency `get_service()` (override được trong test) |
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

### Retriever `FTS5Retriever`

- **Làm sạch truy vấn** (tránh lỗi cú pháp FTS5 và injection toán tử): tách token bằng regex `\w+` (Unicode),
  hạ chữ thường, bỏ stopword tiếng Anh (danh sách nhỏ cố định trong module, ~40 từ), bỏ token < 2 ký tự,
  bọc mỗi token trong dấu nháy kép, nối bằng ` OR `. Không còn token → trả `[]`.
- SQL: `SELECT c.*, -bm25(chunks_fts) AS score FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid
  WHERE chunks_fts MATCH ? ORDER BY score DESC LIMIT ?` (FTS5 `bm25()` trả số âm, càng nhỏ càng khớp →
  đổi dấu để "lớn hơn = tốt hơn").
- **Ngưỡng**: giữ chunk có `score >= min_score` (`DOCQA_MIN_SCORE`, mặc định hiệu chỉnh ở T11 trên bộ mẫu
  sao cho hit@3 ≥ 0.8 và mọi câu "unanswerable" trong `eval.jsonl` ra `found=false`; giá trị ghi vào README).
- Tokenizer FTS5: `unicode61 remove_diacritics 2` (chịu được tiếng Việt không dấu/có dấu cơ bản).

### `ClaudeAnswerModel` (ràng buộc đã chốt — làm đúng nguyên văn)

- `client = anthropic.Anthropic()` — đọc `ANTHROPIC_API_KEY` từ môi trường; không hardcode, không log key.
- Model mặc định `claude-opus-5-5` (đúng chuỗi, không hậu tố ngày), đổi qua `DOCQA_MODEL`.
  Effort `output_config={"effort": "low"}`, đổi qua `DOCQA_EFFORT` (mặc định `low`).
- Gọi:
  ```python
  client.beta.messages.create(
      model=settings.model,
      max_tokens=4096,
      betas=["server-side-fallback-2026-07-01"],
      fallbacks="default",
      output_config={"effort": settings.effort},
      system=SYSTEM_PROMPT,
      messages=[{"role": "user", "content": [*document_blocks, {"type": "text", "text": question}]}],
  )
  ```
- **Cấm gửi**: `temperature`, `top_p`, `top_k`, `thinking` (kể cả `{"type": "disabled"}`), `budget_tokens`,
  prefill assistant, `output_config.format` (structured outputs không dùng chung được với citations).
  Test T7 khẳng định các khoá này vắng mặt trong request.
- Mỗi chunk → một document block, **tất cả** đều bật citations, đặt **trước** text block câu hỏi:
  `{"type": "document", "source": {"type": "text", "media_type": "text/plain", "data": chunk.text},
  "title": f"{chunk.source}#{chunk.id}", "citations": {"enabled": True}}`.
- `SYSTEM_PROMPT` (tiếng Anh): chỉ trả lời dựa trên các document được cung cấp; nếu không có thông tin thì
  nói rõ là không tìm thấy trong tài liệu; ngắn gọn.
- Đọc phản hồi:
  1. Kiểm `response.stop_reason` **trước**. `"refusal"` → raise `LLMRefusalError` (kèm
     `response.stop_details.category` nếu có). `"max_tokens"` → vẫn dùng text, log cảnh báo.
  2. Lặp `response.content`, chỉ đọc block `type == "text"`; nối `block.text` thành câu trả lời.
  3. Block có `citations`: mỗi phần tử `type == "char_location"` có `cited_text`, `document_index`,
     `document_title` → `Citation(source=chunks[document_index].source, quote=cited_text,
     chunk_id=chunks[document_index].id)`. Loại trùng theo `(chunk_id, quote)`. `document_index` ngoài phạm
     vi → bỏ qua + log cảnh báo.
- Bắt lỗi theo thứ tự cụ thể → chung, đổi sang lỗi miền (không lộ key/nội dung nhạy cảm trong message):
  `anthropic.AuthenticationError` → `LLMAuthError`; `anthropic.RateLimitError` → `LLMRateLimitError`;
  `anthropic.APIStatusError` → `LLMUnavailableError` (kèm status code); `anthropic.APIConnectionError` →
  `LLMUnavailableError`.
- Không HTTP thô, không shim OpenAI.

### `FakeAnswerModel`

Ghi lại mọi lời gọi vào `self.calls: list[tuple[str, list[Chunk]]]`; trả `Answer` tất định trích dẫn chunk đầu
(`quote` = 60 ký tự đầu). Dùng trong test để chứng minh AC2 (`fake.calls == []`) và test API/CLI.

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
```

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
| `ANTHROPIC_API_KEY` | — | Chỉ cần cho `ask` có bằng chứng và `eval` đầy đủ. SDK tự đọc. |
| `DOCQA_MODEL` | `claude-opus-5-5` | Model Claude |
| `DOCQA_EFFORT` | `low` | `output_config.effort` |
| `DOCQA_DB` | `./docqa.db` | File SQLite |
| `DOCQA_TOP_K` | `5` | Số chunk đưa vào LLM |
| `DOCQA_MIN_SCORE` | hiệu chỉnh ở T11 | Ngưỡng `-bm25` để coi là có bằng chứng |
| `DOCQA_INGEST_ROOT` | thư mục làm việc | API chỉ cho ingest thư mục **bên trong** gốc này |

Không đọc `.env` tự động bằng thư viện (không thêm `python-dotenv`); README hướng dẫn `export`/`--env-file`
của Docker. (Nếu muốn tự load `.env` → câu hỏi mở Q3.)

### CLI (`docqa`)

| Lệnh | Hành vi | Exit code |
|---|---|---|
| `docqa ingest <dir> [--db PATH]` | In `Ingested N documents, M chunks; skipped: ...` | 0; 1 nếu dir không tồn tại |
| `docqa ask "<question>" [--k N] [--db PATH] [--json]` | In câu trả lời + danh sách `[n] source — "quote"`; `--json` in đúng schema của `/ask` | 0 (cả khi not found); 2 khi lỗi LLM (thông điệp rõ ra stderr, vd "ANTHROPIC_API_KEY is missing or invalid") |
| `docqa eval <file.jsonl> [--retrieval-only] [--k 3] [--db PATH]` | In `hit@k`, số case; chế độ đầy đủ in thêm `citation_rate`, `not_found_accuracy` | 0; 1 nếu file sai định dạng |

### HTTP API (FastAPI, chạy `uvicorn docqa.api:app`)

| Endpoint | Request | Response 200 | Lỗi |
|---|---|---|---|
| `GET /health` | — | `{"status": "ok"}` | — |
| `POST /ingest` | `{"path": "examples/docs"}` | `{"documents": int, "chunks": int, "skipped": [str]}` | 400 path ngoài `DOCQA_INGEST_ROOT` hoặc không tồn tại |
| `POST /ask` | `{"question": str (1..2000 ký tự), "k": int (1..20, tuỳ chọn)}` | `{"answer": str, "citations": [{"source": str, "quote": str}], "found": bool}` | 422 validate; 429 `LLMRateLimitError`; 502 `LLMAuthError`/`LLMUnavailableError`/`LLMRefusalError` với `{"detail": {"code": "...", "message": "..."}}` |

Request/response là model pydantic (đi kèm FastAPI). Service lấy qua `Depends(get_service)` để test override bằng
`FakeAnswerModel` + DB tạm.

### Định dạng `examples/eval.jsonl`

Mỗi dòng: `{"question": str, "expected_sources": [str], "answerable": bool}`.
`hit@k` = tỉ lệ case `answerable=true` có ít nhất một chunk trong top-k với `source ∈ expected_sources`.
Bộ mẫu: ≥ 10 câu answerable + ≥ 3 câu unanswerable, viết trên `examples/docs/` (3–5 file tự viết, công khai
được, chủ đề hư cấu "Kaikeel handbook" — có ít nhất một `.md` và một `.txt`). PDF được phủ bằng fixture nhỏ
trong `tests/fixtures/`.

## Kế hoạch test (map với tiêu chí nghiệm thu)

Công cụ: `pytest` + `pytest-cov`, `fastapi.testclient`, `typer.testing.CliRunner`. Mọi test dùng DB SQLite
trong `tmp_path`. `tests/conftest.py` có fixture `autouse` xoá `ANTHROPIC_API_KEY` và monkeypatch
`anthropic.Anthropic` để **raise nếu bị khởi tạo** → test nào vô tình gọi API thật sẽ đỏ.
Ngưỡng: `--cov=docqa --cov-fail-under=80` (cấu hình trong `pyproject.toml`).

| AC | Kiểm chứng tự động (CI) | Kiểm chứng thủ công |
|---|---|---|
| AC1 | `test_service.py::test_ask_returns_citation_from_expected_file` (ingest `examples/docs` + `FakeAnswerModel`, citation `source` đúng file); `test_llm.py` dựng response giả đủ dạng (text block + `citations` `char_location`) → `Citation.source` map đúng qua `document_index`; khẳng định request có document block bật citations đặt trước câu hỏi, model/betas/fallbacks/output_config đúng, không có `temperature`/`top_p`/`top_k`/`thinking`. | T13: `docqa ingest examples/docs && docqa ask "<câu trong bộ mẫu>"` với key thật → ≥ 1 trích dẫn đúng file; dán output vào PR. |
| AC2 | `test_service.py::test_not_found_does_not_call_model` (câu hỏi ngoài tài liệu → `found=False`, `NOT_FOUND_TEXT`, `fake.calls == []`, `model_factory` không được gọi); `test_retriever.py` (truy vấn chỉ có stopword/ký tự đặc biệt → `[]`; dưới ngưỡng → `[]`; không lỗi cú pháp FTS5 với `"`, `*`, `NEAR`, `AND`). | — |
| AC3 | `test_api.py`: `GET /health` → 200 `{"status":"ok"}`; `POST /ask` → đúng schema `{answer, citations[{source, quote}], found}` cả nhánh found và not found; `POST /ingest` ngoài root → 400; lỗi `LLMRateLimitError` → 429, `LLMAuthError` → 502. | — |
| AC4 | `test_eval.py::test_sample_hit_at_3` (ingest `examples/docs`, `run_retrieval_eval(k=3) >= 0.8`, không key); `test_cli.py::test_eval_retrieval_only` (CliRunner, in `hit@3`); CI có thêm bước chạy thật `uv run docqa eval examples/eval.jsonl --retrieval-only --k 3`. | — |
| AC5 | CI: `ruff check`, `ruff format --check`, `mypy src` (strict), `pytest --cov-fail-under=80`; env `ANTHROPIC_API_KEY=""`; fixture chặn khởi tạo client. | — |
| AC6 | CI job `docker build` (khi đã có Dockerfile). | T12/T13: làm theo README trên thư mục clone sạch (`git clone` vào thư mục tạm, `uv sync`, ingest, ask) + lối Docker; bấm giờ ≤ 10 phút; ghi kết quả vào PR. |
| AC7 | `test_config.py`: không có giá trị mặc định cho key; `ClaudeAnswerModel` không nhận key qua tham số; log không chứa key (caplog). | Security gate của `sec-devops` (gitleaks, review) → `SECURITY_REPORT.md` PASS. |

Test đơn vị khác: `test_ingest.py` (chunk size/overlap/biên khoảng trắng, md/txt/pdf, file rỗng, đuôi không hỗ
trợ, ingest lại idempotent, đổi nội dung → thay chunk, FTS đồng bộ sau xoá), `test_store.py` (schema, có FTS5).

## Triển khai

- **Local**: `uv sync` → `uv run docqa ingest examples/docs` → `export ANTHROPIC_API_KEY=...` →
  `uv run docqa ask "..."`; API: `uv run uvicorn docqa.api:app --port 8000`.
- **Docker**: `Dockerfile` một stage trên `python:3.12-slim`, copy binary `uv` từ image chính thức
  `ghcr.io/astral-sh/uv` (pin tag), `uv sync --frozen --no-dev`, chạy user không phải root, `EXPOSE 8000`,
  `CMD ["uvicorn", "docqa.api:app", "--host", "0.0.0.0", "--port", "8000"]`. `examples/` được copy vào image
  để demo; DB ở `/data/docqa.db` (`DOCQA_DB`), mount volume để giữ. Key truyền bằng `--env-file .env` hoặc
  `-e ANTHROPIC_API_KEY`, không bake vào image. `.dockerignore` loại `.env`, `.venv`, `*.db`, `.git`.
- **CI** (`.github/workflows/ci.yml`): GitHub Actions, `astral-sh/setup-uv`, `uv sync --locked`, lint/format/
  type/test + eval retrieval-only; job build Docker chạy khi có `Dockerfile`. Không secret, không gọi API.
- **Release**: sau QA + Security gate PASS → `CHANGELOG.md` mục `[0.1.0]`, tag `v0.1.0`. Push/tạo repo trên
  GitHub org `kaikeel` (private) là bước riêng, không thuộc SHAPE; public repo cần CEO duyệt (Milestone 2).
- Không deploy production (out of scope).
