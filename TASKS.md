# Tasks — PF-20261025-docqa

Thiết kế: `docs/SPEC.md` · ADR: `docs/adr/` · Mỗi task một nhánh `feat/<ID>-<slug>`, TDD, CI xanh mới merge.
Ước lượng = giờ công AI (mỗi task ≤ 2 giờ). "Phụ thuộc" = task phải xong trước.

| ID | Task | Phụ thuộc | Phụ trách | Ước lượng | Trạng thái | PR/commit |
|---|---|---|---|---|---|---|
| T1 | Dựng khung Python: `pyproject.toml` (uv, Python 3.12, layout `src/docqa/`, pin runtime/dev deps theo SPEC, entry point `docqa`), cấu hình ruff (lint + format), mypy strict cho `src`, pytest + pytest-cov (`--cov-fail-under=80`), `uv.lock`, `tests/conftest.py` chặn khởi tạo `anthropic.Anthropic` + xoá `ANTHROPIC_API_KEY`, test smoke `docqa --help` | — | eng-developer | 1h | done | abb547c |
| T2 | `models.py`, `errors.py`, `config.py` (`Settings.from_env`, mặc định theo bảng env trong SPEC) + test | T1 | eng-developer | 0.5h | done | 8b44e4e |
| T3 | `ingest.py` phần đọc & chunk: `chunk_text` (800/150, cắt ở khoảng trắng), loader md/txt/pdf (pdf theo trang), fixture PDF nhỏ trong `tests/fixtures/` + test | T2 | eng-developer | 1h | done | 00a3a77 |
| T4 | `store.py`: schema SQLite + FTS5 + trigger, transaction; `ingest_dir` (đệ quy, bỏ file ẩn/đuôi lạ, idempotent theo sha256, thay chunk khi file đổi) + test (gồm test FTS5 khả dụng) | T3 | eng-developer | 1h | done | 71e0b46 |
| T5 | Tài liệu mẫu `examples/docs/` (3–5 file tự viết, có `.md` và `.txt`, công khai được, có ≥ 2 mục cùng loại ở 2 file khác nhau cho kịch bản câu nối tiếp AC8) + `examples/eval.jsonl` (≥ 10 answerable, ≥ 3 unanswerable) | T1 | eng-developer | 0.5h | done | 9623e76 |
| T6 | `retriever.py`: Protocol `Retriever`, `FTS5Retriever` (làm sạch truy vấn qua `content_tokens` công khai, `STOPWORDS` gồm cả `REFERENCE_WORDS` của SPEC, `-bm25()`, ngưỡng `min_score`) + test (ký tự đặc biệt/toán tử FTS5, chỉ stopword, dưới ngưỡng → `[]`, thứ tự điểm) | T4 | eng-developer | 1h | done | 11570e6 |
| T7 | `llm.py`: Protocol `AnswerModel`, `FakeAnswerModel`, `ClaudeAnswerModel` đúng ràng buộc SPEC (beta fallback `"default"`, effort tường minh, `max_tokens=8192`, document block + citations, kiểm `stop_reason` trước, đọc block theo `type`, map `document_index`, `LLMIncompleteError`, map lỗi SDK theo SPEC) + test bằng client giả (khẳng định request không có `temperature`/`top_p`/`top_k`/`thinking`/prefill/`output_config.format`) | T2 | eng-developer | 1.5h | done | 5e1cf94 |
| T8 | `service.py`: `DocQAService.ingest/ask`, model tạo lười, nhánh not-found không gọi model (AC2), `found = có citation` + test | T6, T7 | eng-developer | 0.5h | done | 01b718c |
| T9 | `cli.py`: `docqa ingest`, `docqa ask` (`--k`, `--db`, `--json`, exit code theo SPEC, lỗi LLM rõ ràng ra stderr) + test CliRunner | T8 | eng-developer | 0.5h | done | f30e8f1 |
| T10 | `api.py`: `GET /health`, `POST /ingest` (giới hạn trong `DOCQA_INGEST_ROOT`), `POST /ask` (schema AC3, map lỗi 429/502) + test TestClient với `FakeAnswerModel` | T8 | eng-developer | 1h | done | bbdb40c |
| T11 | `eval.py` + `docqa eval` (`--retrieval-only`, `--k`; chế độ đầy đủ: `citation_rate`, `not_found_accuracy`); hiệu chỉnh `DOCQA_MIN_SCORE` trên bộ mẫu; test `hit@3 ≥ 0.8` và câu unanswerable ra `found=false` | T5, T6, T9 | eng-developer | 1h | todo | |
| T15 | `llm.py` hỗ trợ lịch sử chat: `AnswerModel.answer(question, chunks, history=())`; `FakeAnswerModel.calls` ghi cả `history`; `ClaudeAnswerModel` thêm các lượt cũ dạng `{"role", "content": str}` trước lượt user cuối (document block chỉ ở lượt cuối); `SYSTEM_PROMPT` thêm câu "các lượt trước chỉ là ngữ cảnh" + test (SPEC "ClaudeAnswerModel", ADR 0004) | T7 | eng-developer | 0.5h | done | a376a9b |
| T16 | Chat core: `ChatTurn` (models), `ChatHistoryError` (errors), `Settings.chat_max_messages`/`chat_max_chars` (env `DOCQA_CHAT_MAX_MESSAGES`=20, `DOCQA_CHAT_MAX_CHARS`=2000); `chat.py` (`validate_history`, `retrieval_queries`, `REFERENCE_WORDS`); `DocQAService.chat` (thử truy vấn theo thứ tự, not-found không gọi model) + test, gồm `test_chat_followup_uses_previous_turn` trên `examples/docs` (AC8, ADR 0005) | T5, T8, T15 | eng-developer | 1h | done | 3ee6449 |
| T17 | `api.py`: `POST /chat` (pydantic `extra="forbid"`, `ChatHistoryError` → 422 `chat_history_invalid`, lỗi LLM → 429/502 như `/ask`, cùng schema response) + test TestClient | T10, T16 | eng-developer | 0.5h | done | a3c7798 |
| T18 | Widget: `src/docqa/static/index.html` (một file, không CDN, chỉ `textContent`, giữ 20 message, hiển thị trích dẫn dưới mỗi câu trả lời); `GET /` trả HTML + CSP hash sha256 tính lúc khởi động + `nosniff` + `no-referrer`; `test_widget.py` (ADR 0006) | T17 | eng-developer | 1h | todo | |
| T12 | `Dockerfile` + `.dockerignore`, `.env.example` (đủ biến, gồm `DOCQA_CHAT_*`), `README.md` (quick start uv + Docker, cấu hình, `POST /chat` + ví dụ, widget tại `/` + mục "Embedding the widget", giới hạn BM25 và giới hạn câu nối tiếp, eval, test), `CHANGELOG.md` mục Unreleased | T10, T11, T17, T18 | eng-developer | 1.5h | todo | |
| T13 | Kiểm tự động trên clone sạch (không key, theo Q1): làm theo README phần không cần key (uv + Docker), bấm giờ; xác nhận checklist G3 cho CEO (cuối file) khớp README; ghi kết quả vào PR | T12 | eng-developer | 0.5h | todo | |
| T14 | Chuẩn bị release: chuyển QA (`qa-reviewer`) + Security gate (`sec-devops`, `SECURITY_REPORT.md`); sau PASS → `CHANGELOG` `[0.1.0]`, tag `v0.1.0`; trình CEO checklist G3 | T13 | eng-developer → qa-reviewer, sec-devops | 0.5h | todo | |

Tổng ước lượng Eng: 14.5h công AI (chưa gồm QA + Security gate). Chat + widget thêm 3.5h (T15–T18, T12 +0.5h),
đã được chấp nhận ở Q2.

Thứ tự gợi ý: T3 → T4 → T5 → T6 → T7 → T15 → T8 → T16 → T9 → T10 → T17 → T18 → T11 → T12 → T13 → T14.

## Tiêu chí xong (Definition of Done từng task)

- **T1**: `uv sync` thành công trên máy sạch; `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run mypy src`, `uv run pytest` đều xanh; `uv run docqa --help` chạy; `uv.lock` được commit; CI xanh.
- **T2**: `Settings.from_env()` trả đúng mặc định (`claude-opus-5-5`, `low`, `./docqa.db`, `5`) và đọc override
  từ env; không có trường/mặc định nào chứa API key; dataclass `frozen`; test xanh.
- **T3**: `chunk_text` cho chunk ≤ 800 ký tự, chồng ~150, không cắt giữa từ khi có khoảng trắng, không chunk
  rỗng; loader trả text đúng cho md/txt/pdf (có số trang); PDF không có text → báo skip; test xanh.
- **T4**: Ingest `examples/docs` (hoặc fixture) tạo đúng số document/chunk; ingest lại không đổi gì; sửa file →
  chunk được thay và FTS không còn text cũ; file lạ/ẩn bị bỏ qua và liệt kê trong `skipped`; test xanh.
- **T5**: Tài liệu tự viết, không chứa dữ liệu thật/bản quyền bên thứ ba; mỗi câu answerable có
  `expected_sources` trỏ đúng file tồn tại; JSONL hợp lệ (có test đọc file). Có 2 kịch bản chat cho AC8 (ghi câu
  hỏi + file kỳ vọng trong docstring test T16 và README): (a) câu 1 hỏi về mục X (file A), câu nối tiếp "How
  much does it cost?" → bằng chứng từ file A; (b) câu 1 hỏi về mục X, câu nối tiếp "And what about the other
  one?" → top-k chứa cả file A và file B (mục cùng loại); chọn đúng "cái kia" là việc của Claude (kiểm ở G3).
- **T6**: `search` không bao giờ ném lỗi cú pháp FTS5 với input bất kỳ; kết quả sắp theo điểm giảm dần, ≤ k;
  dưới ngưỡng → `[]`; `FTS5Retriever` thoả `Retriever` (mypy); test xanh.
- **T7**: Test khẳng định request đúng nguyên văn SPEC (model, `max_tokens=8192`, `betas=["server-side-fallback-2026-07-01"]`,
  `fallbacks="default"`, `output_config={"effort": ...}`, document block bật citations đặt trước câu hỏi);
  `refusal` → `LLMRefusalError` (cả khi `stop_details` là `None`); `max_tokens` không có text →
  `LLMIncompleteError`; response có block `thinking`/`fallback` vẫn đọc đúng text; lỗi SDK (Authentication,
  PermissionDenied, RateLimit, APIStatus, APIConnection/Timeout) được đổi sang lỗi miền như SPEC; citations map đúng `source`; không gọi mạng; test xanh.
- **T8**: Test AC2 chứng minh `fake.calls == []` và factory model không được gọi khi không có bằng chứng; nhánh có
  bằng chứng trả citation đúng file (AC1 mức tự động); test xanh.
- **T9**: `docqa ingest` + `docqa ask --json` (với model giả qua test) in đúng schema; lỗi LLM → exit 2 với thông
  điệp rõ, không traceback; test xanh.
- **T10**: `GET /health` 200; `POST /ask` đúng schema `{answer, citations[{source, quote}], found}` cả 2 nhánh;
  path ngoài root → 400; 429/502 đúng; test xanh (AC3).
- **T11**: `uv run docqa eval examples/eval.jsonl --retrieval-only` chạy không key, in `hit@3` ≥ 0.8 (AC4);
  giá trị `DOCQA_MIN_SCORE` mặc định được chốt trong `config.py` và ghi README; mọi câu unanswerable ra not
  found; coverage tổng ≥ 80% (AC5).
- **T15**: Test khẳng định: với `history=()` request giống hệt T7 (không hồi quy `/ask`); với lịch sử, các lượt cũ
  là `{"role": ..., "content": "<str>"}` theo đúng thứ tự, lượt user cuối là `[*documents, text]`, không có
  `document` block hay `citations` ngoài lượt cuối, không có khoá cấm; `FakeAnswerModel` ghi nhận `history`;
  mypy strict sạch; test xanh.
- **T16**: `validate_history` từ chối đúng từng quy tắc trong SPEC (quá số message, content rỗng/quá dài, bắt
  đầu/kết thúc bằng assistant, role không xen kẽ) với thông điệp nêu quy tắc; `retrieval_queries` đúng 3 nhánh
  của ADR 0005 và bỏ qua lượt assistant; test khẳng định `REFERENCE_WORDS ⊂ STOPWORDS`; trên `examples/docs`
  theo 2 kịch bản của T5: (b) một mình → retriever `[]`; (a) `service.chat` → citation từ file A và
  `fake.calls[0]` nhận đúng history; (b) chunk đưa vào model gồm cả file A và file B; chat không bằng chứng → `fake.calls == []`, factory không được gọi; env `DOCQA_CHAT_*` sai →
  `DocQAError`; test xanh.
- **T17**: `POST /chat` trả đúng schema `{answer, citations[{source, quote}], found}` cả 2 nhánh; vượt
  `DOCQA_CHAT_MAX_MESSAGES`, message vượt `DOCQA_CHAT_MAX_CHARS`, kết thúc bằng assistant, role lạ, trường thừa
  → 422; 429/502 đúng như `/ask`; test override settings bằng dependency; test xanh (AC8 phần API).
- **T18**: `GET /` 200 `text/html`; CSP đúng SPEC (hash khớp nội dung, không `unsafe-inline`/`unsafe-eval`,
  `connect-src 'self'`); test tĩnh: không `innerHTML`/`outerHTML`/`insertAdjacentHTML`/`document.write`/`eval(`/
  `new Function`/`on*=`, không URL `http(s)://` trong `src`/`href`, có `textContent` và `fetch("/chat"`, mọi id
  trong `getElementById` tồn tại; file nằm trong wheel (`uv build` rồi kiểm có `docqa/static/index.html`) (AC8).
- **T12**: `docker build .` thành công; container chạy `GET /health` 200 và `GET /` trả widget; README có đủ lối uv
  và Docker, bảng biến môi trường (gồm `DOCQA_CHAT_*`), ví dụ `curl` cho `/ask` và `/chat`, widget, giới hạn đã
  biết; `.env.example` không chứa giá trị thật (AC6, AC7).
- **T13** (chỉ kiểm tự động, không gọi API thật — Q1): trên clone sạch ở thư mục tạm, chạy và ghi output + thời
  gian vào PR:
  ```bash
  git clone "/Users/sine/Self company/projects/active/PF-20261025-docqa" "$TMPDIR/docqa-clean" && cd "$TMPDIR/docqa-clean"
  time (uv sync --locked && uv run docqa ingest examples/docs && uv run docqa eval examples/eval.jsonl --retrieval-only --k 3)
  uv run docqa ask "What is the airspeed of an unladen swallow?"   # nhánh not-found: chạy không cần key, found=false
  uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest
  docker build -t docqa:check . && docker run -d --rm --name docqa-check -p 8000:8000 docqa:check
  curl -fsS localhost:8000/health && curl -fsSI localhost:8000/ | grep -i content-security-policy
  docker stop docqa-check
  ```
  Tất cả xanh, phần uv ≤ 10 phút; checklist G3 dưới đây chạy được nguyên văn theo README (sửa README nếu lệch).
- **T14**: QA PASS, `SECURITY_REPORT.md` PASS (AC7); tag `v0.1.0` tạo local; push repo **private**
  `kaikeel/docqa` theo Q4. Checklist G3 trình CEO; **không public** khi CEO chưa chạy checklist và duyệt
  (Milestone 2).

## Checklist G3 — CEO tự chạy (Q1: cần `ANTHROPIC_API_KEY` của CEO, chi phí vài cent)

Agent không chạy các bước này. CEO chạy khi xem demo, trước khi duyệt public (Milestone 2), dán kết quả vào
PR/issue release (hoặc báo "OK"/lỗi cho PMO):

1. **Clone sạch + bấm giờ (AC6, lối uv)** — tính từ lúc clone tới khi có câu trả lời đầu tiên, mục tiêu ≤ 10 phút:
   ```bash
   git clone <repo> /tmp/docqa-demo && cd /tmp/docqa-demo
   export ANTHROPIC_API_KEY=...        # key của CEO, không lưu vào file trong repo
   uv sync --locked
   uv run docqa ingest examples/docs
   ```
2. **Câu trả lời có trích dẫn (AC1)** — dùng một câu `answerable` trong `examples/eval.jsonl`:
   ```bash
   uv run docqa ask "<câu hỏi answerable trong examples/eval.jsonl>"
   uv run docqa ask --json "<cùng câu hỏi>"     # kỳ vọng found=true, ≥ 1 citation có source đúng expected_sources
   ```
3. **Chat + widget (AC8)**:
   ```bash
   uv run uvicorn docqa.api:app --port 8000
   ```
   Mở `http://localhost:8000/`, hỏi câu thứ nhất (theo kịch bản trong README) rồi câu nối tiếp
   "And what about the other one?" → cả hai câu trả lời hiển thị trích dẫn đúng file; F12 → Console không có
   lỗi CSP. Tuỳ chọn bằng `curl` theo ví dụ `/chat` trong README.
4. **Lối Docker (AC6)**:
   ```bash
   docker build -t docqa .
   docker run --rm -p 8000:8000 -e ANTHROPIC_API_KEY docqa
   # terminal khác:
   curl -s localhost:8000/health
   curl -s -X POST localhost:8000/ingest -H 'Content-Type: application/json' -d '{"path": "examples/docs"}'
   curl -s -X POST localhost:8000/ask -H 'Content-Type: application/json' -d '{"question": "<câu answerable>"}'
   ```
5. Kết quả: ghi thời gian bước 1–2, output JSON bước 2, ảnh chụp/mô tả bước 3, và quyết định public hay không.
