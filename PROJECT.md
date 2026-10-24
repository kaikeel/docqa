# PF-20261025-docqa — Kaikeel DocQA

- Freelancer project ID / link: — (dự án portfolio nội bộ, backlog B-014)
- Khách hàng: Kaikeel (nội bộ) · Người xem: khách tiềm năng trên Freelancer, khách SG/CN
- Giá trị: $0 · Loại: portfolio
- Appetite: tối đa 1 ngày công AI, ≤ 1 giờ CEO (chỉ xem demo, duyệt public)
- Trạng thái: SHAPE

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
- Eval: bộ câu hỏi mẫu trên tài liệu mẫu, đo retrieval hit@k (không cần API key) và tỉ lệ câu trả lời có trích dẫn.
- Tài liệu mẫu nhỏ, tự viết, được phép công khai, trong `examples/docs/`.
- Dockerfile, GitHub Actions CI (ruff, mypy, pytest + coverage), CHANGELOG, tag `v0.1.0`, license MIT.

## Ngoài phạm vi (Out of scope)
- Giao diện web (chỉ CLI + API).
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

## Milestone
| # | Đầu ra | Giá ($) | Ngày giao | Trạng thái |
|---|---|---|---|---|
| 1 | v0.1.0: toàn bộ AC1–AC7, repo riêng tư trên `kaikeel` | 0 | 2026-10-26 | todo |
| 2 | CEO duyệt → public repo + thêm vào `08-marketing-brand/portfolio.md` | 0 | sau duyệt | todo |

## Giả định & câu hỏi còn mở
- Model mặc định `claude-opus-5-5`, đổi qua biến `DOCQA_MODEL`. Bật server-side fallback khi bị từ chối.
- Chạy demo thật cần `ANTHROPIC_API_KEY` của người chạy; CI không gọi API.
- Python 3.12, quản lý bằng `uv`.

## Rủi ro
| Rủi ro | Khả năng | Ảnh hưởng | Xử lý |
|---|---|---|---|
| BM25 kém với câu hỏi diễn đạt khác tài liệu | TB | TB | Ghi rõ trong README; interface retriever để nâng cấp; eval đo được |
| Code AI "trông được nhưng mong manh" | TB | Cao | QA độc lập + security gate trước khi public |
| Lộ key khi demo | Thấp | Cao | `.env` gitignore, gitleaks trong security gate |

## Phê duyệt G2
- [x] Claude duyệt theo ADR 0005 (dự án nội bộ, không khách, không tiền) — ngày: 2026-10-25
- [ ] CEO duyệt public repo (Milestone 2) — việc gửi ra ngoài, phải hỏi CEO
