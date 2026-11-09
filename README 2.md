# LuậtAI — Hệ thống Truy vấn và Giải đáp Pháp luật Việt Nam ứng dụng AI & RAG

Đồ án môn học **Phân tích và Thiết kế Hướng đối tượng (OOAD)**: Xây dựng hệ thống hỏi đáp pháp luật Việt Nam kết hợp kiến trúc **Cơ sở dữ liệu kép (Relational DB + Vector DB)**, kỹ thuật **Local Embedding** (nhúng văn bản trực tiếp trên máy cục bộ để tiết kiệm quota API) và **Google Gemini API** theo mô hình **RAG (Retrieval-Augmented Generation)**.

## 1. Hệ thống làm gì? (Tổng quan & Chức năng)

### 1.1. Bài toán và Giải pháp
Khi tra cứu pháp luật, người dùng phổ thông thường đặt câu hỏi bằng ngôn ngữ tự nhiên (ví dụ: *"Thời gian thử việc tối đa là bao lâu?"*) thay vì nhớ chính xác số hiệu văn bản hay số Điều luật. Ngược lại, nếu chỉ hỏi trực tiếp các mô hình ngôn ngữ lớn (LLM) thông thường mà không có dữ liệu kiểm chứng, mô hình rất dễ gặp hiện tượng "ảo giác" (hallucination) — trích dẫn sai Điều luật hoặc áp dụng văn bản đã hết hiệu lực.

**LuậtAI** giải quyết bài toán này bằng quy trình **RAG (Retrieval-Augmented Generation)** tối ưu hóa chi phí:
- **Chống bịa đặt (Anti-Hallucination) & Trích dẫn minh bạch**: Mọi câu trả lời đều bắt buộc căn cứ trên các đoạn văn bản luật thực tế được truy xuất từ kho dữ liệu của hệ thống và hiển thị kèm thẻ nguồn trích dẫn (tên văn bản, số Điều luật, nội dung gốc và điểm tương đồng ngữ nghĩa).
- **Tiết kiệm 100% Quota API cho bước Embedding**: Toàn bộ quá trình băm văn bản luật thành vector (khi Admin tải tài liệu lên) và tạo vector cho câu hỏi (khi User truy vấn) được thực hiện **trực tiếp tại máy cục bộ (Local Embedding)**. Hệ thống chỉ gọi **Google Gemini API** duy nhất 1 lần ở bước tổng hợp câu trả lời cuối cùng.
- **Kết hợp đa mô hình Cơ sở dữ liệu**: Phối hợp chặt chẽ giữa **SQLite** (lưu trữ có cấu trúc: người dùng, phân quyền, metadata văn bản, toàn văn Điều luật, lịch sử hỏi đáp) và **ChromaDB** (lưu trữ vector nhiều chiều và tìm kiếm tương đồng Cosine).

### 1.2. Các tác nhân và Chức năng chính (Theo Sơ đồ Use Case UML)

| Tác nhân | Nhóm chức năng | Mô tả chi tiết |
|---|---|---|
| **Người dùng (`USER`)** | Đăng ký / Đăng nhập & Bảo mật | Tạo tài khoản mới, đăng nhập bằng Email hoặc Họ tên, đổi mật khẩu. Tự động khóa tài khoản và vô hiệu hóa biểu mẫu nếu nhập sai mật khẩu quá 5 lần liên tiếp. |
| **Người dùng (`USER`)** | Đặt câu hỏi & Nhận tư vấn pháp luật | Nhập câu hỏi bằng ngôn ngữ tự nhiên hoặc chọn từ danh sách câu hỏi gợi ý. Nhận câu trả lời do AI tổng hợp bám sát quy định pháp luật hiện hành. |
| **Người dùng (`USER`)** | Xem nguồn trích dẫn (`<<extend>>`) | Bấm vào từng thẻ nguồn (ví dụ: `Bộ luật Lao động 2019 · Điều 25`) dưới câu trả lời để mở hộp thoại xem toàn văn nội dung Điều luật gốc đã dùng làm căn cứ. |
| **Người dùng (`USER`)** | Xem lịch sử hội thoại | Tra cứu lại toàn bộ danh sách các câu hỏi đã đặt, thời gian, trạng thái xử lý và mở lại chi tiết cuộc hội thoại cũ. |
| **Quản trị viên (`ADMIN`)** | Quản lý người dùng | Xem danh sách toàn bộ tài khoản trong hệ thống, kiểm tra vai trò (`USER` / `ADMIN`), trạng thái hoạt động và thực hiện **Khóa / Mở khóa** tài khoản. |
| **Quản trị viên (`ADMIN`)** | Cập nhật dữ liệu pháp luật (RAG Ingest) | Tải lên các văn bản pháp luật mới (`.pdf`, `.docx`, `.txt`, `.md`) kèm thông tin Tiêu đề, Loại văn bản (Luật, Bộ luật, Nghị định, Thông tư), Cơ quan ban hành, Ngày ban hành để hệ thống tự động tách Điều, tạo Local Embedding và cập nhật vào kho RAG. |
| **Quản trị viên (`ADMIN`)** | Quản lý hệ thống | Theo dõi thống kê số lượng văn bản, số đoạn (chunks), trạng thái Vector Store và cấu hình tham số hệ thống (`system_config`). |
| **Hệ thống AI (`API LLM`)** | Sinh câu trả lời từ ngữ cảnh (`<<include>>`) | Nhận ngữ cảnh gồm Top-5 Điều luật tương đồng nhất kèm chỉ dẫn hệ thống (System Instruction) nghiêm ngặt để sinh câu trả lời chuẩn xác. |

## 2. Thiết kế Hệ thống (Kiến trúc, Hướng đối tượng & CSDL)

### 2.1. Kiến trúc tổng thể & Công nghệ sử dụng

| Tầng (Layer) | Công nghệ / Thư viện | Vai trò trong hệ thống |
|---|---|---|
| **Giao diện (Frontend)** | HTML5, CSS3, Vanilla JavaScript (`frontend/`) | Giao diện Single-Page Application (SPA) gọn nhẹ, không cần bước build, giao tiếp với Backend qua REST API cùng origin (`/api`). |
| **API & Điều phối (Backend)** | Python 3.10+, FastAPI, Uvicorn, Pydantic | Cung cấp RESTful API, kiểm tra tính hợp lệ dữ liệu đầu vào, phân quyền bằng Dependency Injection và phục vụ trực tiếp file tĩnh Frontend. |
| **Bảo mật (Security)** | `PyJWT` (`HS256`), `bcrypt` | Băm mật khẩu an toàn, cấp phát & xác thực JSON Web Token (JWT), kiểm soát số lần đăng nhập sai. |
| **Xử lý văn bản (Ingestion)** | `pypdf`, `python-docx`, Regex | Trích xuất văn bản từ `.pdf`, `.docx`, `.txt`, `.md`; làm sạch và chia đoạn thông minh theo từng `"Điều N"` (chồng lấp 200 ký tự). |
| **Local Embedding** | `sentence-transformers` (`paraphrase-multilingual-MiniLM-L12-v2`) + Bộ tạo vector tiếng Việt 384 chiều | Chuyển đổi văn bản tiếng Việt thành vector 384 chiều chuẩn hóa L2 ngay trên máy cục bộ, không tiêu tốn quota Gemini API. |
| **CSDL Vector (Vector DB)** | `ChromaDB` (`chroma_db/`) | Lưu trữ vector embedding và thực hiện tìm kiếm ngữ nghĩa theo độ tương đồng Cosine (`hnsw:space = "cosine"`). |
| **CSDL Quan hệ (Relational DB)** | `SQLite` (`DB/legal_rag.db`), `SQLAlchemy ORM` | Lưu trữ toàn vẹn dữ liệu quan hệ gồm 8 bảng, khóa ngoại, 6 chỉ mục (Index) và 3 Trigger tự động. |
| **Mô hình Ngôn ngữ (LLM)** | Google Gemini API (`gemini-2.5-flash` / `gemini-3.8-flash`) | Tổng hợp câu trả lời pháp lý từ ngữ cảnh Top-5 Điều luật truy xuất được. |

### 2.2. Thiết kế Hướng đối tượng (Ánh xạ Sơ đồ Lớp UML sang Mã nguồn)
Hệ thống được thiết kế tuân thủ chặt chẽ phương pháp hướng đối tượng trong tài liệu `UML.drawio.pdf` (tách biệt rõ **Lớp người dùng**, **Lớp nghiệp vụ chính**, **Lớp dịch vụ** và **Lớp dữ liệu / lưu trữ**):

| STT | Lớp trong UML | Phân loại lớp | File cài đặt trong dự án | Thuộc tính & Phương thức tiêu biểu |
|---|---|---|---|---|
| 1 | `User` | Lớp người dùng (Cha) | `app/models.py` | `user_id`, `full_name`, `email`, `password_hash`, `role`, `status`; `login()`, `logout()`, `changePassword()`, `updateProfile()` |
| 2 | `Admin` | Lớp người dùng (Kế thừa `User`) | `app/models.py` | Kế thừa `User`; `manageUser()`, `manageSystem()`, `updateLegalData()` |
| 3 | `Question` | Lớp nghiệp vụ chính | `app/models.py` | `question_id`, `user_id`, `content`, `status`, `created_at`; `process()`, `getAnswer()` |
| 4 | `Answer` | Lớp nghiệp vụ chính | `app/models.py` | `answer_id`, `question_id`, `content`, `model_name`, `created_at`; `getFormattedAnswer()` |
| 5 | `SourceDocument` | Lớp dữ liệu / lưu trữ | `app/models.py` | `document_id`, `title`, `document_type`, `issue_date`, `issuing_agency`, `content`; `getRelevantChunks()`, `getMetadata()` |
| 6 | `DocumentChunk` | Lớp dữ liệu / lưu trữ | `app/models.py` | `chunk_id`, `document_id`, `chunk_index`, `content`, `token_count`; `getContent()`, `getArticleLabel()` |
| 7 | `AnswerSource` | Lớp dữ liệu liên kết (N-N) | `app/models.py` | Liên kết `Answer` với `SourceDocument` và `DocumentChunk` kèm thứ hạng `rank_no` và điểm `score` |
| 8 | `ChatHistory` | Lớp dữ liệu / lưu trữ | `app/models.py` | `history_id`, `user_id`, `question_id`, `answer_id`, `created_at` |
| 9 | `SystemConfig` | Lớp hỗ trợ cấu hình | `app/models.py` | `config_key`, `config_value`, `updated_by`, `updated_at` |
| 10 | `Database` | Lớp dữ liệu / kết nối | `app/database.py` | `dbType`, `connectionString`; `connect()`, `executeQuery()`, `close()`, `init_db()`, `get_db()` |
| 11 | `VectorStore` (`VectorDB`) | Lớp dữ liệu Vector | `app/vector_store.py` | `dbId`, `type`, `connectionString`; `storeEmbedding()`, `search()`, `delete()`, `count()` |
| 12 | `DocumentProcessor` | Lớp dịch vụ xử lý tài liệu | `app/document_processor.py` | `chunkSize`, `overlap`; `readDocument()`, `splitIntoChunks()`, `generateEmbedding()` |
| 13 | `LocalEmbeddingEngine` & `Embedding` | Lớp dịch vụ nhúng cục bộ | `app/gemini_client.py` | `embeddingId`, `chunkId`, `vector`, `model`; `embed_documents()`, `embed_query()`, `generate()` |
| 14 | `GeminiClient` (`AIService`) | Lớp dịch vụ gọi AI API | `app/gemini_client.py` | `apiKey`, `model`; `callAPI()`, `generate_answer()` |
| 15 | `RAGService` | Lớp dịch vụ điều phối RAG | `app/rag_service.py` | Kết nối `VectorStore`, `GeminiClient`, `DocumentProcessor`; `ingestDocument()`, `searchDocuments()`, `getRelevantDocs()`, `buildContext()`, `answerQuestion()` |
| 16 | `AuthService` | Lớp dịch vụ bảo mật | `app/auth_utils.py` | `jwtSecret`; `authenticate()`, `authorize()`, `validateToken()`, `hash_password()`, `create_access_token()` |

### 2.3. Thiết kế Cơ sở dữ liệu Quan hệ (`DB/legal_rag_schema_sqlite.sql`) và Vector DB (`chroma_db/`)

#### A. Cơ sở dữ liệu quan hệ SQLite (8 bảng chuẩn hóa)
File `DB/legal_rag_schema_sqlite.sql` định nghĩa 8 bảng với `PRAGMA foreign_keys = ON`, 6 chỉ mục tăng tốc truy vấn và 3 Trigger tự động cập nhật `updated_at`:

| Tên bảng | Khóa chính (`PK`) | Khóa ngoại (`FK`) & Ràng buộc | Vai trò lưu trữ |
|---|---|---|---|
| `users` | `user_id` | `email UNIQUE`, `role IN ('USER','ADMIN')`, `status IN (0,1)` | Lưu thông tin tài khoản, mật khẩu băm, vai trò, trạng thái khóa và bộ đếm `failed_login_attempts`. |
| `source_documents` | `document_id` | `created_by -> users(user_id) ON DELETE SET NULL` | Lưu thông tin văn bản pháp luật (tiêu đề, loại, cơ quan ban hành, ngày ban hành, tên file và nội dung toàn văn). |
| `document_chunks` | `chunk_id` | `document_id -> source_documents(document_id) ON DELETE CASCADE`, `UNIQUE(document_id, chunk_index)` | Lưu từng đoạn văn bản pháp luật sau khi tách theo `"Điều N"` kèm thứ tự đoạn và ước lượng số token. |
| `questions` | `question_id` | `user_id -> users(user_id) ON DELETE CASCADE`, `status IN ('PENDING','PROCESSING','COMPLETED','FAILED')` | Lưu câu hỏi của người dùng và trạng thái xử lý trong pipeline RAG. |
| `answers` | `answer_id` | `question_id UNIQUE -> questions(question_id) ON DELETE CASCADE` | Lưu câu trả lời do AI sinh ra (quan hệ 1-1 với `questions`) và tên model đã sử dụng. |
| `answer_sources` | `(answer_id, document_id, chunk_id)` | `answer_id -> answers`, `document_id -> source_documents`, `chunk_id -> document_chunks` | Bảng trung gian (quan hệ N-N) lưu danh sách các Điều luật được trích dẫn cho mỗi câu trả lời kèm `rank_no` và điểm tương đồng `score`. |
| `chat_histories` | `history_id` | `user_id -> users`, `question_id -> questions`, `answer_id -> answers` | Lưu lịch sử hội thoại theo thời gian của từng người dùng. |
| `system_config` | `config_key` | `updated_by -> users(user_id) ON DELETE SET NULL` | Lưu cấu hình hệ thống (`embedding_provider`, `local_embedding_model`, `gemini_model`, `rag_top_k`...). |

#### B. Cơ sở dữ liệu Vector ChromaDB & Cơ chế Đồng bộ 2 pha (Two-Phase Rollback)
- Mỗi bản ghi trong bảng `document_chunks` của SQLite có một vector tương ứng trong collection `legal_chunks` của **ChromaDB** với **`id` trùng khớp hoàn toàn với `chunk_id`**.
- **Đảm bảo tính toàn vẹn giữa 2 CSDL**: Trong `RAGService.ingestDocument()`, nếu quá trình lưu vào SQLite hoặc lưu vector vào ChromaDB phát sinh bất kỳ lỗi nào, hệ thống lập tức thực thi `db.rollback()` trên SQLite đồng thời gọi `vectorDB.delete(ids=chunk_ids, document_id=doc_id)` trên ChromaDB để hai kho dữ liệu không bao giờ bị lệch nhau.
- Ngoài ra, nếu thư mục `chroma_db/` bị xóa thủ công, hàm `_resync_vector_store_from_sqlite()` trong `app/seed.py` sẽ tự động tái tạo lại toàn bộ vector từ bảng `document_chunks` của SQLite ngay khi khởi động server.

### 2.4. Thiết kế Chi tiết các Luồng Nghiệp vụ

1. **Luồng Nạp Văn bản Pháp luật (Admin Ingestion Pipeline)**:
   - **Bước 1**: Admin tải lên file `.pdf`, `.docx`, `.txt` hoặc `.md` qua `POST /api/admin/documents`.
   - **Bước 2**: `DocumentProcessor` đọc văn bản, chuẩn hóa khoảng trắng và dùng biểu thức chính quy tách văn bản theo từng **`"Điều N"`**. Nếu một Điều luật dài quá `1200` ký tự, hệ thống tự động chia nhỏ thành các đoạn con chồng lấp nhau **`200` ký tự** (`CHUNK_OVERLAP_CHARS = 200`) và gắn nhãn `"Điều N (tiếp theo):"` ở đầu mỗi đoạn con để không mất ngữ cảnh.
   - **Bước 3**: `LocalEmbeddingEngine` tính toán vector embedding 384 chiều trực tiếp trên máy cục bộ (không tốn quota API).
   - **Bước 4**: Lưu đồng bộ vào SQLite (`source_documents`, `document_chunks`) và ChromaDB (`legal_chunks`).

2. **Luồng Hỏi đáp Pháp luật bằng RAG (User Q&A Pipeline)**:
   - **Bước 1**: Lưu câu hỏi vào bảng `questions` với trạng thái `status = 'PROCESSING'`.
   - **Bước 2**: Tạo vector embedding cho câu hỏi bằng **Local Embedding** (cùng không gian vector với tài liệu).
   - **Bước 3**: Truy vấn ChromaDB để tìm **Top 5** đoạn Điều luật có độ tương đồng Cosine cao nhất (`RAG_TOP_K = 5`).
   - **Bước 4**: Đối chiếu `chunk_id` với SQLite để lấy đầy đủ tên văn bản, số Điều luật và ghép thành khối `[NGỮ CẢNH PHÁP LUẬT ĐƯỢC TRUY XUẤT]` kèm `SYSTEM_INSTRUCTION_LEGAL_RAG` (yêu cầu chỉ trả lời theo ngữ cảnh, bắt buộc trích dẫn Điều luật và không tự suy diễn).
   - **Bước 5**: Gọi **Google Gemini API** để sinh câu trả lời.
   - **Bước 6**: Lưu kết quả vào các bảng `answers`, `answer_sources`, `chat_histories` và cập nhật câu hỏi thành `COMPLETED` (nếu gọi API lỗi, cập nhật trạng thái thành `FAILED`).

3. **Luồng Bảo mật Đăng nhập & Tự động Khóa tài khoản (Theo Activity Diagram UML trang 14)**:
   - Mỗi lần đăng nhập sai mật khẩu, cột `failed_login_attempts` của người dùng tăng thêm 1 và hệ thống thông báo số lần thử còn lại.
   - Khi chạm ngưỡng `MAX_FAILED_LOGIN_ATTEMPTS = 5`, hệ thống tự động chuyển `status = 0` (Khóa tài khoản) và trả về mã `403 Forbidden` kèm thông điệp `"Tài khoản đã bị khóa..."`. Giao diện `app.js` nhận diện thông báo này và lập tức khóa toàn bộ ô nhập liệu trên màn hình đăng nhập.

### 2.5. Cấu trúc Thư mục Dự án

```text
RAG/
├── main.py                         # Điểm khởi động FastAPI, khởi tạo DB/Seed và mount Frontend
├── run_windows.bat                 # Script chạy tự động 1-click trên Windows / Antigravity
├── requirements.txt                # Danh sách các thư viện Python cần cài đặt
├── .env.example                    # File mẫu cấu hình biến môi trường
├── .env                            # File cấu hình thực tế (điền GEMINI_API_KEY tại đây)
├── README.md                       # Tài liệu hướng dẫn chi tiết hệ thống
├── DB/
│   ├── legal_rag_schema_sqlite.sql # Lược đồ SQLite (8 bảng, khóa ngoại, 6 index, 3 trigger)
│   └── legal_rag.db                # File CSDL SQLite (tự động tạo và seed khi chạy)
├── chroma_db/                      # Thư mục lưu trữ Vector DB của ChromaDB
├── sample_docs/                    # 3 văn bản pháp luật Việt Nam mẫu nạp sẵn khi khởi chạy
│   ├── bo_luat_lao_dong_2019.txt
│   ├── bo_luat_dan_su_2015_thua_ke.txt
│   └── luat_giao_thong_nghi_dinh_168.txt
├── app/
│   ├── __init__.py
│   ├── config.py                   # Đọc và quản lý cấu hình từ file .env
│   ├── database.py                 # Kết nối SQLite (tương thích Windows NTFS), bật khóa ngoại
│   ├── models.py                   # Các lớp ORM & phương thức OOP theo sơ đồ lớp UML
│   ├── schemas.py                  # Các lớp Pydantic kiểm tra định dạng JSON Request/Response
│   ├── mappers.py                  # Chuyển đổi đối tượng CSDL sang JSON theo contract của app.js
│   ├── auth_utils.py               # Lớp AuthService: băm mật khẩu bcrypt, tạo/giải mã JWT
│   ├── dependencies.py             # FastAPI Dependencies: xác thực người dùng và quyền ADMIN
│   ├── seed.py                     # Khởi tạo tài khoản Admin/User mặc định & văn bản luật mẫu
│   ├── gemini_client.py            # LocalEmbeddingEngine (nhúng cục bộ) & GeminiClient (gọi AI API)
│   ├── document_processor.py       # Đọc TXT/MD/PDF/DOCX, làm sạch và chia đoạn theo "Điều N"
│   ├── vector_store.py             # Lớp VectorStore thao tác với ChromaDB (Cosine similarity)
│   ├── rag_service.py              # Lớp RAGService: điều phối luồng nạp văn bản và luồng hỏi đáp
│   └── routers/
│       ├── __init__.py
│       ├── auth.py                 # Các API xác thực (/api/auth/*)
│       ├── chat.py                 # Các API hỏi đáp & lịch sử (/api/questions, /api/history)
│       └── admin.py                # Các API quản trị (/api/admin/*)
└── frontend/
    ├── index.html                  # Trang khung HTML chính của ứng dụng
    ├── styles.css                  # Giao diện CSS (Responsive, Sidebar, Chat, Modal, Table)
    └── app.js                      # Logic giao diện Vanilla JS kết nối với Backend (/api)
```

### 2.6. Danh sách API Endpoints

| Phương thức | Đường dẫn (Endpoint) | Quyền truy cập | Mô tả chức năng |
|---|---|---|---|
| `GET` | `/api/health` | Công khai | Kiểm tra trạng thái server, chế độ Local Embedding, số lượng vector và trạng thái Gemini API Key. |
| `POST` | `/api/auth/login` | Công khai | Đăng nhập bằng Email hoặc Họ tên (`identifier`, `password`), trả về `user` và `token` JWT. |
| `POST` | `/api/auth/register` | Công khai | Đăng ký tài khoản người dùng mới (`name`, `email`, `password` tối thiểu 8 ký tự). |
| `GET` | `/api/auth/me` | Yêu cầu JWT | Kiểm tra phiên đăng nhập và lấy thông tin người dùng hiện tại. |
| `POST` | `/api/auth/change-password` | Yêu cầu JWT | Đổi mật khẩu (`currentPassword`, `newPassword`). |
| `POST` | `/api/questions` | Yêu cầu JWT | Gửi câu hỏi pháp luật (`content`), thực thi pipeline RAG và trả về câu trả lời kèm danh sách `sources`. |
| `GET` | `/api/history` | Yêu cầu JWT | Lấy danh sách lịch sử các cuộc hội thoại của người dùng đang đăng nhập. |
| `GET` | `/api/admin/users` | Chỉ `ADMIN` | Lấy danh sách toàn bộ người dùng trong hệ thống. |
| `PATCH` | `/api/admin/users/{user_id}/status` | Chỉ `ADMIN` | Khóa (`status: false`) hoặc Mở khóa (`status: true`) tài khoản người dùng. |
| `GET` | `/api/admin/documents` | Chỉ `ADMIN` | Lấy danh sách các văn bản pháp luật trong kho kèm số lượng đoạn (`chunks`). |
| `POST` | `/api/admin/documents` | Chỉ `ADMIN` | Upload file văn bản luật mới (`multipart/form-data`: `file`, `title`, `type`, `agency`, `issueDate`). |
| `DELETE` | `/api/admin/documents/{document_id}` | Chỉ `ADMIN` | Xóa văn bản pháp luật khỏi cả SQLite và ChromaDB. |

## 3. Hướng dẫn Chạy trên Antigravity IDE (Windows)

### 3.1. Yêu cầu môi trường trên Windows
- **Python**: Phiên bản `3.10` – `3.12` dành cho Windows (khi cài đặt Python trên Windows, nhớ tích chọn ô **"Add python.exe to PATH"**).
- **IDE**: Google Antigravity trên Windows.
- **Google Gemini API Key**: Lấy miễn phí tại Google AI Studio (`https://aistudio.google.com/`).

### 3.2. Các bước mở và chạy dự án trong Antigravity (Windows)

#### Bước 1: Mở thư mục `RAG` trong Antigravity
1. Giải nén file `RAG_Legal_AI_Project.zip` ra máy tính (ví dụ: `D:\RAG` hoặc `C:\Users\<TenBan>\Desktop\RAG`).
2. Mở **Antigravity**, chọn **File -> Open Folder...** và chọn đúng thư mục **`RAG`** (thư mục có chứa file `main.py` và `requirements.txt`).
3. Bấm tổ hợp phím `` Ctrl + ` `` (hoặc chọn **Terminal -> New Terminal** trên thanh menu) để mở cửa sổ Terminal tích hợp bên dưới Antigravity.

#### Bước 2: Điền `GEMINI_API_KEY` vào file `.env`
Trong thanh Explorer bên trái của Antigravity, bấm vào file **`.env`** và điền API Key của bạn vào dòng đầu tiên:
```env
GEMINI_API_KEY=AIzaSy_DIEN_API_KEY_CUA_BAN_VAO_DAY
GEMINI_MODEL=gemini-2.5-flash
EMBEDDING_PROVIDER=local
LOCAL_EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
ALLOW_EXTRACTIVE_FALLBACK=true
```
- **Lưu ý**: Ngay cả khi bạn chưa điền `GEMINI_API_KEY`, nhờ `ALLOW_EXTRACTIVE_FALLBACK=true`, hệ thống vẫn chạy được hoàn chỉnh bước **Local Embedding + Tìm kiếm Cosine trong ChromaDB** và hiển thị trực tiếp nội dung Điều luật trích xuất được.

#### Bước 3: Khởi chạy dự án trong Terminal của Antigravity (2 cách)

- **Cách 1 — Chạy nhanh tự động bằng file `run_windows.bat` (Khuyên dùng trên Windows)**:
  Tại cửa sổ Terminal của Antigravity (PowerShell hoặc CMD), gõ lệnh:
  ```powershell
  .\run_windows.bat
  ```
  Script sẽ tự động tạo môi trường ảo `venv`, cài đặt các thư viện trong `requirements.txt` và khởi động server tại `http://127.0.0.1:8000`.

- **Cách 2 — Chạy từng lệnh thủ công trên PowerShell của Antigravity**:
  Nếu bạn muốn tự gõ từng lệnh trong PowerShell của Windows:
  ```powershell
  # 1. Tạo môi trường ảo venv
  python -m venv venv

  # 2. Cài đặt thư viện trực tiếp bằng python trong venv (không lo lỗi ExecutionPolicy của PowerShell)
  .\venv\Scripts\python.exe -m pip install --upgrade pip
  .\venv\Scripts\python.exe -m pip install -r requirements.txt

  # 3. Chạy server (hoặc chạy: .\venv\Scripts\python.exe main.py)
  .\venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
  ```
  *(Mẹo trên Windows PowerShell: Nếu bạn muốn gõ `.\venv\Scripts\Activate.ps1` mà gặp thông báo đỏ `running scripts is disabled on this system`, chỉ cần chạy lệnh `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` trước hoặc dùng trực tiếp `.\venv\Scripts\python.exe` như trên).*

#### Bước 4: Mở Giao diện Web
Khi Terminal hiện dòng `Uvicorn running on http://127.0.0.1:8000`, giữ phím **`Ctrl` + Click chuột** vào đường dẫn trong Terminal của Antigravity:
- **Giao diện Web LuậtAI**: `http://127.0.0.1:8000`
- **Tài liệu Swagger API**: `http://127.0.0.1:8000/docs`
- **Kiểm tra Health Check**: `http://127.0.0.1:8000/api/health`

### 3.3. Tài khoản mặc định & Dữ liệu pháp luật nạp sẵn
Khi khởi chạy lần đầu, module `app/seed.py` tự động tạo CSDL `DB/legal_rag.db`, khởi tạo 2 tài khoản mặc định và nạp sẵn 3 văn bản pháp luật Việt Nam (`Bộ luật Lao động số 45/2019/QH14`, `Bộ luật Dân sự số 91/2015/QH13 - Chế định Thừa kế`, `Luật TTATGT đường bộ 2024 & Nghị định 168/2024/NĐ-CP`) vào SQLite và ChromaDB:

| Vai trò | Tên đăng nhập hoặc Email | Mật khẩu | Chức năng trải nghiệm |
|---|---|---|---|
| **Quản trị viên (`ADMIN`)** | `admin@example.com` (hoặc `Quản trị viên`) | `admin12345` | Có đầy đủ 4 tab: **Hỏi đáp**, **Lịch sử**, **Người dùng** (khóa/mở khóa tài khoản) và **Văn bản** (upload thêm luật mới). |
| **Người dùng (`USER`)** | `user@example.com` (hoặc `Nguyễn Văn A`) | `user12345` | Có 2 tab: **Hỏi đáp** (tra cứu pháp luật, xem nguồn trích dẫn) và **Lịch sử** (xem lại hội thoại), kèm nút **Đổi mật khẩu**. |

### 3.4. Hướng dẫn thao tác trên Giao diện Web

1. **Tra cứu & Hỏi đáp pháp luật (Tab `💬 Hỏi đáp`)**:
   - Sau khi đăng nhập, bạn có thể bấm trực tiếp vào một trong 4 **Câu hỏi gợi ý** ở cột bên phải (ví dụ: *"Thời gian thử việc tối đa là bao lâu?"*, *"Quy định về quyền thừa kế theo pháp luật?"*, *"Khi nào người điều khiển xe bị xử phạt?"*) hoặc tự gõ câu hỏi mới vào ô nhập liệu rồi bấm **Gửi câu hỏi ↗** (hoặc tổ hợp phím `Ctrl + Enter`).
   - Ngay bên dưới câu trả lời của **LuậtAI**, các thẻ nguồn trích dẫn sẽ xuất hiện (ví dụ: `📄 Bộ luật Lao động số 45/2019/QH14 · Điều 25`). Bấm vào thẻ nguồn bất kỳ để mở cửa sổ xem chi tiết số Điều và nội dung trích đoạn gốc trong luật.
2. **Xem lại lịch sử tư vấn (Tab `🕘 Lịch sử`)**:
   - Hiển thị danh sách toàn bộ các câu hỏi bạn đã đặt kèm thời gian và trạng thái `Đã xử lý`. Bấm nút **Xem** ở dòng bất kỳ để nạp lại toàn bộ nội dung câu hỏi, câu trả lời và các thẻ nguồn trích dẫn vào màn hình trò chuyện.
3. **Nạp thêm văn bản pháp luật mới (Tab `📚 Văn bản` — Dành cho Admin)**:
   - Đăng nhập bằng tài khoản `admin@example.com` / `admin12345` và chọn mục **Văn bản** trên thanh menu trái.
   - Chọn file văn bản pháp luật (`.pdf`, `.docx`, `.txt`, `.md`) từ máy tính, điền **Tiêu đề**, chọn **Loại văn bản** (`Luật`, `Bộ luật`, `Nghị định`, `Thông tư`), **Cơ quan ban hành**, **Ngày ban hành** rồi bấm **Tải lên & cập nhật RAG**.
   - Hệ thống sẽ tự động tách văn bản theo từng `"Điều N"`, tạo Local Embedding, lưu vào SQLite + ChromaDB và cập nhật ngay số lượng `Chunks` trên bảng danh sách tài liệu.
4. **Quản lý và Khóa/Mở khóa người dùng (Tab `👥 Người dùng` — Dành cho Admin)**:
   - Tại mục **Người dùng**, Admin có thể theo dõi trạng thái (`Hoạt động` / `Đã khóa`) của từng tài khoản và bấm nút **Khóa** hoặc **Mở khóa** (ví dụ: mở khóa lại cho người dùng bị khóa tự động sau 5 lần nhập sai mật khẩu).