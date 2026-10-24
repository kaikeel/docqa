# PF-20261025-docqa — Kaikeel DocQA

- Freelancer project ID / link: — (dự án portfolio nội bộ, backlog B-014)
- Khách hàng: Kaikeel (nội bộ) · Người xem: khách tiềm năng trên Freelancer, khách SG/CN
- Giá trị: $0 · Loại: portfolio
- Appetite: tối đa 1 ngày công AI, ≤ 1 giờ CEO (chỉ xem demo, duyệt public)
- Trạng thái: VERIFY (BUILD T1–T13, T15–T18 xong 2026-10-25; chờ QA + Security gate — T14)

## Vấn đề (người xem portfolio muốn thấy gì)
Khách thuê "RAG chatbot" thường nhận về bản demo chạy được một lần, trả lời bịa, không có test, không ai
tiếp quản được. Dự án này chứng minh Kaikeel làm RAG **đúng chuẩn**: câu trả lời có trích dẫn kiểm chứng
được, biết nói "không tìm thấy" thay vì bịa, có test, có eval, README chạy được trên máy sạch.

## Phạm vi (In scope)
- Nạp tài liệu `.md`, `.txt`, `.pdf` từ một thư mục; tách đoạn (chunk) có chồng lấn; lưu vào SQLite.
- Tìm kiếm BM25 bằng SQLite FTS5 (không cần dịch vụ ngoài). Retriever là một interface để thay bằng vector
  search sau này.
- Trả lời bằng Claude (Anthropic SDK chính thức), đưa các đoạn tìm được vào dưới dạng `document` block bật
  `citations` → mỗi câu trả lời kèm trích dẫn (tên file, đoạn trích nguyên văn).
- Không có bằng chứng (retriever không trả về gì đủ điểm) → trả "không tìm thấy trong tài liệu", không gọi LLM.
- CLI: `docqa ingest <dir>`, `docqa ask "<câu hỏi>"`, `docqa eval <file.jsonl>`.
- API FastAPI: `POST /ingest`, `POST /ask`, `GET /health`.
- **Chế độ chat nhiều lượt (thêm 2026-10-25, ADR 0007 — phủ nhóm job "chatbot hỗ trợ khách" 18%)**:
  `POST /chat` stateless — client gửi lịch sử hội thoại `messages[{role, content}]` (giới hạn số lượt và độ dài),
  server dùng câu hỏi mới nhất (kèm ngữ cảnh lượt trước để tìm kiếm câu hỏi nối tiếp) cho retriever, trả cùng
  schema `{answer, citations, found}`. Không lưu phiên trên server.
- **Widget chat mẫu**: một file HTML tĩnh tự chứa (không framework, không CDN) được phục vụ tại `GET /`, gọi
  `POST /chat`, hiển thị trích dẫn dưới mỗi câu trả lời — minh hoạ cách nhúng vào website khách.
- Eval: bộ câu hỏi mẫu trên tài liệu mẫu, đo retrieval hit@k (không cần API key) và tỉ lệ câu trả lời có trích dẫn.
- Tài liệu mẫu nhỏ, tự viết, được phép công khai, trong `examples/docs/`.
- Dockerfile, GitHub Actions CI (ruff, mypy, pytest + coverage), CHANGELOG, tag `v0.1.0`, license MIT.

## Ngoài phạm vi (Out of scope)
- Giao diện web đầy đủ (chỉ CLI + API + một widget chat HTML tĩnh làm mẫu); lưu phiên chat phía server.
- Vector DB / embeddings, đăng nhập người dùng, multi-tenant, OCR cho PDF scan.
- Deploy production. (Demo chạy local hoặc Docker.)

## Tiêu chí nghiệm thu
- [ ] AC1: `docqa ingest examples/docs` rồi `docqa ask` trả lời câu hỏi có trong tài liệu, kèm ≥ 1 trích dẫn đúng file.
- [ ] AC2: Câu hỏi không có trong tài liệu → trả "not found", không gọi API (kiểm bằng test với LLM giả).
- [ ] AC3: `POST /ask` trả JSON `{answer, citations[{source, quote}], found}`; `GET /health` trả 200.
- [ ] AC4: `docqa eval examples/eval.jsonl --retrieval-only` chạy không cần API key, in hit@k; hit@3 ≥ 0.8 trên bộ mẫu.
- [ ] AC5: Test chạy không cần mạng / API key (LLM giả qua interface); coverage logic ≥ 80%; ruff + mypy sạch.
- [ ] AC6: README đưa người lạ từ máy sạch tới câu trả lời đầu tiên trong ≤ 10 phút (có cả lối Docker).
- [ ] AC7: Không secret trong repo; key chỉ đọc từ biến môi trường; SECURITY_REPORT PASS.
- [ ] AC8: `POST /chat` với câu hỏi nối tiếp ("còn cái kia thì sao?") tìm đúng tài liệu nhờ ngữ cảnh lượt trước;
  lịch sử vượt giới hạn → 422; `GET /` trả widget chạy được, hiển thị nội dung từ API bằng `textContent` (không
  `innerHTML` với dữ liệu trả về) (test).

## Milestone
| # | Đầu ra | Giá ($) | Ngày giao | Trạng thái |
|---|---|---|---|---|
| 1 | v0.1.0: toàn bộ AC1–AC7, repo riêng tư trên `kaikeel` | 0 | 2026-10-26 | todo |
| 2 | CEO duyệt → public repo + thêm vào `08-marketing-brand/portfolio.md` | 0 | sau duyệt | todo |

## Giả định & câu hỏi còn mở
- Model mặc định `claude-opus-5-5`, đổi qua biến `DOCQA_MODEL`. Bật server-side fallback khi bị từ chối.
- Chạy demo thật cần `ANTHROPIC_API_KEY` của người chạy; CI không gọi API.
- Python 3.12, quản lý bằng `uv`.
- (SHAPE, sol-architect 2026-10-25) Thiết kế ở `docs/SPEC.md`, ADR 0002 (FTS5/BM25) và 0003 (citations gốc).
  `found=true` chỉ khi retriever có bằng chứng **và** Claude trả ≥ 1 trích dẫn.
- Giả định: CI sẽ đỏ cho tới khi T1 thêm `pyproject.toml` + `uv.lock` (CI đã chỉnh sẵn cho stack).
- (SHAPE bổ sung, sol-architect 2026-10-25) Chat + widget thiết kế ở `docs/SPEC.md`, ADR dự án `docs/adr/` 0004 (chat stateless,
  lịch sử text thuần, document chỉ ở lượt cuối), 0005 (truy vấn câu nối tiếp tất định: câu mới nhất + câu user
  ngay trước, không viết lại bằng LLM), 0006 (widget một file, chỉ `textContent`, CSP hash). Task T15–T18.
- Q5 đã đóng (sol-architect, kiểm offline trên `.venv`): `anthropic==2.3.0` có `fallbacks: Literal["default"]` và
  beta `server-side-fallback-2026-07-01`, đã bỏ `temperature`/`top_p`/`top_k`, gửi `anthropic-version: 2026-10-21`.
- Giả định: Milestone 1 (v0.1.0) gồm cả AC8 (theo Q2); bảng Milestone còn ghi "AC1–AC7" — đề nghị PMO sửa.
- Giả định: `uv` local là 0.6.3 (2025-02); nếu không đọc được `uv.lock` do CI tạo bằng bản mới thì nâng uv local
  (`brew upgrade uv`) — việc trên máy CEO, cần CEO đồng ý.

- (Claude, 2026-10-25, theo ADR 0005) **uv**: không nâng uv trên máy CEO; CI ghim `astral-sh/setup-uv` đúng bản
  local `0.6.3` để `uv.lock` tương thích hai phía.

### Quyết định cho câu hỏi đã mở (Claude, 2026-10-25, theo ADR 0005)
- Q1 → Máy build không có `ANTHROPIC_API_KEY`. Agent dừng ở mức kiểm tự động (model giả). Bước chạy với API thật
  (AC1, phần thời gian của AC6) chuyển thành mục **CEO tự chạy khi xem demo ở G3 nội bộ**, bằng key của CEO.
- Q2 → Giữ nguyên scope và thêm chế độ chat (ADR 0007); chấp nhận vượt appetite về giờ công AI (không phải tiền).

### Câu hỏi còn mở (BUILD, eng-developer 2026-10-25)
- ~~Q6~~ **Đã đóng (QA fix round 1, T19, ADR 0007):** cổng bằng chứng trên chunk tốt nhất được giữ, nhưng
  ngưỡng điểm BM25 thô (`DOCQA_MIN_SCORE`) bị thay bằng độ phủ câu hỏi có trọng số IDF (`DOCQA_MIN_COVERAGE` =
  0.5), vì QA chứng minh ngưỡng cũ chặn phần lớn câu hỏi ngắn tự nhiên. Hiệu chỉnh trên bộ dev, kiểm trên bộ
  holdout riêng (số liệu trong ADR 0007). sol-architect xem lại ADR 0007 khi rà soát; không cần sửa tài liệu mẫu.
- Q7 (T14, Q4): TASKS T14 mới ghi "push repo private `kaikeel/docqa`", nhưng phiên BUILD được giao kèm ràng buộc
  "không push, không tạo repo GitHub". Chưa push; việc push để lại cho bước sau QA + Security theo Q4.
- Q8 (board): không tìm thấy issue dự án docqa trên `kaikeel/ops` nên chưa comment "T<n> done" lên board; cần
  PMO tạo issue (`ops.py project add`) nếu muốn theo dõi trên board.

### Câu hỏi còn mở (lịch sử)
- Q1 (AC1, AC6 — T13): Kiểm thủ công với API thật cần `ANTHROPIC_API_KEY`. Dùng key nào (key công ty của
  CEO?), ai chạy (eng-developer trong phiên có key, hay CEO tự chạy khi xem demo)? Chi phí dự kiến rất nhỏ
  (vài lời gọi), nhưng là thao tác liên quan tiền → cần CEO xác nhận.
- Q2 (appetite): Tổng ước lượng Eng là 11 giờ công AI (14 task, chưa gồm QA + Security). Nếu "1 ngày công AI"
  = 8 giờ thì vượt ~3 giờ. Đề xuất giữ nguyên scope, chấp nhận vượt nhẹ; nếu phải cắt thì bỏ chế độ eval đầy
  đủ (`citation_rate`) trước — chờ PMO/CEO quyết.
- Q3: Có cần tự đọc file `.env` (thêm `python-dotenv`) không? SPEC hiện chọn không (chỉ biến môi trường thật,
  Docker dùng `--env-file`) để giữ phụ thuộc tối thiểu.
- Q4: Bước tạo repo private trên org `kaikeel` và push (Milestone 1) do ai thực hiện và khi nào? SHAPE/BUILD
  không push.
- Q5: Bản `anthropic==2.3.0` cần hỗ trợ tham số `fallbacks` + beta `server-side-fallback-2026-07-01` trên
  `client.beta.messages.create`; T7 sẽ xác nhận bằng type check. Nếu SDK chưa có tham số này thì cần quyết định
  (nâng SDK / truyền qua `extra_body`) — sẽ ghi ADR, không tự đổi sang HTTP thô.

## Rủi ro
| Rủi ro | Khả năng | Ảnh hưởng | Xử lý |
|---|---|---|---|
| BM25 kém với câu hỏi diễn đạt khác tài liệu | TB | TB | Ghi rõ trong README; interface retriever để nâng cấp; eval đo được |
| Code AI "trông được nhưng mong manh" | TB | Cao | QA độc lập + security gate trước khi public |
| Lộ key khi demo | Thấp | Cao | `.env` gitignore, gitleaks trong security gate |

## Phê duyệt G2
- [x] Claude duyệt theo ADR 0005 (dự án nội bộ, không khách, không tiền) — ngày: 2026-10-25
- [ ] CEO duyệt public repo (Milestone 2) — việc gửi ra ngoài, phải hỏi CEO

### Quyết định cho câu hỏi còn mở (Claude, theo ADR 0005 — 2026-10-25)
- **Q1:** Agent không gọi API thật. QA kiểm AC1/AC6 bằng LLM giả + kiểm tra cấu trúc request. Lần chạy thật
  đầu tiên do **CEO tự chạy** bằng key của mình khi xem demo ở Milestone 2 (một lệnh `docqa ask`, chi phí vài cent).
- **Q2:** Giữ nguyên scope, chấp nhận vượt appetite ~3 giờ công AI (chi phí không đáng kể, portfolio cần đủ).
- **Q3:** Không thêm `python-dotenv`. README hướng dẫn `export` và Docker `--env-file .env`.
- **Q4:** Claude tạo repo **private** `kaikeel/docqa` và push sau khi QA + Security PASS (Milestone 1).
  Public repo là việc ra bên ngoài → hỏi CEO (Milestone 2).
- **Q5:** T7 kiểm SDK. Thiếu `fallbacks` → bỏ fallback, ghi ADR, vẫn dùng SDK chính thức (không HTTP thô).
- **uv:** máy dùng uv 0.6.3, không nâng cấp; lockfile tạo bằng bản này vẫn đọc được bởi uv mới trên CI.
