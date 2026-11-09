# HƯỚNG DẪN CHI TIẾT CÁCH CHẠY HỆ THỐNG LUẬTAI (TỪ A ĐẾN Z)

Tài liệu này hướng dẫn chi tiết từng bước thao tác từ lúc lấy mã nguồn từ GitHub về máy tính cho đến khi khởi động và sử dụng hệ thống **LuậtAI** trên trình duyệt web. 

Hướng dẫn áp dụng cho mọi trình soạn thảo phổ biến: **Antigravity IDE**, **Visual Studio Code (VS Code)**, **PyCharm**, hoặc chạy trực tiếp bằng **Terminal / Command Prompt**.

> [!NOTE]
> Tài liệu phân tích thiết kế chi tiết (kiến trúc, sơ đồ lớp UML, sơ đồ CSDL, thuật ngữ hướng đối tượng) được lưu giữ nguyên vẹn tại file [readme (1).md](file:///d:/Documents/VSCode/RAG/readme%20(1).md).

---

## MỤC LỤC CÁC BƯỚC THỰC HIỆN 

1. [Bước 1: Chuẩn bị phần mềm cần thiết](#bước-1-chuẩn-bị-phần-mềm-cần-thiết)
2. [Bước 2: Lấy mã nguồn từ GitHub về máy tính](#bước-2-lấy-mã-nguồn-từ-github-về-máy-tính)
3. [Bước 3: Mở thư mục dự án bằng IDE hoặc Trình soạn thảo](#bước-3-mở-thư-mục-dự-án-bằng-ide-hoặc-trình-soạn-thảo)
4. [Bước 4: Mở Terminal và tạo Môi trường ảo Python (Virtual Environment)](#bước-4-mở-terminal-và-tạo-môi-trường-ảo-python-virtual-environment)
5. [Bước 5: Cài đặt các thư viện phụ thuộc (`requirements.txt`)](#bước-5-cài-đặt-các-thư-viện-phụ-thuộc-requirementstxt)
6. [Bước 6: Lấy Google Gemini API Key và cấu hình file `.env`](#bước-6-lấy-google-gemini-api-key-và-cấu-hình-file-env)
7. [Bước 7: Khởi chạy hệ thống](#bước-7-khởi-chạy-hệ-thống)
8. [Bước 8: Mở trình duyệt Web và trải nghiệm hệ thống](#bước-8-mở-trình-duyệt-web-và-trải-nghiệm-hệ-thống)
9. [Bước 9: Cách dừng hoặc khởi động lại hệ thống](#bước-9-cách-dừng-hoặc-khởi-động-lại-hệ-thống)
10. [Xử lý các lỗi thường gặp (Troubleshooting)](#xử-lý-các-lỗi-thường-gặp-troubleshooting)

---

## BƯỚC 1: CHUẨN BỊ PHẦN MỀM CẦN THIẾT

Trước khi bắt đầu, hãy đảm bảo máy tính của bạn đã cài đặt các phần mềm sau:

1. **Python** (phiên bản `3.10` trở lên, khuyến nghị `3.11` hoặc `3.12`):
   - Tải tại trang chủ: [https://www.python.org/downloads/](https://www.python.org/downloads/)
   - **CỰC KỲ QUAN TRỌNG KHI CÀI TRÊN WINDOWS**: Ở màn hình cài đặt đầu tiên, **bắt buộc tích chọn ô "Add python.exe to PATH"** trước khi bấm *Install Now*.
2. **Trình soạn thảo / IDE** (chọn 1 trong các ứng dụng sau tùy bạn thích):
   - **Antigravity IDE**
   - **Visual Studio Code (VS Code)**: [https://code.visualstudio.com/](https://code.visualstudio.com/)
   - **PyCharm**: [https://www.jetbrains.com/pycharm/](https://www.jetbrains.com/pycharm/)
   - Hoặc chỉ cần **PowerShell / Command Prompt / Terminal** có sẵn trên máy.
3. **Trình duyệt web**: Google Chrome, Microsoft Edge, Cốc Cốc, Brave, Firefox hoặc Safari.

---

## BƯỚC 2: LẤY MÃ NGUỒN TỪ GITHUB VỀ MÁY TÍNH

Bạn có thể chọn **Cách 1 (tải file ZIP - dành cho người không dùng Git)** hoặc **Cách 2 (dùng lệnh Git Clone)**:

### Cách 1: Tải file nén `.ZIP` (Dễ nhất cho mọi người)
1. Mở trang repository GitHub của dự án trên trình duyệt.
2. Tìm nút màu xanh lá cây **`<> Code`** ở phía trên danh sách file.
3. Bấm vào nút đó và chọn **`Download ZIP`**.
4. Sau khi tải xong file (ví dụ `RAG-main.zip`):
   - Chuột phải vào file `.zip` vừa tải -> Chọn **Extract All...** (Giải nén).
   - Chọn thư mục bạn muốn lưu (ví dụ: `D:\Documents\VSCode\RAG`).
   - Bấm **Extract**.

### Cách 2: Dùng lệnh `git clone` (Nếu đã cài Git)
1. Mở cửa sổ **Terminal** (macOS/Linux) hoặc **PowerShell / Command Prompt** (Windows).
2. Di chuyển đến thư mục bạn muốn lưu dự án (ví dụ `D:\Documents\VSCode`):
   ```bash
   cd D:\Documents\VSCode
   ```
3. Chạy lệnh clone:
   ```bash
   git clone <URL_GITHUB_CỦA_DỰ_ÁN>.git
   cd RAG
   ```

---

## BƯỚC 3: MỞ THƯ MỤC DỰ ÁN BẰNG IDE HOẶC TRÌNH SOẠN THẢO

Mở ứng dụng lập trình mà bạn sử dụng:

### Nếu dùng Antigravity IDE hoặc VS Code:
1. Mở **Antigravity IDE** hoặc **VS Code**.
2. Trên thanh menu trên cùng, chọn: **File** > **Open Folder...** (hoặc bấm tổ hợp phím `Ctrl + K, Ctrl + O` trên Windows, `Cmd + O` trên Mac).
3. Tìm và chọn đúng thư mục `RAG` (thư mục chứa file `main.py`, `requirements.txt`). Bấm **Select Folder**.
4. Cột bên trái (*Explorer*) sẽ hiển thị đầy đủ cây thư mục dự án gồm các thư mục `app`, `DB`, `frontend`, `sample_docs`...

### Nếu dùng PyCharm:
1. Mở **PyCharm**.
2. Chọn **Open** (hoặc **File** > **Open...**).
3. Điều hướng đến thư mục `RAG` và bấm **OK** -> Chọn *Trust Project*.

### Nếu không dùng IDE (chỉ dùng CMD / PowerShell):
1. Nhấn phím `Windows + R`, gõ `powershell` hoặc `cmd` rồi bấm **Enter**.
2. Dùng lệnh `cd` để đi vào thư mục dự án:
   ```powershell
   cd D:\Documents\VSCode\RAG
   ```

---

## BƯỚC 4: MỞ TERMINAL VÀ TẠO MÔI TRƯỜNG ẢO PYTHON (VIRTUAL ENVIRONMENT)

Môi trường ảo (venv) giúp cài đặt các thư viện riêng biệt cho dự án, không làm xung đột với các phiên bản Python khác trên máy tính của bạn.

### 4.1. Mở Terminal bên trong IDE
- Trong **Antigravity IDE** hoặc **VS Code**: 
  - Bấm tổ hợp phím: **``Ctrl + ` ``** (phím dấu huyền nằm cạnh số 1 trên bàn phím).
  - Hoặc chọn trên menu: **Terminal** > **New Terminal**.
- Trong **PyCharm**: Bấm vào tab **Terminal** ở thanh dưới cùng của cửa sổ.

### 4.2. Tạo môi trường ảo
Nhập dòng lệnh sau vào Terminal và nhấn **Enter**:

```powershell
python -m venv venv
```
*(Đợi khoảng 5-10 giây để Python tạo thư mục `venv` trong dự án).*

### 4.3. Kích hoạt môi trường ảo

Tùy vào hệ điều hành và loại Terminal bạn đang mở, chạy lệnh tương ứng:

- **Nếu dùng Windows (PowerShell - mặc định của VS Code / Antigravity)**:
  ```powershell
  .\venv\Scripts\Activate.ps1
  ```
  *(Nếu gặp thông báo lỗi màu đỏ về `Execution_Policies`, hãy xem cách khắc phục ở [Mục 10](#102-lỗi-running-scripts-is-disabled-trên-powershell-khi-chạy-activateps1)).*

- **Nếu dùng Windows (Command Prompt - cmd.exe)**:
  ```cmd
  venv\Scripts\activate.bat
  ```

- **Nếu dùng macOS hoặc Linux**:
  ```bash
  source venv/bin/activate
  ```

> [!TIP]
> **Dấu hiệu kích hoạt thành công**: Ở đầu dòng lệnh của Terminal sẽ xuất hiện tiền tố **`(venv)`**, ví dụ:  
> `(venv) PS D:\Documents\VSCode\RAG>`

---

## BƯỚC 5: CÀI ĐẶT CÁC THƯ VIỆN PHỤ THUỘC (`requirements.txt`)

Khi đã thấy chữ `(venv)` ở đầu dòng lệnh, hãy chạy lệnh cài đặt toàn bộ thư viện:

```powershell
pip install -r requirements.txt
```

Quá trình này sẽ tự động tải và cài đặt:
- **FastAPI**, **Uvicorn**: Máy chủ backend REST API.
- **ChromaDB**: Cơ sở dữ liệu Vector lưu trữ ngữ nghĩa điều luật.
- **Sentence-Transformers**: Tạo embedding trực tiếp trên máy (không tốn tiền API).
- **PyPDF**, **python-docx**: Đọc tài liệu PDF, Word khi nạp thêm luật mới.
- **PyJWT**, **bcrypt**: Bảo mật, băm mật khẩu và xác thực người dùng.

> [!NOTE]
> Quá trình cài đặt lần đầu có thể mất từ 1 đến 3 phút tùy tốc độ mạng của bạn. Hãy chờ cho đến khi terminal chạy xong và hiển thị lại dòng nhập lệnh bình thường.

---

## BƯỚC 6: LẤY GOOGLE GEMINI API KEY VÀ CẤU HÌNH FILE `.ENV`

Hệ thống sử dụng **Google Gemini API** để tổng hợp câu trả lời thông minh dựa trên các Điều luật truy xuất được. API Key này được Google cấp **hoàn toàn miễn phí**.

### 6.1. Cách lấy API Key (Miễn phí 100%)
1. Mở trình duyệt web và truy cập vào: **[https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)**
2. Đăng nhập bằng tài khoản Google (Gmail) cá nhân của bạn.
3. Bấm vào nút **"Create API key"** (hoặc **"Get API key"**).
4. Chọn **"Create API key in new project"** (Tạo trong project mới).
5. Sau khi tạo xong, bấm nút **Copy** để sao chép chuỗi key (thường có dạng bắt đầu bằng `AQ....` hoặc `AIzaSy....`).

### 6.2. Cấu hình file `.env` trong dự án
1. Quay lại IDE (Antigravity / VS Code).
2. Nhìn vào danh sách file ở cột bên trái:
   - Nếu đã có sẵn file `.env`: Bấm chuột trái vào file **[.env](file:///d:/Documents/VSCode/RAG/.env)** để mở.
   - Nếu chưa có file `.env`: Tìm file `.env.example`, bấm chuột phải chọn **Copy**, sau đó bấm **Paste** và đổi tên thành **`.env`** (hoặc gõ lệnh `copy .env.example .env` trong terminal).
3. Dán API Key bạn vừa copy vào dòng số 1 (sau dấu `=`):
   ```env
   GEMINI_API_KEY=AIzaSy_DIEN_API_KEY_CUA_BAN_VAO_DAY
   ```
4. Bấm tổ hợp phím **`Ctrl + S`** (hoặc `Cmd + S` trên Mac) để lưu file lại.

> [!TIP]
> **Chế độ chạy Demo không cần key**: Nếu bạn chưa kịp lấy API Key, hệ thống vẫn chạy bình thường nhờ tính năng `ALLOW_EXTRACTIVE_FALLBACK=true`. Hệ thống sẽ tự động tìm kiếm trong CSDL Vector và trích xuất nguyên văn các Điều luật liên quan nhất hiển thị lên màn hình!

---

## BƯỚC 7: KHỞI CHẠY HỆ THỐNG

Tại cửa sổ Terminal (đã kích hoạt `(venv)`), bạn gõ một trong hai lệnh sau và nhấn **Enter**:

### Lệnh 1 (Khuyên dùng với uvicorn):
```powershell
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Hoặc Lệnh 2 (Chạy trực tiếp file main.py):
```powershell
python main.py
```

### Dấu hiệu khởi chạy thành công:
Màn hình Terminal sẽ xuất hiện các dòng thông báo tương tự như sau:

```text
INFO:     Started server process
INFO:     Waiting for application startup.
[Database] SQLite database initialized successfully: DB/legal_rag.db
[Seed] Seeded default admin and user accounts.
[Seed] Synchronized legal documents to ChromaDB.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

Khi thấy dòng `Application startup complete`, hệ thống đã sẵn sàng phục vụ!

---

## BƯỚC 8: MỞ TRÌNH DUYỆT WEB VÀ TRẢI NGHIỆM HỆ THỐNG

### 8.1. Truy cập vào ứng dụng
Mở trình duyệt web bất kỳ (Chrome, Edge, Firefox, Cốc Cốc...) và gõ vào thanh địa chỉ:

👉 **`http://localhost:8000`** *(hoặc `http://127.0.0.1:8000`)*

*(Ngoài ra bạn có thể vào `http://localhost:8000/docs` để xem tài liệu tương tác Swagger API OpenAPI).*

---

### 8.2. Danh sách tài khoản thử nghiệm có sẵn
Hệ thống đã tự động tạo sẵn 2 tài khoản mẫu trong CSDL để bạn trải nghiệm ngay mà không cần tạo mới:

| Vai trò | Tên đăng nhập hoặc Email | Mật khẩu | Quyền hạn và Tab hiển thị |
|---|---|---|---|
| **Quản trị viên (`ADMIN`)** | `admin@example.com`<br>*(hoặc gõ: `Quản trị viên`)* | `admin12345` | Có đầy đủ 4 tab: **Hỏi đáp**, **Lịch sử**, **Người dùng** (khóa/mở khóa tài khoản) và **Văn bản** (nạp văn bản luật mới vào RAG). |
| **Người dùng (`USER`)** | `user@example.com`<br>*(hoặc gõ: `Nguyễn Văn A`)* | `user12345` | Có 2 tab: **Hỏi đáp** (tra cứu pháp luật, xem trích dẫn) và **Lịch sử** (xem lại hội thoại), kèm nút **Đổi mật khẩu**. |

---

### 8.3. Hướng dẫn chi tiết dành cho Người dùng thông thường (USER)

#### A. Cách tạo tài khoản mới (Đăng ký)
Nếu bạn muốn tạo một tài khoản riêng cho mình:
1. Tại màn hình Đăng nhập ban đầu, nhìn xuống dòng chữ dưới cùng:  
   *Chưa có tài khoản?* -> Bấm chuột vào chữ **`Đăng ký`** màu xanh.
2. Biểu mẫu **"Tạo tài khoản"** sẽ hiển thị, bạn điền đầy đủ thông tin vào 3 ô:
   - **Họ và tên**: Nhập họ tên của bạn (ví dụ: `Trần Thị B`).
   - **Email**: Nhập địa chỉ email hợp lệ (ví dụ: `tranthib@example.com`).
   - **Mật khẩu**: Nhập mật khẩu có độ dài **tối thiểu 8 ký tự** (ví dụ: `user12345`).
3. Bấm nút màu xanh **`Đăng ký`**.
4. Hệ thống sẽ tự động tạo tài khoản, mã hóa mật khẩu an toàn bằng `bcrypt`, đăng nhập ngay lập tức và đưa bạn thẳng vào giao diện chính.

#### B. Cách đăng nhập hệ thống
1. Tại màn hình Đăng nhập:
   - Ô **Tên đăng nhập hoặc Email**: Gõ email của bạn (ví dụ `user@example.com`) hoặc gõ họ tên (ví dụ `Nguyễn Văn A`).
   - Ô **Mật khẩu**: Gõ mật khẩu tài khoản (ví dụ `user12345`).
2. Bấm nút **`Đăng nhập`**.
3. **Cơ chế bảo mật chống dò mật khẩu**: Nếu bạn nhập sai mật khẩu quá **5 lần liên tiếp**, hệ thống sẽ tự động khóa tài khoản và vô hiệu hóa toàn bộ ô nhập liệu để bảo vệ tài khoản. Khi đó cần nhờ Quản trị viên mở khóa lại.

#### C. Cách tra cứu và hỏi đáp pháp luật (Tab `💬 Hỏi đáp`)
Sau khi đăng nhập, hệ thống sẽ mở sẵn tab **Hỏi đáp**:
1. **Đặt câu hỏi**:
   - **Cách 1 (Dùng câu hỏi gợi ý)**: Ở cột bên phải có danh sách các câu hỏi mẫu (như *"Thời gian thử việc tối đa là bao lâu?"*, *"Quy định về quyền thừa kế theo pháp luật?"*...). Bạn chỉ cần bấm chuột vào câu hỏi bất kỳ, câu hỏi sẽ tự động được điền vào khung chat.
   - **Cách 2 (Tự gõ câu hỏi)**: Nhấp chuột vào khung soạn thảo ở góc dưới bên trái, gõ câu hỏi thắc mắc bằng tiếng Việt thông thường.
2. **Gửi câu hỏi**:
   - Bấm nút màu xanh **`Gửi câu hỏi ↗`** hoặc bấm tổ hợp phím tắt **`Ctrl + Enter`** (trên máy Mac là `Cmd + Enter`).
3. **Nhận câu trả lời**:
   - Trợ lý **LuậtAI** sẽ phản hồi câu trả lời trực tiếp, rõ ràng, nêu rõ căn cứ số Khoản, số Điều và tên văn bản luật tương ứng.

#### D. Cách xem chi tiết Điều luật gốc (Minh bạch nguồn trích dẫn)
1. Ngay bên dưới câu trả lời của LuậtAI, bạn sẽ nhìn thấy các thẻ trích dẫn nguồn màu xanh (ví dụ: `📄 Bộ luật Lao động 2019 · Điều 25`).
2. Bấm chuột trực tiếp vào thẻ nguồn đó.
3. Một cửa sổ (Modal) bật lên hiển thị chi tiết: Tiêu đề văn bản, tên Điều luật và toàn văn nội dung trích đoạn gốc của Điều luật đó trong CSDL.
4. Bấm nút **`Đóng`** (hoặc bấm ra ngoài vùng mờ) để tắt cửa sổ xem nguồn.

#### E. Xem lại lịch sử các câu hỏi đã đặt (Tab `🕘 Lịch sử`)
1. Bấm vào mục **`🕘 Lịch sử`** trên thanh menu bên trái.
2. Màn hình sẽ hiển thị bảng danh sách các câu hỏi bạn từng đặt gồm: *Thời gian hỏi*, *Nội dung câu hỏi*, *Trạng thái đã xử lý*.
3. Bấm nút **`Xem`** ở cột cuối cùng của câu hỏi bất kỳ: Hệ thống sẽ tự động nạp lại toàn bộ câu hỏi, câu trả lời của AI và các thẻ nguồn trích dẫn vào màn hình trò chuyện.

#### F. Đổi mật khẩu cá nhân
1. Ở thanh menu bên trái, nhìn xuống góc dưới (dưới tên của bạn), bấm vào nút **`Đổi mật khẩu`**.
2. Một hộp thoại xuất hiện yêu cầu bạn nhập:
   - **Mật khẩu hiện tại**: Nhập mật khẩu bạn đang dùng.
   - **Mật khẩu mới**: Nhập mật khẩu mới (tối thiểu 8 ký tự).
   - **Nhập lại mật khẩu mới**: Gõ lại chính xác mật khẩu mới.
3. Bấm **`Cập nhật mật khẩu`**. Hệ thống sẽ thông báo thành công.

#### G. Bắt đầu phiên hội thoại mới và Đăng xuất
- **Cuộc hội thoại mới**: Bấm nút **`Cuộc hội thoại mới`** ở góc trên cùng bên phải thanh tiêu đề để xóa trắng khung chat và bắt đầu một chủ đề hỏi đáp mới.
- **Đăng xuất**: Bấm nút **`Đăng xuất`** ở thanh menu bên trái để thoát khỏi tài khoản an toàn.

---

### 8.4. Hướng dẫn chi tiết dành cho Quản trị viên (ADMIN)

Để sử dụng các tính năng quản trị, bạn đăng nhập bằng tài khoản:  
- **Tên đăng nhập / Email**: `admin@example.com` *(hoặc `Quản trị viên`)*  
- **Mật khẩu**: `admin12345`

Sau khi đăng nhập Admin, ngoài 2 tab Hỏi đáp và Lịch sử, thanh menu bên trái sẽ xuất hiện thêm 2 tab quản trị đặc quyền: **`📚 Văn bản`** và **`👥 Người dùng`**.

#### A. Thao tác Quản lý và Tải lên văn bản pháp luật mới (Tab `📚 Văn bản`)
Đây là tính năng nạp thêm văn bản pháp luật vào kho RAG để AI có thêm tri thức trả lời:

1. **Truy cập**: Bấm vào mục **`📚 Văn bản`** trên menu bên trái.
2. **Điền thông tin vào biểu mẫu "Cập nhật văn bản"**:
   - **File văn bản**: Bấm nút *Choose File / Chọn tệp* để chọn file văn bản pháp luật từ máy tính (Hệ thống hỗ trợ đầy đủ các định dạng: **`.pdf`**, **`.docx`**, **`.txt`**, **`.md`**).
   - **Tiêu đề**: Nhập tiêu đề văn bản (ví dụ: *Luật Đất đai số 31/2024/QH15*). Nếu bạn để trống, hệ thống sẽ tự động lấy tên file làm tiêu đề.
   - **Loại văn bản**: Nhấp chuột chọn một trong các loại: *Luật*, *Bộ luật*, *Nghị định*, *Thông tư*, hoặc *Khác*.
   - **Cơ quan ban hành**: Nhập cơ quan ban hành (ví dụ: *Quốc hội*, *Chính phủ*, *Bộ Tài nguyên và Môi trường*).
   - **Ngày ban hành**: Bấm vào biểu tượng lịch để chọn ngày văn bản được ban hành.
3. **Thực thi nạp dữ liệu**:
   - Bấm nút màu xanh **`Tải lên & cập nhật RAG`**.
   - Nút bấm sẽ chuyển sang trạng thái **"Đang xử lý..."**.
   - **Quy trình tự động chạy ngầm**: Hệ thống sẽ đọc file -> Loại bỏ số trang PDF thừa -> Tách thông minh theo từng Điều và từng Khoản -> Tạo Local Embedding 384 chiều trực tiếp trên máy -> Lưu đồng thời vào SQLite và ChromaDB.
   - Khi hoàn tất, một thông báo màu xanh hiện lên: *"Đã cập nhật văn bản vào pipeline RAG."*
4. **Kiểm tra kết quả**:
   - Nhìn xuống bảng danh sách văn bản bên dưới, bạn sẽ thấy văn bản vừa nạp xuất hiện ngay lập tức kèm số lượng đoạn (**`Chunks`**) được tạo ra.
   - Bạn có thể bấm nút **`Làm mới`** ở góc trên bên phải để đồng bộ lại thống kê toàn bộ kho tài liệu.
5. **Thử nghiệm ngay**: Sau khi tải lên thành công, bạn quay lại tab **`💬 Hỏi đáp`** và gõ câu hỏi liên quan đến nội dung văn bản vừa nạp, AI sẽ lập tức sử dụng tài liệu mới để trả lời!

#### B. Thao tác Quản lý và Khóa / Mở khóa tài khoản người dùng (Tab `👥 Người dùng`)
Admin có toàn quyền kiểm soát người dùng trong hệ thống:

1. **Truy cập**: Bấm vào mục **`👥 Người dùng`** trên menu bên trái.
2. **Theo dõi danh sách tài khoản**:
   - Bảng người dùng hiển thị đầy đủ: *Họ tên*, *Email*, *Vai trò (`USER` / `ADMIN`)*, *Trạng thái (`Hoạt động` / `Đã khóa`)* và *Ngày tạo tài khoản*.
3. **Thao tác Khóa hoặc Mở khóa tài khoản**:
   - **Muốn khóa một tài khoản**: Tại dòng của người dùng đang có trạng thái `Hoạt động`, bấm nút **`Khóa`**. Trạng thái lập tức đổi sang chữ màu xám **`Đã khóa`**. Tài khoản này sẽ bị cấm truy cập ngay lập tức.
   - **Muốn mở khóa cho người dùng**: Khi người dùng bị khóa tự động do gõ sai mật khẩu quá 5 lần, hoặc tài khoản đang ở trạng thái `Đã khóa`, Admin chỉ cần bấm nút **`Mở khóa`** ở dòng tương ứng. Trạng thái sẽ chuyển về **`Hoạt động`**, số lần gõ sai được hoàn trả về 0 và người dùng có thể đăng nhập bình thường.
4. **Làm mới danh sách**: Bấm nút **`Làm mới`** để cập nhật danh sách người dùng mới nhất vừa đăng ký.

## BƯỚC 9: CÁCH DỪNG HOẶC KHỞI ĐỘNG LẠI HỆ THỐNG

### Cách dừng server:
Khi bạn không sử dụng nữa:
1. Quay lại cửa sổ **Terminal** của IDE / Command Prompt đang chạy lệnh uvicorn.
2. Nhấn tổ hợp phím **`Ctrl + C`**.
3. Server sẽ báo `Application shutdown complete` và dừng lại.
4. Gõ `deactivate` để thoát khỏi môi trường ảo nếu muốn.

### Cách khởi động lại vào lần sau:
Lần sau khi mở lại máy tính hoặc mở lại dự án, bạn **không cần cài đặt lại thư viện**, chỉ cần:
1. Mở thư mục dự án trong IDE / Terminal.
2. Kích hoạt môi trường ảo:
   ```powershell
   .\venv\Scripts\Activate.ps1
   ```
3. Chạy lại lệnh:
   ```powershell
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```
4. Mở trình duyệt vào ``.

---

## XỬ LÝ CÁC LỖI THƯỜNG GẶP (TROUBLESHOOTING)

### 10.1. Lỗi cổng 8000 bị chiếm dụng (`Port 8000 is already in use` hoặc `error while attempting to bind on address`)
- **Nguyên nhân**: Bạn đang có một cửa sổ terminal khác đang chạy server hoặc có phần mềm khác đang dùng port 8000.
- **Cách xử lý**:
  - Cách 1: Tìm cửa sổ terminal cũ đang chạy và bấm `Ctrl + C` để tắt.
  - Cách 2: Đổi sang một cổng khác khi chạy lệnh, ví dụ cổng `8080` hoặc `8888`:
    ```powershell
    uvicorn main:app --reload --host 0.0.0.0 --port 8080
    ```
    Sau đó mở trình duyệt tại: `http://localhost:8080`.

---

### 10.2. Lỗi "running scripts is disabled" trên PowerShell khi chạy `Activate.ps1`
- **Thông báo lỗi**: `File ...\Activate.ps1 cannot be loaded because running scripts is disabled on this system.`
- **Nguyên nhân**: Chính sách bảo mật của Windows PowerShell chặn file script chưa cấp quyền.
- **Cách xử lý**:
  1. Trong cửa sổ PowerShell đó, gõ lệnh sau rồi nhấn Enter:
     ```powershell
     Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
     ```
  2. Bấm phím `Y` và Enter nếu được hỏi xác nhận.
  3. Sau đó chạy lại lệnh kích hoạt:
     ```powershell
     .\venv\Scripts\Activate.ps1
     ```

---

### 10.3. Lỗi "python is not recognized as an internal or external command"
- **Nguyên nhân**: Máy tính chưa cài Python hoặc khi cài đặt quên chưa tích chọn ô *"Add python.exe to PATH"*.
- **Cách xử lý**:
  1. Tải lại bộ cài Python từ [python.org](https://www.python.org/downloads/).
  2. Mở file cài đặt, chọn **Modify** hoặc cài mới.
  3. **Tích vào ô "Add python.exe to PATH"** rồi bấm Next/Install.
  4. Tắt toàn bộ VS Code / Terminal đi và mở lại.

---

### 10.4. Muốn reset lại dữ liệu về trạng thái ban đầu
Nếu trong quá trình thử nghiệm bạn lỡ xóa văn bản hoặc chỉnh sửa lung tung trong CSDL:
1. Bấm `Ctrl + C` để dừng server.
2. Xóa 2 thư mục/file dữ liệu phát sinh sau:
   - Xóa file `DB/legal_rag.db`
   - Xóa thư mục `chroma_db/`
3. Chạy lại lệnh:
   ```powershell
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```
4. Hệ thống sẽ tự động tạo mới hoàn toàn CSDL sạch và nạp lại 3 văn bản luật mẫu ban đầu!
http://localhost:8000