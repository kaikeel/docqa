# SECURITY_REPORT — PF-20261025-docqa v0.1.0

- Người kiểm: `sec-devops` (Digital Worker) · Ngày: 2026-10-25
- Phạm vi: nhánh `main` @ `0de2e8e` (toàn bộ lịch sử git: 69 commit trên 22 ref + 4 commit dangling), image
  Docker build từ `git archive HEAD`, `.github/workflows/ci.yml`.
- Checklist: `05-devops-security/checklists/security.md` + yêu cầu bổ sung của PMO (AC7, API, widget, Docker, CI).
- Ràng buộc: không gọi API Anthropic thật, không dùng key thật. Mọi kiểm tra động chạy offline với `FakeAnswerModel`
  qua FastAPI `TestClient` (socket bị chặn), và một container chạy local trên `127.0.0.1` không có key.

## Kết luận: **FAIL** (không có critical/high; 2 lỗi medium chặn gate)

Không có secret trong repo hay lịch sử git, dependency Python không có CVE, SAST không có cảnh báo high, Docker chạy
non-root và không mang `.env`/DB vào image. Gate **FAIL** vì hai mục kiểm tay mà PMO yêu cầu rõ không đạt:

- **M1**: file symlink nằm *trong* `DOCQA_INGEST_ROOT` trỏ ra ngoài vẫn được đọc, đánh chỉ mục và trích dẫn nguyên văn.
- **M2**: giới hạn độ dài tin nhắn `/chat` bị vượt qua bằng cách đệm khoảng trắng (đo trên `strip()` nhưng gửi bản
  gốc cho model); request body không có giới hạn kích thước.

Cả hai sửa nhỏ (ước lượng < 1 giờ kèm test). Sửa xong M1, M2 thì chạy lại gate. M3 (ghim action theo SHA) nên làm
trước khi public repo, nhưng riêng nó không chặn gate.

## Bảng kiểm

| # | Mục | Lệnh / cách kiểm | Kết quả thật (rút gọn) | Trạng thái |
|---|---|---|---|---|
| 1a | Secret scan, toàn bộ lịch sử | `gitleaks detect --source . --log-opts=--all -v` (gitleaks 8.30.1) | `48 commits scanned … no leaks found` | PASS |
| 1b | Secret scan, cả diff merge | `gitleaks detect --source . --log-opts="--all -m"` | `69 commits scanned … no leaks found` | PASS |
| 1c | Secret scan, commit dangling (stash cũ, không push) | `git fsck --lost-found` → 4 commit; `gitleaks detect --log-opts=<sha>` từng cái | `no leaks found` ×4 | PASS |
| 1d | Secret scan, cây làm việc | `gitleaks detect --source . --no-git -v` | `no leaks found` | PASS |
| 1e | `.env` trong lịch sử | `git log --all --name-only --format= \| grep -E '(^\|/)\.env'` | chỉ `.env.example` (giá trị rỗng) | PASS |
| 1f | Chuỗi key giả trong test | `grep -rn sk-ant src tests …` | `sk-ant-secret`, `sk-ant-test-should-not-appear` trong `tests/` — gitleaks **không** báo (rule Anthropic cần dạng `sk-ant-api03-…` đủ dài) → không có false positive, chưa cần allowlist | PASS |
| 1g | Tác giả commit | `git log --all --format='%an <%ae>'` | 69/69 là `Sine <…@users.noreply.github.com>` — không lộ email cá nhân/công ty | PASS |
| 2 | Dependency CVE (lockfile) | `uv export --frozen --no-emit-project > req.txt` (có hash, gồm cả dev) → `uvx pip-audit -r req.txt --require-hashes --disable-pip` (pip-audit 2.10.1), nguồn PyPI và `-s osv` | `No known vulnerabilities found` (cả hai nguồn, 47 gói; runtime 32 gói) | PASS |
| 3a | SAST Python | `uvx bandit -r src` (bandit 1.9.4); thêm `uvx bandit -r scripts` | `No issues identified.` 1046 LOC; High 0 / Medium 0 / Low 0 | PASS |
| 3b | SAST đa ngôn ngữ | `uvx semgrep scan --metrics=off --config p/python --config p/owasp-top-ten --config p/security-audit --config p/secrets --config p/dockerfile --config p/github-actions --config p/javascript src Dockerfile .github` (semgrep 1.182.1, 281 rule) | 3 phát hiện, cùng rule `github-actions-mutable-action-tag`, severity **WARNING** (không có ERROR) → xem M3. `src/` và `index.html`: 0 | PASS (có M3) |
| 3c | `semgrep --config auto` | `uvx semgrep scan --config auto --metrics=off` | **Chưa chạy**: semgrep từ chối `auto` khi tắt metrics; không bật metrics để tránh gửi thông tin repo ra ngoài. Đã thay bằng 7 ruleset tường minh ở 3b | CHƯA CHẠY (đã thay thế) |
| 4a | Validate input `/ask` | probe `TestClient` | `question` 2001 ký tự → 422, rỗng → 422, `k=1000` → 422, field lạ → 422, JSON hỏng → 422 | PASS |
| 4b | Validate input `/chat` | probe | 21 tin → 422, 2001 ký tự → 422, 200 000 tin → 422; **nhưng** `"refund window " + 5 000 000 khoảng trắng` → **200**, model nhận câu hỏi dài 5 000 014 ký tự | **FAIL (M2)** |
| 4c | Kích thước request | đọc code + probe | Không có giới hạn body (uvicorn/FastAPI mặc định không giới hạn); `ChatMessage.content` và `messages` không có `max_length` ở Pydantic nên toàn bộ body được parse trước khi kiểm | **FAIL (M2)** |
| 4d | Path traversal `/ingest` | probe với root tạm | `../outside`, `/etc`, `docs/../../outside`, symlink thư mục `linkdir` → 400 `path_outside_root`; symlink thư mục con không bị duyệt (`os.walk` không follow) | PASS |
| 4e | Symlink file ra ngoài root | probe: `docs/link.md -> ../outside/secret.md` rồi `POST /ingest {"path":"docs"}`, `POST /ask` | `store sources: ['a.md', 'link.md']`; `/ask` trả `"quote":"TOPSECRET outside root password hunter2 refund"` | **FAIL (M1)** |
| 4f | Ký tự lạ trong path | probe `{"path":"docs\u0000"}` | 500 `Internal Server Error` (không lộ stack trace) | L1 |
| 4g | SQL tham số hoá | đọc `store.py`, `retriever.py` | Mọi câu SQL dùng `?`; truy vấn FTS5 được dựng từ token `\w+`, mỗi token bọc `"…"` và nhân đôi `"` | PASS |
| 4h | Cú pháp FTS5 do người dùng nhập | probe 16 chuỗi: `"`, `'`, `*`, `NEAR(a b)`, `a AND OR NOT`, `refund" OR "x`, `^refund`, `col:refund`, `(((`, `--`, `;DROP TABLE chunks;--`, `\x00`, emoji, dấu, 2000×`a`, `{} [] \ / % _` | 16/16 → 200, không lỗi 500, không thay đổi DB | PASS |
| 4i | XSS widget | đọc `static/index.html`, header `GET /` | Chỉ `textContent`/`createTextNode`, không `innerHTML`; CSP `default-src 'none'; script-src 'sha256-…'; style-src 'sha256-…'; connect-src 'self'; … frame-ancestors 'self'`; `X-Content-Type-Options: nosniff`; `Referrer-Policy: no-referrer` | PASS |
| 4j | CORS / CSRF | probe preflight từ `https://evil.example` | `OPTIONS /chat` → 405, không có header `Access-Control-*`; POST `text/plain` (simple request) → 422 (cần `application/json` nên không bị CSRF dạng form) ; không có cookie/session | PASS |
| 4k | Lỗi không lộ stack trace / đường dẫn | probe: model ném `RuntimeError("/Users/secret/path … sk-ant-api03-FAKE")` | 500 `Internal Server Error` (text thuần), không chứa đường dẫn hay chuỗi key; lỗi LLM → 502 JSON `{"code","message"}` cố định | PASS |
| 4l | Key không vào log/response | probe: đặt `ANTHROPIC_API_KEY=sk-ant-api03-PROBEKEY…`, mạng bị chặn, log root ở DEBUG | 502 `llm_unavailable`; `key in response: False`, `key in logs: False` (145 dòng log). Thiếu key → 502 `llm_auth`. `Settings` không chứa key; `llm.py` chỉ log status/request_id/tên lớp lỗi | PASS |
| 4m | Prompt injection từ tài liệu | đọc `llm.py`, ADR 0003/0004 | Xem L6 — rủi ro được chấp nhận, có giảm thiểu một phần | Ghi nhận |
| 4n | Auth / mật khẩu / crypto | đọc code | Không có auth, không có mật khẩu, không tự viết crypto (chỉ `hashlib.sha256` cho hash nội dung và hash CSP) | N/A |
| 4o | Scraping / dữ liệu cá nhân | đọc code | Không scrape; không lưu dữ liệu người dùng (chat stateless, chỉ lưu tài liệu do người vận hành ingest) | PASS |
| 5a | Docker non-root | `docker build` từ `git archive HEAD`; `docker run … id` | `uid=10001(docqa)`; `/app` thuộc root, `touch /app/x` → `Permission denied`; chỉ `/data` ghi được | PASS |
| 5b | `.dockerignore` | build với `.env` (chứa `sk-ant-PLANTED`), `.env.probe`, `stray.db` cài sẵn trong context; `find / -name ".env*" -o -name "*.db"`; `grep -rl PLANTED /app` | Không tìm thấy gì; `tests/ docs/ scripts/ .git/ .github/` không có trong image | PASS |
| 5c | Image tối thiểu | `docker history`, `du` | `python:3.12-slim`, 81 MB nén; còn **uv cache `/root/.cache/uv` 41 MB** và binary `uv` 30 MB trong image | L2 |
| 5d | Trivy image | `trivy image --scanners vuln,secret,misconfig docqa:secgate` (trivy 0.76.1) | OS (debian 13.7): HIGH 44 mục / 8 CVE, **tất cả chưa có bản sửa** (`affected` 43, `fix_deferred` 1); `--ignore-unfixed --severity HIGH,CRITICAL` → 0. Python: chỉ `pip 25.0.1` của base image, 5 MEDIUM 1 LOW. Secret: 13 hit `gcp-service-account` CRITICAL = **false positive** (docstring `{"type": "service_account"}` trong SDK `anthropic`, ở `.venv` và uv cache). Misconfig Dockerfile: 0 | PASS (có L2, L3) |
| 5e | Trivy config repo | `trivy config --severity HIGH,CRITICAL .` | `Dockerfile … 0` | PASS |
| 5f | Container chạy thật | `docker run -p 127.0.0.1:18080:8000`, `curl` | `/health` 200; `/ingest {"path":"/etc"}` → 400; `/ingest "."` không ingest `.venv` (hidden); log uvicorn không chứa body | PASS |
| 6a | CI `permissions` | đọc `ci.yml` | `permissions: contents: read` ở cấp workflow; không có job nào nâng quyền | PASS |
| 6b | CI không dùng secret | đọc `ci.yml` | Không có `secrets.*`; `ANTHROPIC_API_KEY: ""` ép rỗng; trigger `push main` + `pull_request` (không `pull_request_target`) | PASS |
| 6c | CI action ghim version | đọc `ci.yml` + semgrep | `actions/checkout@v4` ×2, `astral-sh/setup-uv@v6` — ghim theo tag major (mutable), chưa theo SHA. uv bên trong ghim `0.6.3` | M3 |

## Phát hiện theo mức

### Critical — không có

### High — không có

### Medium

**M1. Symlink file trong `DOCQA_INGEST_ROOT` được đọc dù trỏ ra ngoài root** (chặn gate)
- Vị trí: `src/docqa/ingest.py` `_walk()` / `ingest_dir()` (`path.read_bytes()` đi theo symlink). `api.py` chỉ kiểm thư
  mục đích (`target.resolve().is_relative_to(root)`), không kiểm từng file.
- Tái hiện: ở trên (4e). Nội dung file ngoài root được lưu vào SQLite và trả nguyên văn qua `/ask`, `/chat`.
- Điều kiện: kẻ tấn công (hoặc người vận hành vô ý) phải tạo được symlink trong cây tài liệu. Test hiện có
  `test_ingest_symlink_escape_is_400` chỉ phủ symlink thư mục.
- Sửa đề xuất: trong `ingest_dir`, với mỗi file: `resolved = path.resolve()`; bỏ qua (thêm vào `skipped` với lý do
  `"symlink outside root"`) nếu `not resolved.is_relative_to(root.resolve())`; hoặc đơn giản bỏ qua mọi
  `path.is_symlink()`. Thêm test symlink file trỏ ra ngoài.

**M2. Vượt giới hạn độ dài `/chat` bằng khoảng trắng; không giới hạn kích thước request** (chặn gate)
- Vị trí: `src/docqa/chat.py` `validate_history()` dùng `len(turn.content.strip())`, nhưng `service.chat()` gửi
  `messages[-1].content` và lịch sử **chưa strip** cho model. `api.py` `ChatMessage.content: str` và
  `ChatRequest.messages` không có `max_length`.
- Tái hiện: một tin user `"refund window " + " " * 5_000_000` → 200, model giả nhận 5 000 014 ký tự (4b). Với API thật:
  tốn token/tiền hoặc 400/413 từ API, và server phải parse body nhiều MB trước khi kiểm (DoS bộ nhớ/CPU).
- Sửa đề xuất: kiểm `len(turn.content)` (bản gốc) hoặc strip trước khi lưu và dùng bản đã strip ở mọi bước; thêm
  `Field(max_length=...)` cho `ChatMessage.content` (vd 10 000 làm trần cứng) và `max_length=` cho `messages`
  (vd 100) để Pydantic chặn sớm; cân nhắc middleware từ chối `Content-Length` > ~256 KB. Thêm test.

**M3. GitHub Actions ghim theo tag mutable** (không chặn gate, nên sửa trước khi public)
- Vị trí: `.github/workflows/ci.yml` dòng 25, 28, 63. semgrep `github-actions-mutable-action-tag`
  (severity WARNING, metadata impact HIGH).
- Tác động hiện tại hạn chế: `permissions: contents: read`, không secret, không publish artifact/image. Nhưng repo sắp
  public và workflow sẽ chạy trên PR từ fork.
- Sửa đề xuất: ghim SHA đầy đủ kèm comment tag, vd `actions/checkout@<40-hex> # v4.x.y`,
  `astral-sh/setup-uv@<40-hex> # v6.x.y`; bật Dependabot cho `github-actions` để cập nhật SHA.

### Low

**L1. Null byte trong `path` của `/ingest` → 500.** `Path.resolve()`/`is_dir()` ném `ValueError` chưa được bắt.
Không lộ thông tin (body chỉ là `Internal Server Error`). Sửa: bắt `ValueError`/`OSError` quanh resolve → 400, hoặc
validate `path` không chứa `\x00`.

**L2. Image chưa tối thiểu.** `RUN uv sync` không dùng `--no-cache` hay cache mount nên `/root/.cache/uv` (41 MB, bản
sao các wheel) nằm trong layer; binary `uv` (30 MB) cũng nằm lại ở runtime. Đây cũng là nguồn một nửa số false positive
của trivy. Sửa: `ENV UV_NO_CACHE=1` hoặc `RUN --mount=type=cache,target=/root/.cache/uv uv sync …`; cân nhắc
multi-stage (stage build có uv, stage runtime chỉ copy `/app/.venv` + `src`).

**L3. CVE của base image chưa có bản sửa.** `python:3.12-slim` (debian 13.7, đã pull bản mới nhất để đối chiếu, giống
hệt): 8 CVE HIGH ở `util-linux`, `acl`, `ncurses`, `systemd` (libs), `perl-base`, tất cả `affected`/`fix_deferred`, không
có đường gọi từ ứng dụng (app chỉ chạy `uvicorn`, không mount, không dùng perl). `pip 25.0.1` của base có 5 CVE MEDIUM,
không dùng lúc runtime. Base image không ghim digest. Chấp nhận rủi ro; khuyến nghị ghim digest `python:3.12-slim@sha256:…`,
rebuild khi Debian có bản sửa, và có thể `pip uninstall -y pip` trong stage runtime.

**L4. Không auth, không rate limit** (thiết kế, đã ghi trong SPEC và README "Run it locally or behind your own
gateway"). Hệ quả nếu lộ ra mạng: ai cũng gọi `/ask`, `/chat` bằng key của người chạy (tốn tiền) và gọi `/ingest`
liên tục (CPU). README hướng dẫn `docker run --rm -p 8000:8000 …` — publish trên mọi interface của máy host. Khuyến nghị
README dùng `-p 127.0.0.1:8000:8000`.

**L5. Lộ thông tin nhỏ.** `/docs`, `/redoc`, `/openapi.json` bật (200); `skipped` của `/ingest` liệt kê đường dẫn tương
đối của mọi file dưới thư mục được ingest; lỗi 422 của Pydantic lặp lại `input` người dùng gửi. Chấp nhận được cho bản
demo; nếu triển khai thật thì tắt docs (`FastAPI(docs_url=None, redoc_url=None, openapi_url=None)`).

**L6. Prompt injection từ tài liệu được ingest và từ lịch sử chat do client giữ** (ghi nhận rủi ro).
- Vector: tài liệu chứa chỉ dẫn ("bỏ qua hướng dẫn trước…"); hoặc client tự bịa lượt `assistant` trong `messages`.
- Giảm thiểu hiện có: tài liệu đi dưới dạng `document` block có `citations` (tách khỏi chỉ dẫn), system prompt chỉ cho
  dùng tài liệu và coi lịch sử là ngữ cảnh, không phải nguồn sự thật; `found=true` chỉ khi có trích dẫn, và trích dẫn là
  đoạn nguyên văn do API trả về (`cited_text`), không phải text model tự viết; model không có tool, không có secret trong
  context, không có hành động phụ; widget chỉ render bằng `textContent` nên output độc hại không thành XSS.
- Rủi ro còn lại: nội dung câu trả lời (text) có thể bị tài liệu độc điều khiển (sai lệch, chèn link lừa đảo dạng text).
  Mức Low vì kho tài liệu do người vận hành chọn. Khi ingest tài liệu không tin cậy, nên ghi cảnh báo trong README.

### Info
- `config.py`: key không thuộc `Settings`, SDK tự đọc `ANTHROPIC_API_KEY`; `repr(Settings)` không chứa key (có test).
- Test chặn mạng toàn cục (`tests/conftest.py`) — CI không thể vô tình gọi API.
- `uvicorn` trong container bind `0.0.0.0` là cần thiết để publish cổng; kiểm soát phạm vi ở cờ `-p` (xem L4).

## Công cụ

| Công cụ | Phiên bản | Đã chạy? | Ghi chú |
|---|---|---|---|
| gitleaks | 8.30.1 (cài `brew install gitleaks`) | Có | lịch sử `--all`, `--all -m`, commit dangling, cây làm việc |
| pip-audit | 2.10.1 (`uvx`) | Có | chạy kiểu `-r req.txt` mặc định bị lỗi tạo venv (`ensurepip … SIGABRT`); chạy lại với `--require-hashes --disable-pip` (lockfile có hash, không cần resolve) — PyPI + OSV |
| bandit | 1.9.4 (`uvx`) | Có | `src`, `scripts` |
| semgrep | 1.182.1 (`uvx`) | Có, một phần | `--config auto` **chưa chạy** (đòi bật metrics); đã chạy 7 ruleset registry tường minh với `--metrics=off` |
| trivy | 0.76.1 (cài `brew install trivy`) | Có | `image` (vuln, secret, misconfig), `config` |
| Docker | Docker Desktop | Có | build từ `git archive HEAD` + file mồi `.env`, chạy container local `127.0.0.1` |
| Probe API | `.venv/bin/python` + `fastapi.testclient`, `FakeAnswerModel`, socket bị chặn | Có | script ở ngoài repo (scratchpad), không commit |
| npm audit | — | N/A | dự án không có dependency JS (widget là một file HTML không thư viện) |

## Khuyến nghị (theo thứ tự)
1. eng-developer sửa **M1, M2** kèm test → `sec-devops` chạy lại gate (mục 4b, 4c, 4e).
2. Trước Milestone 2 (public repo): sửa **M3** (ghim SHA + Dependabot), **L2** (bỏ uv cache), đổi lệnh `docker run` trong
   README sang `-p 127.0.0.1:8000:8000` (L4), bắt `ValueError` ở `/ingest` (L1).
3. Không cần allowlist gitleaks hiện tại. Nếu sau này thêm chuỗi giả trông giống key thật (`sk-ant-api03-…`), dùng
   `# gitleaks:allow` ở cuối dòng hoặc `.gitleaks.toml` với `[allowlist] paths = ['''tests/.*''']` kèm `regexes` cụ thể.
4. Thêm job `gitleaks` (hoặc `pip-audit`) vào CI để gate tự chạy trên mỗi PR sau khi public.
