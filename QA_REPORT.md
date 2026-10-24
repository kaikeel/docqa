# QA Report — PF-20261025-docqa — Milestone 1 (v0.1.0), vòng 2 — 2026-10-25

**Kết luận: PASS** (phạm vi QA). Không còn lỗi blocker/major; còn 3 lỗi minor mới, không chặn bàn giao.

Điều kiện còn lại trước khi bàn giao, nằm ngoài phạm vi QA hoặc là bước sau gate:
- `SECURITY_REPORT.md` vòng 2 do `sec-devops` làm song song. DoD chỉ đạt khi báo cáo đó PASS.
- CI trên GitHub chưa chạy vì repo chưa push (T14, Q4/Q7). QA đã chạy local đúng từng bước của CI và tất cả xanh.
- `CHANGELOG` `[0.1.0]` và tag `v0.1.0` làm sau gate (T14).
- Các bước cần key thật để CEO chạy ở G3 (xem cuối báo cáo).

Người kiểm: `qa-reviewer` (độc lập với Eng). Commit kiểm: `320f25c`. Môi trường: macOS (arm64), Python 3.12.9,
uv 0.6.3, Docker Desktop, Google Chrome 155.0.8059.85 headless (Playwright qua `uvx`). Mọi lệnh chạy trên clone sạch
trong thư mục tạm, đã xoá sau khi kiểm. Image, volume và container do QA tạo cũng đã xoá.

**Không dùng API Anthropic thật:** không có key thật, mọi kịch bản có bằng chứng dùng model giả hoặc dừng ở `llm_auth`.
Có một lệnh CLI chạy với khoá giả `ANTHROPIC_API_KEY=sk-ant-fake-qa` để kiểm cách báo lỗi. Lệnh này có thể đã gửi 1
request bị từ chối 401 tới endpoint thật, không có chi phí.

## Lịch sử
- **Vòng 1 (`0de2e8e`): FAIL.** 5 lỗi major: #1 ngưỡng BM25 thô chặn câu hỏi ngắn, #2 Docker `--env-file` lỗi 500,
  #3 widget kẹt sau câu trả lời dài, #4 độn khoảng trắng vượt giới hạn `/chat`, #5 symlink file ra ngoài root.
  Thêm 11 lỗi minor (#6–#16). Security vòng 1 FAIL (M1, M2, M3).
- **Vòng sửa 1:** T19–T25 (ADR 0007, sửa ADR 0002 và 0004).
- **Vòng 2 (`320f25c`, báo cáo này):** cả 16 lỗi vòng 1 đã đóng (sửa, hoặc ghi vào README *Known limitations* với
  các lỗi chấp nhận là giới hạn). Còn 3 lỗi minor mới (R2-1..R2-3).

## Ma trận nghiệm thu

| Tiêu chí | Test / bằng chứng | Kết quả |
|---|---|---|
| AC1 ingest + ask trả lời có ≥ 1 trích dẫn đúng file | Tự động: `test_service.py`, `test_cli.py`, `test_llm.py` (request đúng nguyên văn, map citation). Thủ công không key: `docqa ingest examples/docs` cho 10 tài liệu / 23 chunk. Câu có bằng chứng (kể cả câu ngắn "What is the warranty?", coverage 1.00) đi tới bước gọi model, ra exit 2 `ANTHROPIC_API_KEY is missing or invalid.` | **Đạt phần tự động.** Phần API thật để CEO kiểm ở G3 |
| AC2 không có trong tài liệu → not found, không gọi API | `test_service.py::test_not_found_does_not_call_model`, `test_chat.py`, `test_eval.py`. Eval: dev chặn 8/8, holdout chặn 11/11. Bộ mới của QA chặn 13/17 (xem R2-1; 4 câu lọt qua cổng sẽ tới Claude, `found` vẫn cần citation) | **Đạt** (giới hạn ghi ở R2-1) |
| AC3 `POST /ask` schema, `GET /health` 200 | `test_api.py`. Thủ công qua uvicorn và Docker: `/health` trả `{"status":"ok"}`, `/ask` trả `{"answer","citations","found"}`. Mọi lỗi là JSON `{"detail":{"code","message"}}` (đã kiểm 400, 404, 405, 413, 422, 502) | **Đạt** |
| AC4 eval `--retrieval-only` không key, hit@3 ≥ 0.8 | `hit@3: 0.968 (30/31)` dev, `0.833 (20/24)` holdout, `0.867 (26/30)` trên bộ 47 câu mới của QA | **Đạt** |
| AC5 test offline, coverage ≥ 80%, ruff + mypy sạch | `243 passed`, `Total coverage: 99.81%`. `ruff check`, `ruff format --check`, `mypy src` đều sạch | **Đạt** |
| AC6 README từ máy sạch tới câu trả lời đầu tiên ≤ 10 phút (có Docker) | Lối uv với cache uv rỗng: clone → `uv sync --locked` → ingest → câu trả lời not-found mất **12 giây**. `docker build --no-cache` mất 17 giây. Đã chạy cả `docker run -e ANTHROPIC_API_KEY` và **`--env-file .env` (copy từ `.env.example`)**: `/health`, `/ingest`, `/ask` đúng như README. Volume giữ được index (lần chạy 2 trả `unchanged: 10`) | **Đạt phần không cần key.** Thời gian tới câu trả lời *thật* để CEO đo |
| AC7 không secret, key chỉ từ env, SECURITY_REPORT PASS | `git grep` mẫu `sk-ant-` dài trên toàn lịch sử: không thấy key thật. Image không có biến `ANTHROPIC*` có giá trị, không có `uv` (multi-stage), user `uid=10001`. `SECURITY_REPORT.md` vòng 2 do sec-devops làm | **Phần QA đạt.** Gate Security chờ sec-devops |
| AC8 `/chat` câu nối tiếp, history quá giới hạn → 422, widget chỉ `textContent` | `test_chat.py`, `test_api.py`, `test_widget.py`. Thủ công: 21 message → 422 `chat_history_invalid`, 101 message → 422 `invalid_request`, user 2001 ký tự → 422. Câu trả lời assistant 2500 ký tự → 200 (được cắt). **Chrome headless thật:** 3 câu gợi ý bấm được, câu trả lời 2654 ký tự rồi 13 lượt hỏi tiếp (vượt 20 message) không có bubble lỗi, câu "the other one" đưa vào model cả `support-plan-starter.md` và `support-plan-pro.txt`, HTML độc không chạy, Console trống, không lỗi CSP | **Đạt** (lỗi hiển thị nhỏ R2-2) |

## Lỗi

### Vòng 1: xác minh lại bằng chính kịch bản tái hiện cũ

| # | Mức (v1) | Kịch bản cũ → kết quả vòng 2 | Trạng thái |
|---|---|---|---|
| 1 | major | 10 câu "khách lần đầu" vòng 1: cả 10 câu nay qua cổng với đúng file đứng top (vd "What is the warranty?" coverage 1.00, "How do you handle incidents?" 0.66, "gitleaks", "SEV1" đều qua). Đã có bộ holdout riêng. QA thêm 47 câu mới: hit@3 0.867. Cổng vẫn là heuristic, giới hạn ghi ở R2-1 | **closed** |
| 2 | major | `cp .env.example .env && docker run --env-file .env`: `/health` 200, `/ingest` 200, `/ask` 502 `llm_auth` (đúng khi không có key). Nếu đặt nhầm `DOCQA_DB=./docqa.db`, container dừng ngay với `DocQA cannot start: cannot open the index ...` | **closed** |
| 3 | major | Chrome headless, model giả trả câu trả lời 2654 ký tự (có HTML), sau đó 13 lượt hỏi tiếp: 0 bubble lỗi. Server nhận lịch sử tối đa 18 lượt, mỗi lượt ≤ 2000 ký tự. Gọi thẳng `/chat` với assistant 2500 ký tự → 200 | **closed** |
| 4 | major | Câu hỏi + 200 000 dấu cách → 422 (trần schema 32 000 ký tự). Kèm 1 000 000 dấu cách (body 1 MB) → 413 `request_too_large`. Body chunked 300 KB không có Content-Length → 413. 1990 ký tự + 30 000 dấu cách ở giữa → 422 `message 1 is longer than 2000 characters` | **closed** |
| 5 | major | `tmpq/hosts.txt -> /etc/hosts` → `skipped: ["hosts.txt: symlink outside root"]`. Symlink trỏ vào trong root vẫn đọc được. Symlink tới `../.env` nằm trong root → `unsupported file type` (đuôi file được kiểm trên đích) | **closed** |
| 6 | minor | Path có NUL → 400 `{"code":"invalid_path"}` | **closed** |
| 7 | minor | `DOCQA_EFFORT=turbo` với uvicorn (local và Docker) → dừng lúc khởi động, exit 3, `DocQA cannot start: DOCQA_EFFORT must be one of ...` | **closed** (xem R2-3) |
| 8 | minor | 422 pydantic → `{"detail":{"code":"invalid_request","message":...,"errors":[...]}}`. 404/405 là JSON. README có bảng mã lỗi | **closed** |
| 9 | minor | Ingest `examples/docs`, rồi `other/` (có `warranty-policy.md` khác), rồi ingest lại `examples/docs` → `unchanged: 10`. Index giữ 2 tài liệu riêng (khoá theo đường dẫn tuyệt đối). Citation cùng tên: đã ghi trong README | **closed** |
| 10 | minor | `保修` vẫn ra not found. README *Known limitations → Languages* ghi rõ | **closed** (giới hạn đã ghi) |
| 11 | minor | README *One shared index* ghi rõ hành vi và khuyến nghị về `DOCQA_INGEST_ROOT` | **closed** (giới hạn đã ghi) |
| 12 | minor | pypdf vẫn in `invalid pdf header`, `EOF marker not found` ra stderr. README *PDFs* ghi rõ | **closed** (giới hạn đã ghi) |
| 13 | minor | `DOCQA_MIN_COVERAGE` = `nan`, `inf`, `-inf`, `1.5`, `-0.1`, `abc` → đều exit 1 kèm thông điệp rõ | **closed** |
| 14 | minor | Bảng milestone trong PROJECT.md ghi AC1–AC8. SPEC "Trạng thái: VERIFY", có `unchanged` và `invalid_path`. Q6 đã đóng bằng ADR 0007 | **closed** |
| 15 | minor | `Store.document_sha` đã giữ `self.lock` | **closed** |
| 16 | minor | `GET /favicon.ico` → 204. Console Chrome trống | **closed** |

### Lỗi mới vòng 2

| # | Mức độ | Mô tả | Cách tái hiện | Trạng thái |
|---|---|---|---|---|
| R2-1 | minor | **Cổng coverage để lọt câu "gần giống nhưng không có đáp án", và chặn vài câu diễn đạt khác.** Trên bộ 47 câu mới của QA, 4/17 câu không có đáp án vượt ngưỡng 0.5: "What does the Gold support plan cost?" 0.55, "How many hours does the Enterprise plan include?" 0.53, "What is the Starter plan price in euros?" 0.60, "How much does the handover meeting cost?" 0.69. Có 3/30 câu có đáp án bị chặn: "Can I cancel Pro anytime?" 0.27, "How fast do you answer emails on Starter?" 0.47, "Do you scan for leaked secrets?" 0.48. Quét ngưỡng 0.35–0.70 cho thấy không ngưỡng nào tách được hai nhóm trên dữ liệu mới, nên 0.5 vẫn là điểm cân bằng hợp lý. **Không đề nghị đổi ngưỡng.** README và ADR 0007 đã nói trung thực rằng đây là heuristic và có ca khó nhất. Nhưng câu trong README "'What is the price of the Enterprise plan?' is rejected, but only just" dễ khiến người đọc nghĩ loại câu này luôn bị chặn | `uv run docqa eval <bộ QA 47 câu> --retrieval-only --k 3` → `hit@3: 0.867 (26/30)`, `unanswerable rejected: 13/17`. Chi tiết từng câu ở phần lệnh. **Đề nghị (không bắt buộc):** thêm vào *Known limitations* một câu kiểu "some such questions pass the gate (e.g. 'How many hours does the Enterprise plan include?') and then rely on Claude to answer 'not found'". CEO nên thử 1–2 câu này ở G3 để xem Claude có trả not found hay không | open (không chặn) |
| R2-2 | minor | Widget: chuỗi dài không có khoảng trắng (URL dài, đường dẫn, mã) tràn ra ngoài bubble theo chiều ngang. `.msg` có `white-space: pre-wrap` nhưng thiếu `overflow-wrap: anywhere`. Chỉ ảnh hưởng hiển thị, không ảnh hưởng chức năng | Chrome headless, model giả trả `"L" * 2500` → text vượt ra ngoài khung trắng (ảnh chụp trong lúc kiểm). Bubble user với `"x" * 2000` bị tương tự | open (không chặn) |
| R2-3 | minor | Khi khởi động API lỗi (env sai, index hỏng hoặc cũ), log có dòng thông điệp rõ trước, rồi một traceback Starlette ~10 dòng và dòng `RuntimeError: DocQA cannot start: ...`. Thông điệp vẫn đúng và rõ, chỉ hơi nhiễu | `docker run --rm -e DOCQA_EFFORT=turbo docqa` | open (cosmetic) |

### README: kết quả làm theo như người lạ
1. **Đúng nguyên văn:** quick start uv, ví dụ not-found, output của hai lệnh eval (39 / 0.968 / 8/8 và 35 / 0.833 / 11/11),
   các lệnh test, `docker run -e`, **`--env-file .env`**, các lệnh curl, `-v docqa-data:/data`, image non-root,
   bảng mã lỗi (đã kiểm từng mã không cần key), các câu hỏi gợi ý (cả 6 câu qua cổng, file đúng ở top-1), và ví dụ
   "What is the warranty on hardware?" bị chặn (0.23).
2. **Chờ hiện thực:** `git clone https://github.com/kaikeel/docqa.git` chỉ chạy được khi repo đã push (T14). Repo private
   thì người lạ không clone được cho tới Milestone 2. QA kiểm bằng cách clone repo local.
3. **Môi trường của QA, không phải lỗi:** máy QA có `VIRTUAL_ENV` của pyenv nên `uv run` in cảnh báo
   `VIRTUAL_ENV=... does not match`. Không ảnh hưởng kết quả.

### Code review (theo `04-qa/checklists/code-review.md`)
- [x] Đúng scope. Diff `0de2e8e..320f25c` chỉ chạm các file cần cho T19–T25 (src, tests, docs, Docker, CI, Dependabot).
  Không thêm tính năng ngoài yêu cầu.
- [x] Logic đúng với case biên, xử lý lỗi rõ ràng: toàn bộ kịch bản vòng 1 và các case biên mới ở trên. Coverage tính
  bằng FTS5 `MATCH`, cùng tokenizer với tìm kiếm. `min_coverage` kiểm `0 ≤ x ≤ 1` (loại cả NaN). `prepare_history`
  strip trước khi đo và gửi đi. Middleware 413 đếm được cả body chunked.
- [x] Test có ý nghĩa: có test riêng cho độn khoảng trắng (`test_chat.py::test_padding_does_not_hide_a_long_user_message`,
  `test_api.py::test_whitespace_padding_is_rejected_before_parsing`), cắt câu trả lời cũ, symlink, NUL, khởi động lỗi,
  ghim SHA của CI (`test_ci.py`), câu gợi ý của widget đi qua cổng. Còn thiếu test widget trên trình duyệt (CI chỉ có
  test tĩnh); QA đã bù bằng Chrome headless thủ công.
- [x] Tên rõ, không trùng lặp đáng kể.
- [x] Không có vòng lặp tốn kém vô lý: coverage tốn 1 truy vấn FTS5 cho mỗi từ nội dung của câu hỏi; câu hỏi bị giới
  hạn 2000 ký tự ở API (ADR 0007 đo ~10 ms).
- [x] Dependency pin, có `uv.lock`. Action CI ghim theo SHA kèm comment tag. Dependabot cho github-actions.
- [x] Không có secret, không log key. `grep -rnE 'TODO|FIXME|XXX|HACK|breakpoint\(|pdb\.|print\(' src scripts tests` → rỗng.

### Kiểm độ bền cổng bằng chứng (bộ câu hỏi mới của QA)
Bộ 47 câu (30 có đáp án, 17 không) viết **trước khi** tính bất kỳ con số nào, không trùng câu nào với dev hoặc holdout
(đã kiểm bằng script). Gồm câu tự nhiên ngắn ("warranty", "Starter plan price", "Do you use emoji?"), câu diễn đạt khác
("Can the handover call be recorded?", "How do you number versions?") và câu gần giống nhưng không có đáp án (gói
Premium/Gold/Enterprise/Platinum, SEV4, giá bằng euro, Azure, Java, NDA).

| Bộ | hit@3 | Chặn câu không có đáp án |
|---|---|---|
| dev `eval.jsonl` (Eng dùng để hiệu chỉnh) | 0.968 (30/31) | 8/8 |
| holdout `eval_holdout.jsonl` | 0.833 (20/24) | 11/11 |
| **QA vòng 2 (mới, 47 câu)** | **0.867 (26/30)** | **13/17 (76%)** |

Đánh giá rủi ro của ngưỡng sát dữ liệu: trên dev, khoảng trống giữa hai nhóm rất hẹp (0.42 so với 0.43), nhưng trên
holdout mọi ngưỡng từ 0.45 tới 0.55 cho cùng kết quả. Trên bộ mới, giá trị coverage của hai nhóm chồng lên nhau trong
khoảng 0.47–0.60. Dịch ngưỡng lên 0.6 sẽ chặn thêm 2 câu không có đáp án nhưng mất 2 câu có đáp án (và mất 2 câu trên
dev). Dịch xuống 0.45 thì được thêm 2 câu có đáp án nhưng lọt thêm 1 câu không có đáp án. Vì vậy 0.5 hợp lý, không cần
đổi. Rủi ro thật: khoảng 1/4 số câu "gần giống" sẽ tới Claude. Hậu quả là tốn 1 lời gọi API, và kết quả phụ thuộc
vào việc Claude tự nói not found (`found` vẫn cần citation). README và ADR 0007 đã nói đây là heuristic, nên QA không coi
là lỗi chặn (R2-1).

### Definition of Done
| Mục | Trạng thái |
|---|---|
| Mọi AC có bằng chứng đạt | Đạt phần tự động và thủ công không cần key. AC1 và phần thời gian của AC6 với API thật để CEO kiểm ở G3. AC7 chờ Security |
| CI xanh, lint sạch, không blocker/major | Lint, format, mypy, test, eval sạch khi chạy local đúng các bước CI. Không còn blocker/major. CI GitHub chờ push (T14) |
| README chạy từ máy sạch | Đạt cả lối uv và Docker (`-e` và `--env-file`), chưa tính URL clone (chờ push) |
| `SECURITY_REPORT.md` PASS | Ngoài phạm vi QA (sec-devops đang làm vòng 2) |
| CHANGELOG cập nhật, tag release | `[Unreleased]` đủ T1–T25 (Added/Changed/Fixed/Security). `[0.1.0]` và tag làm sau gate (T14) |
| Không code thừa / TODO / debug print / secret | Đạt |

### Để lại cho CEO ở G3 (cần key của CEO)
1. **AC1:** `docqa ask` và `ask --json` với một câu *answerable* trong `examples/eval.jsonl` → `found=true`, ≥ 1 citation
   có `source` đúng `expected_sources`, `quote` là trích nguyên văn. Thử thêm "What is the warranty?" (trước đây bị chặn).
2. **AC6:** bấm giờ từ lúc clone (URL thật sau khi push) tới câu trả lời **thật** đầu tiên theo lối uv, rồi chạy lối Docker
   (`-e` hoặc `--env-file`). Phần không cần key QA đo được: 12 giây (uv, cache rỗng), 17 giây (`docker build --no-cache`).
3. **AC8 trên widget:** bấm câu gợi ý "What support plans do you have?", rồi gõ "And what about the other one?" → câu trả
   lời có trích dẫn đúng file. F12 → Console không có lỗi. Thử thêm một câu dài có URL để xem R2-2 có làm xấu giao diện không.
4. **R2-1:** hỏi "How many hours does the Enterprise plan include?" hoặc "What does the Gold support plan cost?" → kỳ vọng
   Claude trả not found (`found=false`) hoặc nói rõ là tài liệu không có gói đó, không lấy số của gói Pro/Starter.
5. Lỗi thật (key sai) → 502 `llm_auth`.

## Kết quả lệnh đã chạy

```
$ git clone "/Users/sine/Self company/projects/active/PF-20261025-docqa" docqa && cd docqa && git log --oneline -1
320f25c Merge branch 'fix/t14-status'
$ time (UV_CACHE_DIR=<thư mục rỗng> uv sync --locked && uv run docqa ingest examples/docs && uv run docqa ask "What is the airspeed of an unladen swallow?")
 + uvicorn==0.54.0
Ingested 10 documents, 23 chunks; skipped: none
Not found in the provided documents.
... 12.151 total

$ uv run ruff check .
All checks passed!
$ uv run ruff format --check .
34 files already formatted
$ uv run mypy src
Success: no issues found in 13 source files
$ uv run pytest --cov=docqa --cov-fail-under=80
Name                     Stmts   Miss Branch BrPart  Cover   Missing
--------------------------------------------------------------------
src/docqa/__init__.py        1      0      0      0   100%
src/docqa/api.py           168      0     14      1    99%   63->68
src/docqa/chat.py           42      0     26      0   100%
src/docqa/cli.py            74      0     10      0   100%
src/docqa/config.py         60      0     12      0   100%
src/docqa/errors.py         33      0      0      0   100%
src/docqa/eval.py           72      0     20      0   100%
src/docqa/ingest.py        128      0     50      0   100%
src/docqa/llm.py           101      0     28      0   100%
src/docqa/models.py         33      0      0      0   100%
src/docqa/retriever.py      52      0     14      0   100%
src/docqa/service.py        50      0     10      0   100%
src/docqa/store.py          67      0      4      1    99%   75->77
--------------------------------------------------------------------
TOTAL                      881      0    188      2    99%
Required test coverage of 80% reached. Total coverage: 99.81%
243 passed in 2.76s

$ uv run docqa eval examples/eval.jsonl --retrieval-only --k 3
cases: 39
hit@3: 0.968 (30/31 answerable)
unanswerable rejected: 8/8 (retrieval found nothing)
$ uv run docqa eval examples/eval_holdout.jsonl --retrieval-only --k 3
cases: 35
hit@3: 0.833 (20/24 answerable)
unanswerable rejected: 11/11 (retrieval found nothing)
$ uv run docqa eval examples/eval.jsonl --retrieval-only          # lệnh đúng nguyên văn AC4
cases: 39
hit@3: 0.968 (30/31 answerable)
unanswerable rejected: 8/8 (retrieval found nothing)
$ uv run docqa eval <bộ QA vòng 2, 47 câu> --retrieval-only --k 3
cases: 47
hit@3: 0.867 (26/30 answerable)
unanswerable rejected: 13/17 (retrieval found nothing)

# Chi tiết bộ QA vòng 2 (coverage của chunk top-1, ngưỡng 0.5)
HIT       cov=1.00 'How long is the warranty?'                     HIT  cov=1.00 'Is the warranty 7 days?'
HIT       cov=1.00 'When does the warranty start?'                 HIT  cov=1.00 'Does the warranty cover new features?'
HIT       cov=1.00 'How much does Pro cost per month?'             HIT  cov=1.00 'Starter plan price'
GATE-MISS cov=0.27 'Can I cancel Pro anytime?'                     HIT  cov=1.00 'Is there a minimum term for the Pro plan?'
GATE-MISS cov=0.47 'How fast do you answer emails on Starter?'     HIT  cov=1.00 'Which repositories get security updates?'
HIT       cov=0.59 'What happens during a SEV1?'                   HIT  cov=0.71 'Who sends status updates during an incident?'
HIT       cov=1.00 'How do you number versions?'                   HIT  cov=1.00 'Do you tag releases?'
HIT       cov=1.00 'Do I need to approve change requests in writing?'  HIT cov=1.00 'Is renaming a label a change request?'
RANK-MISS cov=1.00 'How are hours billed after the warranty?'  top=[support-plan-pro.txt, support-plan-starter.md, support-plan-pro.txt]
HIT       cov=1.00 'Do you use TypeScript?'                        HIT  cov=0.73 'Are tests allowed to call paid APIs?'
HIT       cov=1.00 'Which time zone are business days in?'         HIT  cov=0.65 'Do you use emoji?'
HIT       cov=0.57 'Who sends quotes?'                             GATE-MISS cov=0.48 'Do you scan for leaked secrets?'
HIT       cov=1.00 'How do you prevent path traversal?'            HIT  cov=1.00 'Is the handover zip built from a branch?'
HIT       cov=1.00 'warranty'                                      HIT  cov=1.00 'postmortem'
HIT       cov=0.68 'Can the handover call be recorded?'            HIT  cov=1.00 "What's included in Pro?"
HIT       cov=1.00 'Do you send credentials by email?'
rejected  cov=0.30 'How much is the Premium plan?'                 LEAK cov=0.55 'What does the Gold support plan cost?'
rejected  cov=0.49 'How long is the warranty on time-and-materials projects?'
rejected  cov=0.13 'Do you offer a yearly plan discount?'          rejected cov=0.43 'What is the SEV4 response time?'
rejected  cov=0.30 'Do you support Azure?'                         LEAK cov=0.60 'What is the Starter plan price in euros?'
rejected  cov=0.00 'Do you sign NDAs?'                             rejected cov=0.37 'What is your phone number?'
LEAK      cov=0.69 'How much does the handover meeting cost?'      rejected cov=0.18 'Who is the CEO of Kaikeel?'
rejected  cov=0.23 'Do you build mobile games?'                    rejected cov=0.13 'What is the penalty for a late delivery?'
LEAK      cov=0.53 'How many hours does the Enterprise plan include?'  rejected cov=0.28 'Do you use Java?'
rejected  cov=0.26 'What is the SLA for Platinum customers?'       rejected cov=0.42 'Is the Pro plan available for hardware support?'

# Quét ngưỡng (hit / chặn)
eval.jsonl   t=0.35: 31/31 7/8 | 0.40: 31/31 7/8 | 0.45: 30/31 8/8 | 0.50: 30/31 8/8 | 0.55: 30/31 8/8 | 0.60: 28/31 8/8 | 0.70: 27/31 8/8
holdout      t=0.35: 20/24 10/11 | 0.40: 20/24 10/11 | 0.45: 20/24 11/11 | 0.50: 20/24 11/11 | 0.55: 20/24 11/11 | 0.60: 19/24 11/11 | 0.70: 19/24 11/11
qa_r2        t=0.35: 28/30 9/17 | 0.40: 28/30 10/17 | 0.45: 28/30 12/17 | 0.50: 26/30 13/17 | 0.55: 26/30 14/17 | 0.60: 24/30 15/17 | 0.70: 22/30 17/17

# Câu hỏi gợi ý trong README và widget
HIT cov=1.00 'What is the warranty?'   HIT cov=1.00 'How quickly are critical defects fixed?'   HIT cov=1.00 'What support plans do you have?'
HIT cov=0.66 'How do you handle incidents?'   HIT cov=1.00 'What is a change request?'   HIT cov=1.00 'How often is a rollback drill rehearsed?'
rejected cov=0.23 'What is the warranty on hardware?'

# Docker
$ docker build --no-cache -q -t docqa-qa2 .          → 16.9 s, image 289MB
$ cp .env.example .env && docker run -d --rm -p 127.0.0.1:8091:8000 --env-file .env docqa-qa2
{"status":"ok"} [HTTP 200]
{"documents":10,"chunks":23,"skipped":[],"unchanged":0} [HTTP 200]                                  # /ingest
{"detail":{"code":"llm_auth","message":"ANTHROPIC_API_KEY is missing or invalid."}} [HTTP 502]     # /ask có bằng chứng
{"answer":"Not found in the provided documents.","citations":[],"found":false} [HTTP 200]          # /ask swallow
{"detail":{"code":"llm_auth",...}} [HTTP 502]                                                      # "What is the warranty?"
 [HTTP 204]                                                                                        # /favicon.ico
content-security-policy: default-src 'none'; script-src 'sha256-G/Fw7dgUpQ0zq0NxtXogF8qEKaUprcGVg6GzDk3ni80='; style-src 'sha256-aFMFmeXwuTyCwGgTMI/ujy4R/LFJCqFkFJj4s3wNxZY='; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'
uid=10001(docqa) gid=10001(docqa) groups=10001(docqa)
ls /usr/local/bin | grep -c uv → 0 ; env | grep -c 'ANTHROPIC_API_KEY=.' → 0
$ docker run --rm -e DOCQA_DB=./docqa.db docqa-qa2
RuntimeError: DocQA cannot start: cannot open the index docqa.db (unable to open database file); set DOCQA_DB to a writable location
$ docker run --rm -e DOCQA_EFFORT=turbo docqa-qa2        → exit 3
DocQA cannot start: DOCQA_EFFORT must be one of low, medium, high, xhigh, max, got 'turbo'
ERROR:    Traceback (most recent call last): ... (R2-3)
# -e ANTHROPIC_API_KEY + -v docqa-qa2-vol:/data, chạy 2 lần
{"documents":10,"chunks":23,"skipped":[],"unchanged":0}
{"documents":0,"chunks":0,"skipped":[],"unchanged":10}

# API (uvicorn local) — kịch bản vòng 1
#5  {"documents":1,"chunks":1,"skipped":["hosts.txt: symlink outside root"],"unchanged":1} [HTTP 200]
#6  {"detail":{"code":"invalid_path","message":"The path is not valid."}} [HTTP 400]
#8  {"detail":{"code":"invalid_request","message":"question: String should have at least 1 character","errors":[...]}} [HTTP 422]
    {"detail":{"code":"invalid_request","message":"1: JSON decode error",...}} [HTTP 422]
    {"detail":{"code":"invalid_request","message":"extra: Extra inputs are not permitted",...}} [HTTP 422]
    {"detail":{"code":"not_found","message":"Not Found"}} [HTTP 404]
    {"detail":{"code":"method_not_allowed","message":"Method Not Allowed"}} [HTTP 405]
#9  {"documents":10,...} → other/: {"documents":1,...} → examples/docs lại: {"documents":0,"chunks":0,"skipped":[],"unchanged":10}
    documents: 11|.../examples/docs/warranty-policy.md|warranty-policy.md ; 12|.../other/warranty-policy.md|warranty-policy.md
#4  câu hỏi + 200 000 dấu cách (200 098 byte): {"detail":{"code":"invalid_request","message":"messages.0.content: String should have at most 32000 characters",...}} [HTTP 422]
    + 1 000 000 dấu cách: {"detail":{"code":"request_too_large","message":"The request body must be at most 262144 bytes."}} [HTTP 413]
    1990 ký tự + 30 000 dấu cách + "warranty": {"detail":{"code":"chat_history_invalid","message":"message 1 is longer than 2000 characters"}} [HTTP 422]
    body chunked 300 KB không Content-Length → [HTTP 413]
#3  assistant 2500 ký tự trong lịch sử → {"answer":"Not found in the provided documents.","citations":[],"found":false} [HTTP 200]
    user 2001 ký tự → 422 chat_history_invalid ; 21 message → 422 "at most 20 messages" ; 101 message → 422 invalid_request
#7  DOCQA_EFFORT=turbo uv run uvicorn docqa.api:app → exit=3, "DocQA cannot start: DOCQA_EFFORT must be one of ..."
    DOCQA_DB=/nonexistent/dir/x.db → exit=3, "DocQA cannot start: cannot open the index /nonexistent/dir/x.db ([Errno 30] Read-only file system: '/nonexistent'); ..."
#13 DOCQA_MIN_COVERAGE=nan  → Error: DOCQA_MIN_COVERAGE must be a number between 0 and 1, got 'nan'  exit=1
    -inf / inf / 1.5 / -0.1 → tương tự, exit=1 ; abc → "must be a number, got 'abc'"  exit=1
symlink tmpq2/notes.txt -> ../.env (trong root) → skipped: ['notes.txt: unsupported file type']

# Widget — Google Chrome 155.0.8059.85 headless (Playwright, channel="chrome"); server = docqa.api + model giả của QA
# (model giả: câu có "warranty" → "<img onerror><script>..." + 2500 ký tự "L"; câu khác → "Answer #n from <file>."; citation quote bắt đầu bằng "<b>")
title: Kaikeel DocQA
suggestion buttons: ['What is the warranty?', 'What support plans do you have?', 'How do you handle incidents?']
[1] (bấm gợi ý 1) long answer chars: 2654 classes: msg assistant
    injected img/script in log: 0 xss: none
[2] (bấm gợi ý 2) Answer #2 from support-plan-starter.md. | support-plan-starter.md — "<b># Kaikeel Handbook Lite: Starter Support Plan ...
[3] (gõ "And what about the other one?") Answer #3 from support-plan-starter.md. ...
[4] after 13 turns: error bubbles = 0; not-found bubbles = 3
[5] (bấm gợi ý 3) Answer #11 from incident-response.md.
[6] gõ 2100 ký tự → input maxlength cắt còn 2000 → msg assistant not-found
[7] after that: msg assistant
total error bubbles: 0
server calls: 12 max history_len: 18 max hist chars: 2000
call[2] sources (other one): ['support-plan-starter.md', 'support-plan-pro.txt', 'support-plan-pro.txt', 'delivery-process.md', 'release-checklist.pdf']
console: []
pageerrors: [] requestfailed: []
non-2xx responses: []
# CSP có hiệu lực và luồng lỗi mạng (lỗi Console bên dưới do QA chủ động gây ra)
inline script ran: blocked
offline bubble: The server could not be reached. Please try again.
after recovery: Answer #13 from incident-response.md. | incident-response.md — msg assistant
500 bubble: Internal server error.
after 500: msg assistant
console: ["error: Executing inline script violates the following Content Security Policy directive 'script-src 'sha256-G/Fw...'' ... The action has been blocked.",
          "error: Loading the image 'https://example.com/x.png' violates ... \"img-src 'self'\". The action has been blocked.",
          "error: Failed to load resource: net::ERR_FAILED", "error: Failed to load resource: the server responded with a status of 500 (Internal Server Error)"]

# CLI case biên
== empty dir        Ingested 0 documents, 0 chunks; skipped: none                       exit=0
== nonexistent      Error: .../edge/nope is not a directory                             exit=1
== file             Error: README.md is not a directory                                 exit=1
== bad pdfs
invalid pdf header: b'not a'
EOF marker not found
EOF marker not found
Ingested 1 documents, 1 chunks; skipped: garbage.pdf: unreadable PDF (PdfStreamError), truncated.pdf: unreadable PDF (PdfStreamError), zero.pdf: unreadable PDF (EmptyFileError)   exit=0
== unicode (vi/zh/emoji)  Ingested 3 documents, 3 chunks; skipped: none                 exit=0
== re-ingest        Ingested 0 documents, 0 chunks (3 unchanged); skipped: none         exit=0
== ask "bao hanh du an gia co dinh" / "bảo hành bao lâu" / "rocket 🚀"   Error: ANTHROPIC_API_KEY is missing or invalid.  exit=2 (có bằng chứng)
== ask "保修"        Not found in the provided documents.                                exit=0 (#10, đã ghi giới hạn)
== ask "" / "??? *** NEAR( OR AND" / 108 000 ký tự   Not found in the provided documents.   exit=0
== eval file thiếu  Error: cannot read nope.jsonl: FileNotFoundError                     exit=1
== eval sai dạng    Error: line 1: 'question' must be a non-empty string                 exit=1
== ask --k 0        Invalid value for '--k': 0 is not in the range 1<=x<=20.             exit=2
== index từ bản 0de2e8e (schema 0)
Error: The index .../old.db was created by another DocQA version (schema 0, expected 3); delete .../old.db and ingest again.   exit=1
(uvicorn với index đó: "DocQA cannot start: The index ... was created by another DocQA version ...")
== khoá giả        Error: ANTHROPIC_API_KEY is missing or invalid.                       exit=2

# Code review
$ grep -rnE 'TODO|FIXME|XXX|HACK|breakpoint\(|pdb\.|print\(' src scripts tests     → (rỗng)
$ git diff --name-only 0de2e8e 320f25c   → .env.example .github/* CHANGELOG.md Dockerfile PROJECT.md QA_REPORT.md README.md SECURITY_REPORT.md TASKS.md docs/* examples/eval*.jsonl src/docqa/{api,chat,cli,config,ingest,retriever,service,store}.py src/docqa/static/index.html tests/*
```
