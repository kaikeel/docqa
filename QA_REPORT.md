# QA Report — PF-20261025-docqa — Milestone 1 (v0.1.0) — 2026-10-25

**Kết luận: FAIL**

Người kiểm: `qa-reviewer` (độc lập với Eng). Commit kiểm: `0de2e8e` (code), HEAD hiện tại `e172bd0` chỉ thêm
`SECURITY_REPORT.md` (`git diff --name-only 0de2e8e e172bd0` → `SECURITY_REPORT.md`). Môi trường: macOS, Python
3.12.9, uv 0.6.3, Docker Desktop. **Không có `ANTHROPIC_API_KEY`, không gọi API thật** (Q1). Mọi lệnh chạy trên
clone sạch ở thư mục tạm (đã xoá sau khi kiểm).

Lý do FAIL: 5 lỗi **major** (không có blocker do QA tìm ra), cộng thêm `SECURITY_REPORT.md` = FAIL (gate của phòng 05).
CHANGELOG `[0.1.0]` + tag và CI trên GitHub là bước sau gate (T14), chưa tính là lỗi.

Phần đúng (tự chạy lại, không dựa vào báo cáo của Eng): 186 test pass, coverage 99.89%, ruff/format/mypy sạch,
hit@3 0.944 (17/18) và 4/4 câu unanswerable bị chặn, `docker build` OK. Tests có ý nghĩa thật: chặn socket + client
thật, khẳng định nguyên văn request gửi Claude, AC2 kiểm `factory.calls == 0`. Widget an toàn XSS, đã kiểm trên
Chrome headless thật.

## Ma trận nghiệm thu

| Tiêu chí | Test / bằng chứng | Kết quả |
|---|---|---|
| AC1 ingest + ask trả lời có ≥ 1 trích dẫn đúng file | Tự động: `test_service.py::test_ask_returns_citation_from_expected_file`, `test_cli.py::test_ask_prints_answer_and_citations`, `test_llm.py::test_request_matches_spec_exactly`, `::test_response_text_and_citations_are_mapped` (map `document_index` → `source`, bỏ block `thinking`/`fallback`). Thủ công: `docqa ingest examples/docs` → 10 tài liệu / 23 chunk; `docqa ask` câu có bằng chứng khi không có key → exit 2 `Error: ANTHROPIC_API_KEY is missing or invalid.` (đúng thiết kế) | **Đạt phần tự động. Phần API thật để CEO (G3).** Có lỗi **#1**: phần lớn câu hỏi tổng quát/ngắn bị trả "Not found" dù tài liệu có câu trả lời |
| AC2 không có trong tài liệu → not found, không gọi API | `test_service.py::test_not_found_does_not_call_model` (`factory.calls == 0`, `model.calls == []`), `test_chat.py::test_chat_not_found_does_not_call_model`, `test_eval.py::test_unanswerable_questions_are_not_found_by_service`, `test_retriever.py` (toán tử FTS5, ký tự lạ, 300 chuỗi ngẫu nhiên). Thủ công không key: CLI + `/ask` + `/chat` trả `found:false`, HTTP 200, exit 0 | **Đạt** |
| AC3 `POST /ask` schema, `GET /health` 200 | `test_api.py` (schema cả 2 nhánh, 422, 429/502). Thủ công qua uvicorn local và Docker: `/health` → `{"status":"ok"}`; `/ask` → `{"answer","citations","found"}`; thiếu key → 502 `llm_auth` | **Đạt** (lỗi định dạng nhỏ **#7**, **#8**) |
| AC4 eval `--retrieval-only` không key, hit@3 ≥ 0.8 | Tự chạy lại: `hit@3: 0.944 (17/18 answerable)`, `unanswerable rejected: 4/4`. QA thêm bộ câu hỏi giữ lại (held-out) 26 câu tự viết: hit@3 0.800 (16/20), chặn 4/6 câu unanswerable | **Đạt** (lưu ý: ngưỡng được hiệu chỉnh trên chính bộ eval; xem **#1**) |
| AC5 test offline, coverage ≥ 80%, ruff + mypy sạch | `186 passed`, `Total coverage: 99.89%`; `ruff check` / `format --check` / `mypy src` sạch; `conftest.py` chặn `socket.connect`, `create_connection`, `anthropic.Anthropic`; `test_smoke.py` chứng minh cơ chế chặn hoạt động | **Đạt** |
| AC6 README đưa người lạ tới câu trả lời đầu tiên ≤ 10 phút (có Docker) | Lối uv, cache uv rỗng: clone → `uv sync --locked` → ingest → câu trả lời đầu tiên (not found) mất **21 giây**. Docker `docker build --no-cache` 49 giây; `docker run -e ANTHROPIC_API_KEY` + các lệnh curl trong README chạy được. **Lối `--env-file .env` mà README hướng dẫn: mọi request trả 500** | **Không đạt** (lỗi **#2**). Thời gian tới câu trả lời *thật* để CEO đo |
| AC7 không secret; key chỉ đọc từ env; SECURITY_REPORT PASS | `git grep` mẫu key trên toàn lịch sử: chỉ thấy chuỗi giả trong test/report; `Settings` không có trường key (`test_settings_never_hold_an_api_key`); image không chứa biến `ANTHROPIC*`, `docker history` không có `sk-ant`. **`SECURITY_REPORT.md` kết luận FAIL** (M1 symlink, M2 giới hạn độ dài `/chat`) | **Không đạt** (do Security gate) |
| AC8 `/chat` câu nối tiếp; history quá giới hạn → 422; widget chỉ dùng `textContent` | `test_chat.py::test_chat_followup_same_item`, `::test_chat_followup_other_item`, `test_api.py::test_chat_history_rules_are_422`, `test_widget.py` (CSP hash, không `innerHTML`). Thủ công: 21 / 1000 message → 422, 2001 ký tự → 422, role sai → 422. Chrome headless thật với model giả trả HTML độc (`<img onerror>`, `<script>`): không chạy script, 0 phần tử bị chèn, không có vi phạm CSP | **Không đạt**: lỗi **#3** (widget bị kẹt) và **#4** (độn khoảng trắng để vượt giới hạn) |

## Lỗi

| # | Mức độ | Mô tả | Cách tái hiện | Trạng thái |
|---|---|---|---|---|
| 1 | major | **Ngưỡng bằng chứng `DOCQA_MIN_SCORE=3.0` từ chối phần lớn câu hỏi tự nhiên, ngắn hoặc tổng quát** dù file đúng đứng top-1. Điểm BM25 tăng theo số từ khớp, nên câu có 1–2 từ nội dung hầu như luôn dưới 3.0. Ngưỡng được hiệu chỉnh trên chính 22 câu eval (toàn câu dài), nên số 0.944 là đo trong mẫu (in-sample). ADR 0002 viết "3.0 is near the low end so short but valid questions still pass"; điều này sai với bằng chứng dưới đây. Câu hỏi mở Q6 (cần sol-architect xác nhận) vẫn chưa đóng. Với portfolio, người xem gõ câu tổng quát vào widget sẽ nhận "Not found" ở hầu hết lượt | Ingest `examples/docs`, rồi `docqa ask "What is the warranty?"` → `Not found` (top-1 `warranty-policy.md` 1.45). 8/10 câu "khách lần đầu" bị Not found: "Tell me about the warranty" 1.45, "What support plans do you have?" 2.65, "What is the release process?" 2.05, "How do you handle incidents?" 2.09, "What is in the security checklist?" 2.65, "What is a change request?" 2.95, "How do you estimate?" 1.97, "What is the delivery process?" 2.64. Từ khoá đơn: "gitleaks" 2.52, "SEV1" 1.71 | open |
| 2 | major | **Docker với `--env-file .env` (lệnh trong README, `.env` copy từ `.env.example`) hỏng hoàn toàn**: `.env.example` đặt `DOCQA_DB=./docqa.db`, ghi đè `DOCQA_DB=/data/docqa.db` của image; `/app` thuộc root nên user `docqa` không tạo được DB. `/health` vẫn 200 nên trông như đang chạy tốt | `cp .env.example .env && docker run -p 8090:8000 --env-file .env docqa` → `/health` 200; `/ingest`, `/ask` → `500 Internal Server Error`; log: `sqlite3.OperationalError: unable to open database file` | open |
| 3 | major | **Widget bị kẹt vĩnh viễn sau một câu trả lời dài hơn `DOCQA_CHAT_MAX_CHARS` (2000)**. Widget đẩy nguyên câu trả lời vào lịch sử, còn server từ chối mọi message > 2000 ký tự, kể cả lượt assistant do chính server sinh ra (`max_tokens` 8192 nên câu trả lời có thể dài hơn 2000 ký tự). Từ đó mọi câu hỏi đều nhận 422 với thông điệp khó hiểu cho người dùng, chỉ thoát được bằng cách tải lại trang | Chrome headless + model giả trả 2500 ký tự: lượt sau hiển thị `message 8 is longer than 2000 characters` cho **mọi** câu hỏi tiếp theo (đã thử 2 câu) | open |
| 4 | major | **Vượt giới hạn độ dài `/chat` bằng cách độn khoảng trắng** (trùng SECURITY M2): `validate_history` đo `len(content.strip())` nhưng chuyển nguyên `content` chưa strip cho retriever và Claude. Thêm vào đó không có giới hạn kích thước body | `POST /chat` với `content = "How long is the warranty on a fixed-price project?" + 1 000 000 dấu cách` (body 1 MB) → qua validate; server thật trả 502 `llm_auth` (tức là đã tới bước gọi model); server dùng model giả trả 200 | open |
| 5 | major | **File symlink nằm trong thư mục ingest nhưng trỏ ra ngoài `DOCQA_INGEST_ROOT` vẫn bị đọc và đưa vào index** (trùng SECURITY M1). Symlink thư mục thì đã bị chặn đúng | Đặt symlink `tmpq/hosts.txt -> /etc/hosts` trong root, rồi `POST /ingest {"path":"tmpq"}` → `{"documents":1,...}` HTTP 200 | open |
| 6 | minor | `POST /ingest` với path chứa ký tự NUL → 500 dạng text thuần (traceback `ValueError: lstat: embedded null character`), trái hợp đồng lỗi `{"detail":{"code","message"}}` | `curl -X POST /ingest -d '{"path":"exam\u0000ples"}'` → `Internal Server Error [HTTP 500]` | open |
| 7 | minor | Cấu hình env sai (vd `DOCQA_EFFORT=turbo`) với API: server vẫn khởi động, `/health` 200, còn `/ask` và `/chat` trả 500 text thuần. Thông điệp rõ ràng chỉ có trong log. CLI thì xử lý đúng (exit 1 kèm thông điệp) | `DOCQA_EFFORT=turbo uv run uvicorn docqa.api:app` → `/ask` `Internal Server Error [HTTP 500]` | open |
| 8 | minor | README ghi lỗi "always as `{"detail": {"code", "message"}}`", nhưng 422 do pydantic trả `detail` dạng list, và có các trường hợp 500 text thuần (#6, #7) | Xem output ở mục lệnh `/ask` / `/chat` dưới đây | open |
| 9 | minor | Ingest một thư mục khác có file trùng *tên tương đối* sẽ âm thầm ghi đè tài liệu cũ trong index (`source` là đường dẫn tương đối so với thư mục ingest). README không ghi giới hạn này | `docqa ingest examples/docs`, rồi `docqa ingest other/` (có `warranty-policy.md` khác) → chunk `warranty-policy.md` bị thay; ingest lại `examples/docs` → `1 documents ... (9 unchanged)` | open |
| 10 | minor | Tìm kiếm tiếng Trung gần như không chạy được: tokenizer `unicode61` không tách từ CJK, nên cả một chuỗi chữ Hán liền nhau thành một token và truy vấn con không khớp. README không ghi giới hạn này, trong khi người xem mục tiêu có khách CN. Tiếng Việt có dấu và không dấu đều khớp (`remove_diacritics 2`) | Ingest `zh.txt` = `保修政策：固定价格项目享有三十天保修。` → MATCH `"保修"` → `[]` | open |
| 11 | minor | `skipped` trong phản hồi `/ingest` không giới hạn độ dài và liệt kê toàn bộ cây file dưới root. Có thể ingest bất kỳ thư mục con nào của root (vd `.venv`), làm bẩn index chung và không có cách xoá ngoài việc xoá file DB | Docker: `POST /ingest {"path":"examples/docs/../../.venv"}` → 200, body ~850 KB, index thêm 28 file license từ site-packages | open |
| 12 | minor | pypdf in cảnh báo ra stderr khi gặp PDF hỏng (`invalid pdf header: b'not a'`, `EOF marker not found`), lẫn vào output CLI vốn đã có dòng `skipped` rõ ràng | `docqa ingest` thư mục có `garbage.pdf`, `truncated.pdf` | open |
| 13 | minor | `DOCQA_MIN_SCORE=nan` (hoặc `-inf`) được chấp nhận: với `nan` mọi phép so sánh đều sai nên cổng bằng chứng bị tắt mà không báo gì | `DOCQA_MIN_SCORE=nan docqa ask "..."` → đi tới bước gọi model | open |
| 14 | minor | Tài liệu lệch nhau: bảng Milestone trong `PROJECT.md` vẫn ghi "AC1–AC7" (Eng đã đề nghị PMO sửa); `docs/SPEC.md` vẫn ghi "Trạng thái: SHAPE", `IngestReport` và bảng API `/ingest` thiếu `unchanged`; Q6 chưa có xác nhận của sol-architect | Đọc tài liệu | open |
| 15 | minor | `Store.document_sha` không giữ `lock`, trong khi mọi hàm khác truy cập kết nối dùng chung giữa các thread đều giữ (lệch với chú thích trong `store.py`) | Đọc code `store.py` | open |
| 16 | minor | Widget không có favicon nên Console báo `404 (Not Found)`. Đây không phải lỗi CSP, nhưng gây nhiễu cho bước "F12 → Console không có lỗi" trong checklist G3 của CEO | Mở `/` trên Chrome, xem Console | open |

### README: chỗ sai, thiếu hoặc mơ hồ (làm đúng như người lạ)
1. **Sai:** lối `docker run ... --env-file .env` kết hợp hướng dẫn trong `.env.example` cho ra container lỗi 500 (#2).
   Nên bỏ dòng `DOCQA_DB` (và `DOCQA_INGEST_ROOT` rỗng) khỏi `.env.example`, hoặc ghi chú riêng cho Docker.
2. **Sai:** câu "always as `{"detail": {"code", "message"}}`" (#8).
3. **Thiếu** trong *Known limitations*: câu hỏi ngắn hoặc tổng quát bị cổng ngưỡng từ chối (#1); CJK (#10); trùng tên
   file giữa các thư mục (#9); symlink (#5, sau khi sửa thì ghi hành vi mới).
4. **Thiếu** cho người xem widget: không có câu hỏi gợi ý nào. Người lạ không biết tài liệu mẫu nói gì, nên kết hợp với
   #1 sẽ gặp "Not found" ngay ở lượt đầu.
5. **Mơ hồ / chờ điền:** `git clone <repository-url>`, cần điền URL thật khi push (Q4/Milestone 2).
6. **Đúng nguyên văn:** quick start uv, ví dụ not-found, output eval (`cases: 22 / hit@3: 0.944 (17/18 answerable) /
   unanswerable rejected: 4/4`), các lệnh test, `docker run -e ANTHROPIC_API_KEY`, các lệnh curl `/health`, `/ingest`,
   `/ask`, `-v docqa-data:/data` (giữ index qua lần chạy lại: lần 2 trả `unchanged: 10`), image non-root (`uid=10001`).

### Code review (theo `04-qa/checklists/code-review.md`)
- [x] Đúng scope, không làm thừa (CLI, API, chat, widget, eval đúng SPEC; lệch duy nhất là ngữ nghĩa ngưỡng, đã ghi ADR 0002, Q6 còn mở).
- [ ] Logic đúng với case biên và xử lý lỗi rõ ràng: lỗi #3, #4, #5, #6, #7, #13.
- [x] Test có ý nghĩa: assert trên nội dung (request gửi Claude, số lần gọi model, thứ tự điểm, rollback transaction, CSP hash), không chỉ chạy để lấy coverage. Lỗ hổng: không có test cho tương tác widget ↔ giới hạn server (#3), không có test độn khoảng trắng (#4), không có test symlink file (#5), không có đánh giá held-out (#1).
- [x] Tên rõ ràng, ít trùng lặp (`answer_payload` của CLI và `AnswerResponse` của API là hai cách serialize cùng một schema; chấp nhận được).
- [x] Không có vòng lặp tốn kém vô lý: file 25 MB (38 466 chunk) ingest trong 1.8 giây, RSS ~200 MB.
- [x] Dependency pin chính xác, có `uv.lock`, license MIT/BSD/Apache (CVE do Security kiểm: sạch).
- [x] Không có secret, không log key; không có TODO/FIXME/debug print (`grep -rnE 'TODO|FIXME|XXX|HACK|breakpoint\(|pdb\.|print\(' src scripts tests` → rỗng).

### Definition of Done
| Mục | Trạng thái |
|---|---|
| Mọi AC có bằng chứng đạt | Không: AC6, AC7, AC8 chưa đạt (xem ma trận) |
| CI xanh, lint sạch, không blocker/major | Lint/test sạch khi chạy local đúng các bước CI; CI trên GitHub chưa chạy vì chưa push (Q4); còn 5 major |
| README chạy từ máy sạch | Lối uv và `docker run -e` đạt; `--env-file` không đạt (#2) |
| `SECURITY_REPORT.md` PASS | Không đạt: FAIL (M1 = #5, M2 = #4) |
| CHANGELOG cập nhật, tag release | `[Unreleased]` đầy đủ T1–T13; `[0.1.0]` + tag `v0.1.0` để sau gate (T14), chưa làm |
| Không code thừa / TODO / debug print / secret | Đạt |

### Để lại cho CEO ở G3 (Q1, cần key của CEO, chỉ làm **sau** khi các lỗi major đã sửa và QA chạy lại PASS)
1. AC1: `docqa ask` / `ask --json` bằng một câu *answerable* trong `examples/eval.jsonl` → `found=true`, có ≥ 1 citation đúng `expected_sources`. Nên thử thêm một câu tổng quát như "What is the warranty?" để kiểm lại #1 sau khi sửa.
2. AC6: bấm giờ từ lúc clone tới câu trả lời **thật** đầu tiên (lối uv) và chạy lối Docker. Phần không cần key: QA đo được 21 giây (uv, cache rỗng) và 49 giây (docker build `--no-cache`).
3. AC8: trên widget, hỏi "What does the Starter plan include?" rồi "And what about the other one?" → Claude chọn đúng gói Pro, trích dẫn `support-plan-pro.txt`. Kiểm Console: không có lỗi CSP (404 favicon là #16).
4. Kiểm phần trích dẫn thật: `quote` là trích nguyên văn, `source` đúng file; lỗi thật (thiếu hoặc sai key) → 502 `llm_auth`.

## Kết quả lệnh đã chạy

```
$ git clone "/Users/sine/Self company/projects/active/PF-20261025-docqa" docqa && cd docqa && git log --oneline -1
0de2e8e Merge branch 'feat/T14-release-prep'
$ uv sync --locked            # cache uv rỗng: UV_CACHE_DIR=<thư mục rỗng>
 + uvicorn==0.54.0
$ uv run docqa ingest examples/docs
Ingested 10 documents, 23 chunks; skipped: none
$ uv run docqa ask "What is the airspeed of an unladen swallow?"
Not found in the provided documents.
cold-cache clone→first (not-found) answer: 21s

$ uv run ruff check .
All checks passed!
$ uv run ruff format --check .
33 files already formatted
$ uv run mypy src
Success: no issues found in 13 source files
$ uv run pytest --cov=docqa --cov-fail-under=80
Name                     Stmts   Miss Branch BrPart  Cover   Missing
--------------------------------------------------------------------
src/docqa/__init__.py        1      0      0      0   100%
src/docqa/api.py            98      0      4      0   100%
src/docqa/chat.py           35      0     22      0   100%
src/docqa/cli.py            71      0     10      0   100%
src/docqa/config.py         52      0      8      0   100%
src/docqa/errors.py         33      0      0      0   100%
src/docqa/eval.py           72      0     20      0   100%
src/docqa/ingest.py        122      0     48      0   100%
src/docqa/llm.py           101      0     28      0   100%
src/docqa/models.py         33      0      0      0   100%
src/docqa/retriever.py      34      0      8      0   100%
src/docqa/service.py        49      0     10      0   100%
src/docqa/store.py          46      0      2      1    98%   63->67
--------------------------------------------------------------------
TOTAL                      747      0    160      1    99%
Required test coverage of 80% reached. Total coverage: 99.89%
186 passed in 13.03s

$ uv run docqa eval examples/eval.jsonl --retrieval-only
cases: 22
hit@3: 0.944 (17/18 answerable)
unanswerable rejected: 4/4 (retrieval found nothing)
$ uv run docqa eval <QA held-out 26 câu> --retrieval-only --k 3
cases: 26
hit@3: 0.800 (16/20 answerable)
unanswerable rejected: 4/6 (retrieval found nothing)

$ docker build --no-cache -q -t docqa-qa-cold .
exit=0 no-cache build: 49s
$ docker run -d --rm -p 8000:8000 -e ANTHROPIC_API_KEY docqa-qa      # không có key
$ curl -s localhost:8000/health
{"status":"ok"}
$ curl -s -X POST localhost:8000/ingest -H 'Content-Type: application/json' -d '{"path": "examples/docs"}'
{"documents":10,"chunks":23,"skipped":[],"unchanged":0}
$ curl -s -X POST localhost:8000/ask ... '{"question": "How long is the warranty on a fixed-price project?"}'
{"detail":{"code":"llm_auth","message":"ANTHROPIC_API_KEY is missing or invalid."}} [HTTP 502]
$ curl -s -X POST localhost:8000/ask ... '{"question": "What is the airspeed of an unladen swallow?"}'
{"answer":"Not found in the provided documents.","citations":[],"found":false} [HTTP 200]
$ curl -sI localhost:8000/
HTTP/1.1 200 OK
content-security-policy: default-src 'none'; script-src 'sha256-OgkWjW5F0vFYvKVwV3jFPH5RiLzreOs6qc8Vov0j7iI='; style-src 'sha256-2Y5x/3TcY8pjhsKiDH7Eaz45BoTaCeLqBIsQ8ySzegI='; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'
x-content-type-options: nosniff
referrer-policy: no-referrer
$ docker exec docqa-qa id
uid=10001(docqa) gid=10001(docqa) groups=10001(docqa)
# -v docqa-qa-vol:/data, chạy lại container:
{"documents":0,"chunks":0,"skipped":[],"unchanged":10}

# Lỗi #2: --env-file từ .env.example
$ cp .env.example .env && docker run -d -p 8090:8000 --env-file .env docqa-qa
{"status":"ok"} [HTTP 200]
Internal Server Error [HTTP 500]        # POST /ingest
Internal Server Error [HTTP 500]        # POST /ask
sqlite3.OperationalError: unable to open database file

# CLI case biên
== empty dir         Ingested 0 documents, 0 chunks; skipped: none            exit=0
== nonexistent       Error: ../edge/nope is not a directory                   exit=1
== file instead      Error: README.md is not a directory                      exit=1
== bad files
invalid pdf header: b'not a'
EOF marker not found
EOF marker not found
Ingested 2 documents, 2 chunks; skipped: broken-xref.pdf: unreadable PDF (PdfReadError), garbage.pdf: unreadable PDF (PdfStreamError), truncated.pdf: unreadable PDF (PdfStreamError), zero.pdf: unreadable PDF (EmptyFileError)
== unicode (vi/zh/emoji)   Ingested 3 documents, 3 chunks; skipped: none
== big (25 MB txt)   Ingested 1 documents, 38466 chunks; 1.83 real; 201687040 max RSS
== ask ""  / "   " / "???"           {"answer": "Not found in the provided documents.", "citations": [], "found": false}  exit=0
== ask "bảo hành dự án giá cố định"   Error: ANTHROPIC_API_KEY is missing or invalid.  exit=2  (có bằng chứng → tới bước gọi model)
== ask "保修" / "保修政策"             not found (#10)
== ask 100 000 ký tự                   Not found in the provided documents.  exit=0
== thiếu key, câu có bằng chứng       Error: ANTHROPIC_API_KEY is missing or invalid.  exit=2
== DOCQA_EFFORT=turbo                  Error: DOCQA_EFFORT must be one of low, medium, high, xhigh, max, got 'turbo'  exit=1
== ask --k 0                           Invalid value for '--k': 0 is not in the range 1<=x<=20.  exit=2
== eval file thiếu                     Error: cannot read nope.jsonl: FileNotFoundError  exit=1
== ingest lại                          Ingested 0 documents, 0 chunks (10 unchanged); skipped: none

# API (uvicorn local) /ingest
..                         {"detail":{"code":"path_outside_root",...}} [HTTP 400]
/etc                       {"detail":{"code":"path_outside_root",...}} [HTTP 400]
examples/docs/../../../edge {"detail":{"code":"path_outside_root",...}} [HTTP 400]
symlink thư mục -> /etc    {"detail":{"code":"path_outside_root",...}} [HTTP 400]
README.md / nope / ~       {"detail":{"code":"ingest_error","message":"... is not a directory."}} [HTTP 400]
"" / 123 / field lạ / JSON hỏng   422
"exam\u0000ples"           Internal Server Error [HTTP 500]                     (#6)
thư mục có symlink file -> /etc/hosts   {"documents":1,"chunks":1,"skipped":[],"unchanged":0} [HTTP 200]   (#5)

# API /ask
""                 422 string_too_short          2001 ký tự  422 string_too_long
"   "              200 not found                  2000 ký tự  200 not found
k=2.5              422                            k="3"      200 (pydantic ép kiểu)
tiếng Việt / tiếng Trung   200 not found
body 5 MB          422 (0.03 s)
DOCQA_EFFORT=turbo  /health 200, / 200, /ask 500, /chat 500                    (#7)

# API /chat
21 message         {"detail":{"code":"chat_history_invalid","message":"messages must contain at most 20 messages"}} [HTTP 422]
1001 message       422 (như trên)        19 message hợp lệ   200
2001 ký tự         {"detail":{"code":"chat_history_invalid","message":"message 1 is longer than 2000 characters"}} [HTTP 422]
role system / messages "hi" / null / content số / content dạng list   422 (pydantic)
bắt đầu bằng assistant   422 "messages must start with a user message"
kết thúc bằng assistant  422 "messages must end with a user message (the new question)"
hai user liền nhau       422 "message roles must alternate between user and assistant"
assistant rỗng           422 "message 2 is empty"
k=21                     422
câu nối tiếp "And what about the other one?" (không key) → 502 llm_auth (retriever có bằng chứng nhờ lượt trước)
câu hỏi + 1 000 000 dấu cách (body 1 MB) → 502 llm_auth (đã qua validate và tới bước gọi model)    (#4)

# Widget trên Chrome headless (Playwright, model giả trả HTML độc; chỉ là harness của QA, không sửa code)
xss flag: none
img/script injected in log: 0
[msg assistant] <img src=x onerror="window.__xss=1"><script>window.__xss=2</script> turns=0 | <b>warranty-policy.md</b> — “<img ...
[msg assistant] ... turns=2 | ...                       (lượt 2 nhận đúng 2 lượt lịch sử)
[msg assistant not-found] Not found in the provided documents.
[msg assistant] LLLL... (2500 ký tự)
[msg assistant error] message 8 is longer than 2000 characters      (#3)
[msg assistant error] message 8 is longer than 2000 characters      (#3, câu tiếp theo vẫn hỏng)
console: ['error: Failed to load resource: ... 404 (Not Found)', 'error: ... 422', 'error: ... 422']
(không có vi phạm CSP; Playwright `wait_for_function` dạng chuỗi bị CSP chặn với "'unsafe-eval' is not an allowed source", cho thấy CSP có hiệu lực)

# Điểm retriever (top-3, không áp ngưỡng) cho lỗi #1
'What is the warranty?'            top=[('warranty-policy.md', 1.45), ('delivery-process.md', 1.13), ...]
'What support plans do you have?'  top=[('support-plan-starter.md', 2.65), ('support-plan-pro.txt', 2.61), ...]
'What is the release process?'     top=[('release-checklist.pdf', 2.05), ...]
'How do you handle incidents?'     top=[('incident-response.md', 2.09), ...]
'What is in the security checklist?' top=[('security-checklist.txt', 2.65), ...]
'What is a change request?'        top=[('estimates-and-change-requests.md', 2.95), ...]
'What are the coding standards?'   top=[('coding-standards.md', 5.17)]          # 1 trong 2 câu qua cổng
'What is the warranty policy?'     top=[('warranty-policy.md', 3.42), ...]      # qua cổng

# Lỗi #9: trùng tên giữa hai thư mục
Ingested 10 documents, 23 chunks; skipped: none
Ingested 1 documents, 1 chunks; skipped: none          # other/warranty-policy.md ghi đè
Ingested 1 documents, 3 chunks (9 unchanged); skipped: none

# Wheel
$ uv build --wheel  →  docqa/static/index.html có trong wheel
```
