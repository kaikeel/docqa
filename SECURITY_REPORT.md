# SECURITY_REPORT — PF-20261025-docqa v0.1.0 (vòng 2)

- Người kiểm: `sec-devops` (Digital Worker) · Ngày: 2026-10-25
- Phạm vi: nhánh `main` @ `320f25c` (toàn bộ lịch sử git: 71 commit không-merge / 100 commit kể cả merge trên 29
  ref + 6 commit dangling), image Docker build từ `git archive HEAD`, `.github/workflows/ci.yml`,
  `.github/dependabot.yml`.
- Checklist: `05-devops-security/checklists/security.md` + yêu cầu PMO (API, widget, Docker, CI) + phần release
  open-source (repo sẽ public: lịch sử git, license, dữ liệu nội bộ).
- Ràng buộc: không gọi API Anthropic thật, không dùng key thật. Kiểm tra động chạy offline với `FakeAnswerModel`
  qua FastAPI `TestClient` (socket bị chặn), CLI `docqa ingest` trên thư mục tạm, và một container local
  `127.0.0.1:18081` không có key. Image/container tạm đã xoá sau khi kiểm.

## Tóm tắt vòng 1 (@ `0de2e8e`)

FAIL vì 2 lỗi medium: **M1** file symlink trong `DOCQA_INGEST_ROOT` trỏ ra ngoài vẫn được đọc và trích dẫn;
**M2** đệm khoảng trắng vượt giới hạn độ dài `/chat` (đo trên `strip()`, gửi bản gốc), body không giới hạn kích
thước. Kèm M3 (action ghim tag mutable), L1 (NUL trong path → 500), L2 (uv + cache trong image), L3 (CVE base image
chưa có bản sửa), L4 (không auth; README publish cổng mọi interface), L5 (`/docs` bật, 422 lặp input), L6 (prompt
injection). Sửa ở T20–T24.

## Kết luận vòng 2: **PASS** (security gate cho G3)

M1, M2, M3, L1, L2, L4 và phần "422 lặp input" của L5 đã sửa và được xác nhận bằng tái hiện PoC vòng 1 cùng biến
thể mới. Không có critical/high/medium còn mở trong code, dependency, image hay lịch sử git (không secret).

**Điều kiện trước khi public repo (G5), không chặn G3:** **R1** — lịch sử git và HEAD chứa đường dẫn máy cục bộ
(`/Users/<user>/<thư mục công ty>/projects/active/...`) trong `TASKS.md` và `QA_REPORT.md`. Không phải secret,
nhưng vi phạm mục "không đường dẫn máy" của checklist release. Cần CEO quyết định (xem mục R1).

## Bảng kiểm

| # | Mục | Lệnh / cách kiểm | Kết quả thật (rút gọn) | Trạng thái |
|---|---|---|---|---|
| 1a | Secret scan, toàn bộ lịch sử | `gitleaks detect --source . --log-opts=--all -v` (gitleaks 8.30.1) | `71 commits scanned … no leaks found` | PASS |
| 1b | Secret scan, cả diff merge | `gitleaks detect --source . --log-opts="--all -m"` | `100 commits scanned … no leaks found` | PASS |
| 1c | Secret scan, commit dangling | `git fsck --lost-found` → 6 commit (stash WIP, commit bị amend); `gitleaks detect --log-opts=<sha>` từng cái | `no leaks found` ×6; không có `.env`/`.db`/`.pem`/`.key` trong các commit này | PASS |
| 1d | Secret scan, cây làm việc | `gitleaks detect --source . --no-git` | `no leaks found` | PASS |
| 1e | `.env` trong lịch sử | `git log --all --name-only --format= \| grep -E '(^\|/)\.env'` | chỉ `.env.example`; mọi dòng `+…=` trong lịch sử của nó đều rỗng hoặc mặc định (`ANTHROPIC_API_KEY=`) | PASS |
| 1f | Tác giả commit | `git log --all --format='%an <%ae>' \| sort \| uniq -c` | `100 Sine <…@users.noreply.github.com>` | PASS |
| 1g | Đường dẫn máy / email nội bộ | `git grep -nIE '<email công ty>\|/Users/' HEAD` và trên `$(git rev-list --all)` | Không có email nội bộ. Đường dẫn máy thật: `TASKS.md:93`, `QA_REPORT.md:93` ở HEAD; có trong 79 / 30 phiên bản lịch sử. (`/Users/secret/path` trong `tests/test_api.py` là chuỗi giả của test) | **R1** |
| 1h | License tương thích MIT | metadata 30 gói runtime trong image | MIT, BSD-2/3, Apache-2.0, ISC, PSF-2.0, `MIT OR Apache-2.0` — không có copyleft | PASS |
| 1i | Không code/dữ liệu khách | đọc `PROJECT.md`, `examples/` | Dự án portfolio nội bộ, không khách, tài liệu mẫu tự viết | PASS |
| 2 | Dependency CVE (lockfile mới) | `uv export --frozen --no-emit-project > req.txt` (45 gói, có hash, gồm dev; runtime 30) → `uvx pip-audit -r req.txt --require-hashes --disable-pip` (2.10.1), nguồn PyPI và `-s osv` | `No known vulnerabilities found` (cả hai nguồn) | PASS |
| 3a | SAST Python | `uvx bandit -r src scripts` (1.9.4) | 1281 LOC; High 0 / Medium 0 / Low 1: `B105 hardcoded_password_string` ở `retriever.py:42` = **false positive** (tên biến `_TOKEN_SQL` chứa câu SQL có `?`) | PASS |
| 3b | SAST đa ngôn ngữ | `uvx semgrep scan --metrics=off --config p/python --config p/owasp-top-ten --config p/security-audit --config p/secrets --config p/dockerfile --config p/github-actions --config p/javascript src Dockerfile .github` (1.182.1, 282 rule, 18 file) | 1 phát hiện: `dependabot-missing-cooldown` (severity MEDIUM) ở `.github/dependabot.yml` → L8. `github-actions-mutable-action-tag`: 0 (vòng 1: 3). `src/`, widget: 0 | PASS (có L8) |
| 3c | `semgrep --config auto` | — | **Chưa chạy**: `auto` bắt buộc bật metrics; giữ `--metrics=off`, thay bằng 7 ruleset ở 3b | CHƯA CHẠY (đã thay thế) |
| 4a | M1: symlink file ra ngoài root (PoC vòng 1) | `docs/link.md -> ../../outside/secret.md`, `POST /ingest {"path":"docs"}`, `POST /ask "TOPSECRET hunter2 …"` | `skipped: "link.md: symlink outside root"`; `/ask` → `found:false`; DB không có file ngoài root | PASS |
| 4b | Biến thể symlink | cùng root tạm: chuỗi lồng `l1.md -> l2.md -> ../../outside/secret.md`; file qua symlink thư mục `viadir.md -> ../escdir/secret.md` (`escdir -> ../outside`); tuyệt đối `abs.txt -> /etc/hosts`; symlink thư mục `docs/sub -> ../../outside`; symlink hỏng | `l1.md`, `l2.md`, `viadir.md`, `abs.txt`: `symlink outside root`; `docs/sub` không được duyệt, `POST /ingest {"path":"docs/sub"}` và `"escdir"` → 400 `path_outside_root`; hỏng → `unreadable (FileNotFoundError)` | PASS |
| 4c | Symlink qua CLI | `docqa ingest kb/docs` với `link.md`, `via.md` ra ngoài và `sib.md -> ../sib.md` (ngoài thư mục ingest, trong `kb`) | `skipped: link.md, sib.md, via.md: symlink outside root` (CLI lấy chính thư mục ingest làm biên) | PASS |
| 4d | Hardlink | `os.link(outside/hard.md, docs/hard.md)` (API) và `ln outside/s.md kb/docs/hard.md` (CLI) | **Được đọc và trích dẫn** (`"source":"hard.md","quote":"HARDLINKSECRET …"`) — không phân biệt được với file thường | L7 (chấp nhận) |
| 4e | Symlink tới file trong root | `docs/inroot.md -> ../private/inroot.md`, `docs/hid.md -> ../.hidden.md` | Cả hai được đọc (đúng thiết kế: biên là `DOCQA_INGEST_ROOT`); `hid.md` lách quy tắc bỏ qua file ẩn | L7 (chấp nhận) |
| 4f | `..` và biến thể qua API | `../outside`, `docs/../../outside`, `/etc`, `．．/outside` (fullwidth, NFKC → `..`), `%2e%2e/outside`, `docs\..\..\outside`, `~`, `docś` (NFD), `‮scod` (RLO), `DOCS` | `..` thật và `/etc` → 400 `path_outside_root`; fullwidth/percent/backslash/`~`/NFD/RLO → 400 `ingest_error` (Python không chuẩn hoá unicode, không decode `%`, không mở rộng `~`, nên chỉ là tên thư mục không tồn tại); `DOCS` → 200 vì APFS không phân biệt hoa thường, vẫn trong root | PASS |
| 4g | L1: NUL trong path | `{"path":"docs\u0000"}`, `{"path":"docs\u0000/../.."}` (TestClient + container) | 400 `invalid_path` | PASS |
| 4h | Path lỗi khác | `{"path": "a"*5000}`; thư mục chứa symlink vòng `self.md -> self.md` | **500** `internal_error` (JSON, không lộ gì) — `OSError [Errno 63] File name too long` ở `is_dir()`, `RuntimeError: Symlink loop` ở `resolve()` ngoài khối `try`. CLI: in traceback `RuntimeError` | L9 |
| 4i | M2: đệm 5 MB khoảng trắng (PoC vòng 1) | `/chat` `"refund window " + " "*5_000_000` (5 000 062 byte) — TestClient, container có `Content-Length`, container `Transfer-Encoding: chunked` | 413 `request_too_large` cả ba; model không được gọi | PASS |
| 4j | Đệm dưới trần body | câu hỏi 50 ký tự + 20 000 dấu cách; + `"\n\t "*5000` và `　`×10 000 (85 KB) | 200, model nhận đúng **50** ký tự (đã strip) | PASS |
| 4k | Đúng biên độ dài | ký tự zero-width `​` (không bị strip) tới đúng 2000 / 2001; 2001 emoji; 900 cặp NFD `é` (1851 code point) | 2000 → 200 (model nhận 2000); 2001 → 422 `chat_history_invalid`; emoji 2001 → 422; NFD đếm theo code point, 1851 → 200 | PASS |
| 4l | Trần Pydantic | 1 message 32 001 ký tự; 101 message; 200 000 khoảng trắng | 422 `invalid_request` (`at most 32000 characters` / `at most 100 items`) trước khi vào service | PASS |
| 4m | Nhiều message nhỏ cộng lại | 21 message ngắn; 19×2000 ký tự (38 000, tối đa theo mặc định); 19×(2000 + 10 000 khoảng trắng) = 228 KB; 21×2000 emoji = 504 KB | 422 `at most 20 messages`; 200 (lịch sử 18×2000, câu hỏi 2000); 200 (sau strip vẫn 2000/message); 413. Tổng gửi model bị chặn ở ≤ 20×2000 ký tự với cấu hình mặc định, ≤ 256 KiB với mọi cấu hình | PASS |
| 4n | Câu trả lời assistant dài | lượt assistant 30 000 ký tự | 200, model nhận lịch sử `[50, 2000]` (cắt về `DOCQA_CHAT_MAX_CHARS`) | PASS |
| 4o | Body lớn / chunked trên endpoint khác | `/ingest` chunked 300 KB; `/chat` chunked 5 byte/chunk (nhỏ) | 413; 200 (không chặn nhầm) | PASS |
| 4p | Body dị dạng | `"[" * 200000`; `{"messages":` + `[`×100 000; JSON hỏng; `text/plain`; `Content-Length: 20` nhưng gửi 5 MB (container) | 400 `http_error` "There was an error parsing the body"; 422 `invalid_request`; uvicorn chỉ đọc 20 byte → 422, phần còn lại bị từ chối "Invalid HTTP request" | PASS |
| 4q | Validate input khác | `k=1000`, role `system`, trường lạ | 422 `invalid_request` | PASS |
| 4r | Lỗi luôn JSON, không lặp input | gửi chuỗi đánh dấu `ECHOMARKER-sk-ant-api03-zzz` trong input sai kiểu; 404; 405; model ném `RuntimeError("/Users/secret/path sk-ant-api03-FAKE")` | 422 không chứa chuỗi đánh dấu (`/ask`, `/chat`, `/ingest`); 404 `not_found`, 405 `method_not_allowed`; 500 `{"code":"internal_error","message":"Internal server error."}`, không lộ đường dẫn/key | PASS |
| 4s | DoS truy vấn | `ask` câu 2000 ký tự gồm ~660 token ngẫu nhiên (cổng bằng chứng chạy 1 truy vấn FTS5/token) | 0.014 s | PASS |
| 4t | SQL tham số hoá | đọc diff `store.py`, `retriever.py` từ vòng 1 | Mọi giá trị qua `?`; f-string chỉ cho hằng `SCHEMA_VERSION` và thông điệp lỗi; truy vấn MATCH dựng bằng `to_match_expression` (token bọc `"…"`) | PASS |
| 4u | XSS / CSP widget | header `GET /` | CSP hash-based giữ nguyên (`default-src 'none'; script-src 'sha256-…'`), `nosniff`; widget đổi ở T25 vẫn qua test tĩnh của QA | PASS |
| 4v | CORS / CSRF | preflight `Origin: https://evil.example` | 405, không header `Access-Control-*`; `text/plain` → 422 | PASS |
| 4w | Prompt injection | đọc lại, không đổi từ vòng 1 | L6 — README "Untrusted documents" đã ghi | Chấp nhận |
| 4x | Auth / crypto / dữ liệu cá nhân / scraping | đọc code | Không auth (L4), không mật khẩu, không tự viết crypto, chat stateless, không scrape | N/A / PASS |
| 5a | Docker non-root | `docker run --entrypoint sh … id; touch /app/x` | `uid=10001(docqa)`; `touch: cannot touch '/app/x': Permission denied` | PASS |
| 5b | Không uv/cache | `docker run -u 0 … find / -xdev -name uv -o -name uvx -o -path '*/.cache/uv'`; `docker history` | Không tìm thấy; `/root` chỉ có `.bashrc .profile .wget-hsts`; layer runtime chỉ `COPY /app/.venv` (71.8 MB) + `examples` (70 kB) | PASS |
| 5c | Không `.env`/DB | build với `.env` (`sk-ant-PLANTED2`), `.env.probe`, `stray.db` cài trong context; `find / -name ".env*" -o -name "*.db"`; `grep -rl PLANTED2 /` (root) | Không tìm thấy gì | PASS |
| 5d | Kích thước | `docker image inspect --format '{{.Size}}'` | 57.9 MB nén (vòng 1: 81 MB), 289 MB giải nén; `.venv` 69 MB | PASS |
| 5e | Trivy image (đầy đủ) | `trivy image --scanners vuln,secret,misconfig` (0.76.1) | Debian 13.7: HIGH 44 mục / 8 CVE (`util-linux` ×5, `ncurses`, `systemd` libs, `acl`, `perl-base`) — tất cả `affected` (43) / `fix_deferred` (1); không CRITICAL. Python: chỉ `pip 25.0.1` của base, 5 MEDIUM 1 LOW. Secret: 11 hit `gcp-service-account` CRITICAL trong 7 file của SDK `anthropic` = **false positive** (docstring `` `{"type": "service_account"}` ``; vòng 1: 13 hit, phần trong uv cache đã mất). Misconfig: 0 | PASS (có L3) |
| 5f | Trivy image `--ignore-unfixed` | `trivy image --ignore-unfixed --severity HIGH,CRITICAL` | Vulnerabilities 0 ở mọi target | PASS |
| 5g | Trivy config | `trivy config --severity HIGH,CRITICAL .`; không lọc mức | `Dockerfile 0`; không lọc: 1 LOW `DS-0026 Add HEALTHCHECK` | PASS |
| 5h | Container chạy thật | `docker run -d -p 127.0.0.1:18081:8000`, `curl` | `/health` 200, `/` 200, ingest `examples/docs` 10 doc; `/etc` 400; log uvicorn không chứa body (`grep -c "refund window"` = 0) | PASS |
| 6a | M3: SHA ghim khớp tag | `git ls-remote https://github.com/actions/checkout 'refs/tags/v4.4.0*'`; tương tự `astral-sh/setup-uv 'refs/tags/v6.8.0*'`; `gh api repos/<repo>/commits/<sha>` | `11d5960a326750d5838078e36cf38b85af677262 refs/tags/v4.4.0` = SHA trong `ci.yml` (×2); `d0cc045d04ccac9d8b7881df0226f9e82c39688e refs/tags/v6.8.0` = SHA trong `ci.yml`. Tag nhẹ (không có dòng `^{}`), SHA là commit; cả hai commit tồn tại upstream | PASS |
| 6b | Dependabot | đọc `.github/dependabot.yml` | `github-actions`, weekly; thiếu `cooldown` (L8) | PASS (có L8) |
| 6c | CI quyền / secret | đọc `ci.yml` | `permissions: contents: read`; không `secrets.*`; `ANTHROPIC_API_KEY: ""`; không `pull_request_target`; uv ghim `0.6.3` | PASS |

## Trạng thái các phát hiện vòng 1

| Mã | Trạng thái | Bằng chứng |
|---|---|---|
| M1 symlink file ra ngoài root | **Đã sửa** | 4a–4c |
| M2 đệm khoảng trắng / body không giới hạn | **Đã sửa** | 4i–4p |
| M3 action ghim tag mutable | **Đã sửa** | 3b, 6a |
| L1 NUL → 500 | **Đã sửa** (biến thể khác còn 500: L9) | 4g, 4h |
| L2 uv + cache trong image | **Đã sửa** | 5b, 5d |
| L3 CVE base image chưa có bản sửa | Còn, chấp nhận | 5e, 5f |
| L4 không auth, README publish mọi interface | README đã đổi sang `-p 127.0.0.1:8000:8000` (dòng 121, 128, 143); không auth: chấp nhận | 5h |
| L5 `/docs` bật, 422 lặp input | 422 không lặp input nữa (4r); `/docs`, `/redoc`, `/openapi.json` vẫn 200: chấp nhận, đã ghi README | 4r |
| L6 prompt injection | Chấp nhận, đã ghi README | 4w |

## Phát hiện còn lại theo mức

### Critical — không có
### High — không có
### Medium — không có

### Low

**L3. CVE của base image chưa có bản sửa** (giữ từ vòng 1, chấp nhận rủi ro). 8 CVE HIGH Debian, tất cả
`affected`/`fix_deferred`, không có đường gọi từ ứng dụng; `pip` của base còn trong image runtime (5 MEDIUM, không
dùng lúc chạy). Base `python:3.12-slim` và `ghcr.io/astral-sh/uv:0.6.3` chưa ghim digest. Khuyến nghị: ghim
`@sha256:…` (Dependabot `docker` có thể cập nhật), `pip uninstall -y pip` ở stage runtime, rebuild khi Debian ra bản sửa.

**L4. Không auth, không rate limit** (thiết kế; README ghi rõ và hướng dẫn bind `127.0.0.1`). Chấp nhận.

**L5. OpenAPI bật** (`/docs`, `/redoc`, `/openapi.json`). Chấp nhận cho bản demo; README đã ghi.

**L6. Prompt injection từ tài liệu / lịch sử chat do client giữ.** Chấp nhận; giảm thiểu như vòng 1 (document block
có citations, trích dẫn là `cited_text` nguyên văn, không tool, widget dùng `textContent`); README "Untrusted documents".

**L7. Hardlink và symlink trong root lách quy tắc** (mới, chấp nhận rủi ro). Hardlink tới file ngoài root được đọc
như file thường (4d) — không thể phân biệt bằng đường dẫn; chỉ chặn được bằng `st_nlink > 1` (sẽ chặn nhầm file hợp
lệ) hoặc so `st_dev`. Symlink tới file ẩn trong root được đọc (4e), và `POST /ingest {"path": ".venv"}` ingest trực
tiếp một thư mục ẩn (container: 28 file README/LICENSE trong site-packages) vì quy tắc "ẩn" chỉ áp cho mục con. Điều
kiện khai thác: phải ghi được vào cây tài liệu (hardlink cần cùng filesystem và quyền đọc file đích) — khi đó kẻ tấn
công cũng chép được file. `.env` không bao giờ bị đọc vì đuôi không được hỗ trợ. Khuyến nghị (không bắt buộc): thêm
hardlink vào mục Symlinks của Known limitations; từ chối `path` có thành phần bắt đầu bằng `.`.

**L8. Dependabot không có `cooldown`** (mới; semgrep `dependabot-missing-cooldown`, MEDIUM theo rule, Low với dự án:
Dependabot chỉ mở PR, người merge vẫn là CEO, CI chạy với `contents: read`). Khuyến nghị thêm
`cooldown: {default-days: 7}`.

**L9. Đường dẫn lỗi còn ra 500** (mới, phần còn lại của L1). `/ingest` với path quá dài (`OSError ENAMETOOLONG` từ
`is_dir()`) hoặc thư mục chứa symlink vòng (`RuntimeError` từ `resolve()` ở `ingest_dir`, ngoài khối `try`) → 500
`internal_error` JSON, không lộ thông tin, không làm sập server. CLI `docqa ingest` gặp symlink vòng thì in traceback
thay vì thông điệp. Sửa: bắt `(OSError, RuntimeError)` quanh `path.resolve()` → `skipped "<rel>: unreadable (symlink
loop)"`, và quanh `is_dir()` trong `api.ingest` → 400 `invalid_path`.

### Release (trước G5 — public repo)

**R1. Đường dẫn máy cục bộ trong HEAD và lịch sử git.** `TASKS.md:93` (lệnh `git clone "/Users/<user>/<thư mục
công ty>/projects/active/PF-20261025-docqa" …`) và `QA_REPORT.md:93`; có trong 79 phiên bản `TASKS.md` và 30 phiên
bản `QA_REPORT.md` trong lịch sử. Lộ tên user máy và cấu trúc thư mục nội bộ; không lộ secret hay email (tác giả commit
đều là `users.noreply.github.com`). Hai lựa chọn cho CEO:
1. Sửa HEAD (thay bằng `<path-to-repo>`) và **chấp nhận** lịch sử (rủi ro thấp: tên user trùng handle GitHub đã công khai).
2. Sửa HEAD rồi public từ lịch sử mới (squash/orphan branch hoặc `git filter-repo --replace-text`) — phá SHA của mọi
   commit, tag, và các tham chiếu commit trong `TASKS.md`.
`sec-devops` khuyến nghị (1) nếu CEO không ngại tên user; nếu không thì (2) ngay trước khi tạo tag `v0.1.0`.
Ghi chú thêm: repo public sẽ gồm cả tài liệu nội bộ tiếng Việt (`PROJECT.md`, `TASKS.md`, `QA_REPORT.md`,
`SECURITY_REPORT.md`) — không có dữ liệu khách hay giá, nhưng CEO nên xác nhận đó là chủ ý (README dòng 41 có nói đến).

### Info
- bandit `B105` ở `retriever.py:42` và 11 hit trivy `gcp-service-account` trong SDK `anthropic` là false positive.
- `DS-0026` (thiếu `HEALTHCHECK`) — LOW, tuỳ chọn.
- TOCTOU giữa `path.resolve()` và `resolved.read_bytes()`: kẻ đã ghi được vào cây tài liệu có thể đổi một thư mục
  cha thành symlink trong khoảng đó. Cùng điều kiện như L7, không khuyến nghị sửa cho v0.1.
- Không còn chuỗi giả dạng `sk-ant-api03-…` đủ dài để gitleaks báo; chưa cần allowlist.

## Công cụ

| Công cụ | Phiên bản | Đã chạy? | Ghi chú |
|---|---|---|---|
| gitleaks | 8.30.1 | Có | `--all`, `--all -m`, 6 commit dangling, cây làm việc |
| pip-audit | 2.10.1 (`uvx`) | Có | `-r req.txt --require-hashes --disable-pip`, nguồn PyPI + OSV |
| bandit | 1.9.4 (`uvx`) | Có | `src`, `scripts` |
| semgrep | 1.182.1 (`uvx`) | Có, một phần | 7 ruleset tường minh, `--metrics=off`; `--config auto` **chưa chạy** (đòi bật metrics) |
| trivy | 0.76.1 | Có | `image` (vuln/secret/misconfig, có và không `--ignore-unfixed`), `config` |
| git ls-remote / gh api | — | Có | đối chiếu SHA ghim với tag upstream |
| Docker | Docker Desktop | Có | build từ `git archive HEAD` + file mồi; container `127.0.0.1`; đã xoá image `docqa:secgate2` |
| Probe API/CLI | `.venv/bin/python -I` + `TestClient`, `FakeAnswerModel`, socket bị chặn; `docqa ingest` | Có | script ở scratchpad, không commit |
| npm audit | — | N/A | không có dependency JS |

## Khuyến nghị
1. G3: security gate PASS — có thể chuyển tiếp khi QA cũng PASS.
2. Trước G5: CEO quyết định R1; tuỳ chọn sửa L9, L8, thêm hardlink vào Known limitations (L7), ghim digest base image (L3).
3. Sau khi public: thêm job `gitleaks` + `pip-audit` vào CI.
