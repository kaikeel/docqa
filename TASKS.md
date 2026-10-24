# Tasks — PF-20261025-docqa

Thiết kế: `docs/SPEC.md` · ADR: `docs/adr/` · Mỗi task một nhánh `feat/<ID>-<slug>`, TDD, CI xanh mới merge.
Ước lượng = giờ công AI (mỗi task ≤ 2 giờ). "Phụ thuộc" = task phải xong trước.

| ID | Task | Phụ thuộc | Phụ trách | Ước lượng | Trạng thái | PR/commit |
|---|---|---|---|---|---|---|
| T1 | Dựng khung Python: `pyproject.toml` (uv, Python 3.12, layout `src/docqa/`, pin runtime/dev deps theo SPEC, entry point `docqa`), cấu hình ruff (lint + format), mypy strict cho `src`, pytest + pytest-cov (`--cov-fail-under=80`), `uv.lock`, `tests/conftest.py` chặn khởi tạo `anthropic.Anthropic` + xoá `ANTHROPIC_API_KEY`, test smoke `docqa --help` | — | eng-developer | 1h | done | abb547c |
| T2 | `models.py`, `errors.py`, `config.py` (`Settings.from_env`, mặc định theo bảng env trong SPEC) + test | T1 | eng-developer | 0.5h | todo | |
| T3 | `ingest.py` phần đọc & chunk: `chunk_text` (800/150, cắt ở khoảng trắng), loader md/txt/pdf (pdf theo trang), fixture PDF nhỏ trong `tests/fixtures/` + test | T2 | eng-developer | 1h | todo | |
| T4 | `store.py`: schema SQLite + FTS5 + trigger, transaction; `ingest_dir` (đệ quy, bỏ file ẩn/đuôi lạ, idempotent theo sha256, thay chunk khi file đổi) + test (gồm test FTS5 khả dụng) | T3 | eng-developer | 1h | todo | |
| T5 | Tài liệu mẫu `examples/docs/` (3–5 file tự viết, có `.md` và `.txt`, công khai được) + `examples/eval.jsonl` (≥ 10 answerable, ≥ 3 unanswerable) | T1 | eng-developer | 0.5h | todo | |
| T6 | `retriever.py`: Protocol `Retriever`, `FTS5Retriever` (làm sạch truy vấn, `-bm25()`, ngưỡng `min_score`) + test (ký tự đặc biệt/toán tử FTS5, chỉ stopword, dưới ngưỡng → `[]`, thứ tự điểm) | T4 | eng-developer | 1h | todo | |
| T7 | `llm.py`: Protocol `AnswerModel`, `FakeAnswerModel`, `ClaudeAnswerModel` đúng ràng buộc SPEC (beta fallback, effort, document block + citations, kiểm `stop_reason`, map `document_index`, bắt 4 loại lỗi) + test bằng client giả (khẳng định request không có `temperature`/`top_p`/`top_k`/`thinking`/prefill/`output_config.format`) | T2 | eng-developer | 1.5h | todo | |
| T8 | `service.py`: `DocQAService.ingest/ask`, model tạo lười, nhánh not-found không gọi model (AC2), `found = có citation` + test | T6, T7 | eng-developer | 0.5h | todo | |
| T9 | `cli.py`: `docqa ingest`, `docqa ask` (`--k`, `--db`, `--json`, exit code theo SPEC, lỗi LLM rõ ràng ra stderr) + test CliRunner | T8 | eng-developer | 0.5h | todo | |
| T10 | `api.py`: `GET /health`, `POST /ingest` (giới hạn trong `DOCQA_INGEST_ROOT`), `POST /ask` (schema AC3, map lỗi 429/502) + test TestClient với `FakeAnswerModel` | T8 | eng-developer | 1h | todo | |
| T11 | `eval.py` + `docqa eval` (`--retrieval-only`, `--k`; chế độ đầy đủ: `citation_rate`, `not_found_accuracy`); hiệu chỉnh `DOCQA_MIN_SCORE` trên bộ mẫu; test `hit@3 ≥ 0.8` và câu unanswerable ra `found=false` | T5, T6, T9 | eng-developer | 1h | todo | |
| T12 | `Dockerfile` + `.dockerignore`, `.env.example` (đủ biến), `README.md` (quick start uv + Docker, cấu hình, giới hạn BM25, eval, test), `CHANGELOG.md` mục Unreleased | T10, T11 | eng-developer | 1h | todo | |
| T13 | Kiểm thủ công: clone sạch → làm theo README (uv + Docker) bấm giờ ≤ 10 phút (AC6); `docqa ask` với key thật → ≥ 1 trích dẫn đúng file (AC1); ghi output vào PR | T12 | eng-developer (cần key — xem Q1 trong PROJECT.md) | 0.5h | todo | |
| T14 | Chuẩn bị release: chuyển QA (`qa-reviewer`) + Security gate (`sec-devops`, `SECURITY_REPORT.md`); sau PASS → `CHANGELOG` `[0.1.0]`, tag `v0.1.0` | T13 | eng-developer → qa-reviewer, sec-devops | 0.5h | todo | |

Tổng ước lượng Eng: 11h công AI (chưa gồm QA + Security gate).

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
  `expected_sources` trỏ đúng file tồn tại; JSONL hợp lệ (có test đọc file).
- **T6**: `search` không bao giờ ném lỗi cú pháp FTS5 với input bất kỳ; kết quả sắp theo điểm giảm dần, ≤ k;
  dưới ngưỡng → `[]`; `FTS5Retriever` thoả `Retriever` (mypy); test xanh.
- **T7**: Test khẳng định request đúng nguyên văn SPEC (model, `max_tokens=4096`, `betas`, `fallbacks`,
  `output_config`, document block bật citations đặt trước câu hỏi); `refusal` → `LLMRefusalError`; 4 loại
  lỗi SDK được đổi sang lỗi miền; citations map đúng `source`; không gọi mạng; test xanh.
- **T8**: Test AC2 chứng minh `fake.calls == []` và factory model không được gọi khi không có bằng chứng; nhánh có
  bằng chứng trả citation đúng file (AC1 mức tự động); test xanh.
- **T9**: `docqa ingest` + `docqa ask --json` (với model giả qua test) in đúng schema; lỗi LLM → exit 2 với thông
  điệp rõ, không traceback; test xanh.
- **T10**: `GET /health` 200; `POST /ask` đúng schema `{answer, citations[{source, quote}], found}` cả 2 nhánh;
  path ngoài root → 400; 429/502 đúng; test xanh (AC3).
- **T11**: `uv run docqa eval examples/eval.jsonl --retrieval-only` chạy không key, in `hit@3` ≥ 0.8 (AC4);
  giá trị `DOCQA_MIN_SCORE` mặc định được chốt trong `config.py` và ghi README; mọi câu unanswerable ra not
  found; coverage tổng ≥ 80% (AC5).
- **T12**: `docker build .` thành công; container chạy `GET /health` 200; README có đủ lối uv và Docker, bảng
  biến môi trường, giới hạn đã biết; `.env.example` không chứa giá trị thật (AC6, AC7).
- **T13**: Có bằng chứng (output dán vào PR) cho AC1 với API thật và thời gian chạy README ≤ 10 phút (AC6).
- **T14**: QA PASS, `SECURITY_REPORT.md` PASS (AC7); tag `v0.1.0` tạo local. Không push/không public khi chưa
  có quyết định CEO (Milestone 2).
