"""
Xử lý tài liệu pháp luật (DocumentProcessor theo sơ đồ lớp UML):
1. Đọc nội dung văn bản từ các định dạng .txt, .md, .pdf, .docx.
2. Làm sạch văn bản PDF/DOCX:
   - Chuẩn hóa bảng mã tiếng Việt NFC (tránh lệch dấu tổ hợp NFD từ PDF).
   - Loại bỏ số trang đứng độc lập trên 1 dòng (ví dụ: '3', '16', 'Trang 5/42' khi trích xuất từ PDF).
   - Tự động tách các tiêu đề "Điều N." hoặc "PHỤ LỤC / DANH MỤC" nếu bị dính liền trên cùng một dòng.
   - Nối các dòng bị ngắt giữa câu do khổ giấy PDF nhưng giữ nguyên cấu trúc Chương, Mục,
     Điều, Khoản (1., 2., 16...), Điểm (a), b), đ), -) và Phụ lục / Danh mục.
3. Chia đoạn (chunking) chính xác theo cấu trúc "Điều N." và tách riêng "Phụ lục / Danh mục":
   - Chỉ tách khi gặp tiêu đề Điều thật sự ("Điều 40. Tên điều") hoặc tiêu đề Phụ lục / Danh mục,
     KHÔNG tách nhầm các câu tham chiếu nội bộ như "theo quy định tại Điều 8 của Luật này;".
   - Tuyệt đối KHÔNG gộp phần Phụ lục / Danh mục ở cuối văn bản vào Điều cuối cùng (như Điều 52).
   - Nếu một Điều quá dài (như Điều 3, Điều 15, Điều 25, Điều 52), ưu tiên ngắt theo ranh giới
     từng Khoản (1., 2., ...) và KHÔNG lặp lại khoản trùng lặp.
"""
from __future__ import annotations

import io
import re
import unicodedata
from pathlib import Path
from typing import Callable

from app.config import settings


def extract_text_from_bytes(filename: str, file_bytes: bytes) -> str:
    """Trích xuất văn bản thuần từ nội dung file (.txt, .md, .pdf, .docx)."""
    ext = Path(filename or "").suffix.lower()

    if ext in (".txt", ".md"):
        for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp1258", "latin-1"):
            try:
                return file_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue
        return file_bytes.decode("utf-8", errors="ignore")

    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("Thư viện pypdf chưa được cài đặt để đọc file PDF.") from exc

        reader = PdfReader(io.BytesIO(file_bytes))
        pages_text: list[str] = []
        for page in reader.pages:
            txt = page.extract_text() or ""
            if txt.strip():
                pages_text.append(txt)
        return "\n\n".join(pages_text)

    if ext == ".docx":
        try:
            from docx import Document as DocxDocument
        except ImportError as exc:
            raise RuntimeError(
                "Thư viện python-docx chưa được cài đặt để đọc file DOCX."
            ) from exc

        doc = DocxDocument(io.BytesIO(file_bytes))
        paragraphs: list[str] = []
        for p in doc.paragraphs:
            if p.text and p.text.strip():
                paragraphs.append(p.text.strip())
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text and c.text.strip()]
                if cells:
                    paragraphs.append(" | ".join(cells))
        return "\n\n".join(paragraphs)

    raise ValueError(
        f"Định dạng file '{ext}' không được hỗ trợ. Vui lòng tải lên .txt, .md, .pdf hoặc .docx."
    )


# Nhận diện dòng mở đầu một mục cấu trúc mới trong văn bản luật (không nối gộp với dòng trước)
_STRUCTURAL_LINE_RE = re.compile(
    r"^\s*(?:"
    r"(?:CHƯƠNG|Chương|MỤC|Mục|PHẦN|Phần|PHỤ\s+LỤC|Phụ\s+lục|DANH\s+MỤC|Danh\s+mục)\b"
    r"|(?:Điều|ĐIỀU)\s+\d+[a-zA-Z0-9]*\s*[\.\:\-]?"
    r"|\d{1,3}\.\s+\S"
    r"|[a-zđ]\)\s+\S"
    r"|[IVXLCDM]{1,6}\.\s+\S"
    r"|[-•+]\s+\S"
    r")"
)


def clean_legal_text(raw_text: str) -> str:
    """
    Làm sạch và chuẩn hóa văn bản pháp luật (đặc biệt tối ưu cho văn bản trích xuất từ PDF):
    1. Chuẩn hóa Unicode tiếng Việt về NFC và xóa ký tự điều khiển / khoảng trắng không ngắt (nbsp).
    2. Xóa các dòng chỉ chứa số trang đơn lẻ (ví dụ: '3', '16', '- 12 -', 'Trang 5') do ngắt trang PDF.
    3. Tự động xuống dòng nếu tiêu đề 'Điều N.' hoặc 'PHỤ LỤC' bị dính liền sau dấu chấm câu.
    4. Nối các dòng bị ngắt giữa chừng trong cùng một khoản/câu của PDF để câu văn liền mạch.
    """
    if not raw_text:
        return ""

    text = unicodedata.normalize("NFC", raw_text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"[ \t]+", " ", text)

    # Nếu PDF ghép liền "Điều N. <Chữ hoa>" hoặc "PHỤ LỤC" ngay sau dấu kết thúc câu (. ; : ! ?) -> tách dòng
    text = re.sub(
        r"([\.\;\:\!\?])\s+((?:Điều|ĐIỀU)\s+\d+[a-zA-Z0-9]*\s*[\.\:]\s*[A-ZÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬĐÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ])",
        r"\1\n\2",
        text,
    )
    text = re.sub(
        r"([\.\;\:\!\?])\s+((?:PHỤ\s+LỤC|Phụ\s+lục|DANH\s+MỤC)\s+[IVXLCDM\d]*)",
        r"\1\n\2",
        text,
    )

    raw_lines = text.split("\n")
    cleaned_lines: list[str] = []

    for line in raw_lines:
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue
        # Bỏ dòng chỉ chứa số trang PDF (ví dụ: '3', '16', '- 16 -', 'Trang 16/45')
        if re.match(r"^[-–—\s]*\d{1,4}[-–—\s]*$", stripped) or re.match(
            r"^(?:Trang|Page)\s+\d+(?:\s*/\s*\d+)?$", stripped, flags=re.I
        ):
            continue
        cleaned_lines.append(stripped)

    # Nối các dòng bị ngắt giữa câu do lề trang PDF
    merged_lines: list[str] = []
    for line in cleaned_lines:
        if not line:
            if merged_lines and merged_lines[-1] != "":
                merged_lines.append("")
            continue

        if not merged_lines or merged_lines[-1] == "":
            merged_lines.append(line)
            continue

        prev = merged_lines[-1]

        # Trường hợp đặc biệt trong PDF: dòng trước chỉ có "Điều 40." hoặc "PHỤ LỤC I" và dòng sau là tên viết hoa
        if re.match(r"^(?:Điều|ĐIỀU)\s+\d+[a-zA-Z0-9]*\s*[\.\:\-]?$", prev):
            merged_lines[-1] = f"{prev if prev.endswith(('.', ':')) else prev + '.'} {line}"
            continue
        if re.match(r"^(?:PHỤ\s+LỤC|Phụ\s+lục)\s*[IVXLCDM\d]*\s*[\.\:\-]?$", prev):
            merged_lines[-1] = f"{prev.rstrip('.:-')} - {line}"
            continue

        # Nếu dòng hiện tại là đầu Chương / Mục / Điều / Khoản (1., 2.) / Điểm (a), b)) / Phụ lục -> giữ dòng mới
        if _STRUCTURAL_LINE_RE.match(line):
            merged_lines.append(line)
            continue

        # Nếu dòng trước là tiêu đề Chương/Mục/Phụ lục hoặc tiêu đề Điều -> giữ dòng mới
        if re.match(
            r"^\s*(?:CHƯƠNG|Chương|MỤC|Mục|PHẦN|Phần|PHỤ\s+LỤC|Phụ\s+lục|DANH\s+MỤC|Danh\s+mục|Điều|ĐIỀU)\s+",
            prev,
        ) and not prev.endswith((",", ";")):
            merged_lines.append(line)
            continue

        # Nếu dòng trước chưa kết thúc câu (không kết thúc bằng ., ;, :, !, ?) -> nối với dòng hiện tại
        if not prev.endswith((".", ";", ":", "!", "?")):
            merged_lines[-1] = f"{prev} {line}"
        else:
            merged_lines.append(line)

    result = "\n".join(merged_lines)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _is_true_article_heading(line: str) -> bool:
    """
    Kiểm tra một dòng có phải là tiêu đề 'Điều N. <Tên điều>' thật sự hay không.
    - Chấp nhận mọi tiêu đề Điều hợp lệ (kể cả 'Điều 15. Ngành, nghề...', 'Điều 40. Nội dung...').
    - Loại trừ các cụm tham chiếu nội bộ trong câu bị rớt dòng như:
      'Điều 8 của Luật này;', 'Điều 20 và Điều 21...', 'Điều 15 tại khoản 2...'
    """
    s = unicodedata.normalize("NFC", (line or "").strip())
    m = re.match(
        r"^(?:Điều|ĐIỀU)\s+(\d+[a-zA-Z0-9]*)\s*([\.\:\-])?\s*(.*)$", s
    )
    if not m:
        return False

    punct = m.group(2) or ""
    rest = (m.group(3) or "").strip()

    if punct not in (".", ":", "-"):
        return False

    if not rest:
        return True

    if re.match(
        r"^(?:của\b|và\b|hoặc\b|tại\b|này\b|đó\b|trên\b|được\s+sửa\s+đổi)",
        rest,
        flags=re.I,
    ):
        return False

    first_alpha = next((ch for ch in rest if ch.isalpha()), "")
    if first_alpha and first_alpha.islower():
        return False

    return True


def _is_appendix_heading(line: str) -> bool:
    """
    Nhận diện tiêu đề Phụ lục hoặc Danh mục lớn ở cuối văn bản pháp luật
    (để tách riêng khỏi Điều cuối cùng như Điều 52).
    """
    s = unicodedata.normalize("NFC", (line or "").strip())
    if re.match(r"^(?:PHỤ\s+LỤC|Phụ\s+lục)\b", s):
        return True
    if re.match(r"^DANH\s+MỤC\b", s):
        return True
    return False


def _is_closing_signature_line(line: str) -> bool:
    """Nhận diện dòng kết thúc văn bản luật (thông qua tại kỳ họp... / Chủ tịch Quốc hội)."""
    s = unicodedata.normalize("NFC", (line or "").strip())
    if re.match(
        r"^(?:Luật|Bộ\s+luật|Nghị\s+quyết)\s+này\s+được\s+Quốc\s+hội\s+nước\s+Cộng\s+hòa",
        s,
        flags=re.I,
    ):
        return True
    return False


def _split_long_article_by_clauses(
    article_text: str,
    max_chars: int,
    overlap_chars: int,
    article_header: str,
) -> list[str]:
    """
    Chia một Điều luật dài (hoặc Phụ lục dài) theo từng Khoản (1., 2., ..., 16., 17.)
    để KHÔNG BAO GIỜ cắt đôi một khoản ở giữa câu.
    Mỗi đoạn con đều có tiêu đề Điều/Phụ lục ở dòng đầu tiên và KHÔNG lặp lại khoản của đoạn trước.
    """
    article_text = article_text.strip()
    if len(article_text) <= max_chars:
        return [article_text] if article_text else []

    lines = article_text.split("\n")
    header_line = lines[0].strip() if lines else article_header
    body_text = "\n".join(lines[1:]).strip() if len(lines) > 1 else article_text

    # Tách theo ranh giới các Khoản đánh số ở đầu dòng (1., 2., 3., ..., 16., 17.)
    clause_splits = re.split(r"(?m)^(?=\d{1,3}\.\s+)", body_text)
    clauses = [c.strip() for c in clause_splits if c and c.strip()]

    if len(clauses) > 1:
        chunks: list[str] = []
        current_clauses: list[str] = []
        prefix = f"{header_line}\n"
        current_len = len(prefix)

        for clause in clauses:
            # Nếu bản thân 1 khoản quá dài (ví dụ > max_chars * 1.5), tách tiếp theo dòng
            if len(clause) > max_chars * 1.5:
                if current_clauses:
                    chunks.append(prefix + "\n".join(current_clauses))
                    current_clauses = []
                    current_len = len(prefix)
                sub_lines = clause.split("\n")
                clause_intro = sub_lines[0].strip()
                sub_buf: list[str] = [clause_intro]
                sub_len = len(prefix) + len(clause_intro) + 1
                for sl in sub_lines[1:]:
                    if len(sub_buf) > 1 and sub_len + len(sl) + 1 > max_chars:
                        chunks.append(prefix + "\n".join(sub_buf))
                        sub_buf = [clause_intro, sl]
                        sub_len = len(prefix) + len(clause_intro) + len(sl) + 2
                    else:
                        sub_buf.append(sl)
                        sub_len += len(sl) + 1
                if sub_buf:
                    chunks.append(prefix + "\n".join(sub_buf))
                continue

            if current_clauses and (current_len + len(clause) + 1 > max_chars):
                chunks.append(prefix + "\n".join(current_clauses))
                current_clauses = [clause]
                current_len = len(prefix) + len(clause) + 1
            else:
                current_clauses.append(clause)
                current_len += len(clause) + 1

        if current_clauses:
            chunks.append(prefix + "\n".join(current_clauses))
        return chunks

    # Fallback: Nếu đoạn văn không chia theo Khoản 1., 2. thì ngắt tại dấu xuống dòng / dấu chấm câu
    chunks = []
    start = 0
    text_len = len(article_text)
    while start < text_len:
        end = min(text_len, start + max_chars)
        if end < text_len:
            window = article_text[start:end]
            last_break = max(
                window.rfind("\n"), window.rfind(". "), window.rfind("; ")
            )
            if last_break > max_chars // 2:
                end = start + last_break + 1

        piece = article_text[start:end].strip()
        if piece:
            if start > 0 and header_line and not piece.startswith(header_line[:10]):
                piece = f"{header_line}\n{piece}"
            chunks.append(piece)
        if end >= text_len:
            break
        start = end

    return chunks


def split_legal_text_by_article(
    text: str,
    max_chars: int | None = None,
    overlap_chars: int | None = None,
) -> list[str]:
    """
    Chia văn bản luật theo từng 'Điều N.' thật sự và tách riêng 'Phụ lục / Danh mục'.
    - Không tách nhầm các cụm tham chiếu 'Điều 8 của Luật này'.
    - Không gộp Phụ lục ở cuối văn bản vào Điều cuối cùng (như Điều 52).
    - Điều nào dài quá max_chars sẽ được tách theo ranh giới từng Khoản (1., 2., ...).
    """
    max_c = max_chars or settings.CHUNK_MAX_CHARS
    overlap_c = (
        overlap_chars if overlap_chars is not None else settings.CHUNK_OVERLAP_CHARS
    )

    cleaned = clean_legal_text(text)
    if not cleaned:
        return []

    lines = cleaned.split("\n")
    articles: list[list[str]] = []
    current_lines: list[str] = []

    for line in lines:
        if _is_true_article_heading(line) or _is_appendix_heading(line):
            if current_lines:
                articles.append(current_lines)
            current_lines = [line]
        elif _is_closing_signature_line(line):
            # Kết thúc phần nội dung Điều cuối cùng, không gộp chữ ký/thông qua vào Điều cuối
            if current_lines:
                articles.append(current_lines)
                current_lines = []
        else:
            # Bỏ qua các dòng tiêu đề Chương / Mục / Phần đứng lẻ loi
            if re.match(r"^\s*(?:CHƯƠNG|Chương|MỤC|Mục|PHẦN|Phần)\s+[IVXLCDM\d]+", line):
                continue
            if current_lines or not articles:
                current_lines.append(line)

    if current_lines:
        articles.append(current_lines)

    # Nếu phần đầu tiên chỉ là phần mở đầu / quốc hiệu trước Điều 1 -> bỏ qua nếu đã có các Điều
    if (
        len(articles) > 1
        and not _is_true_article_heading(articles[0][0])
        and not _is_appendix_heading(articles[0][0])
    ):
        preamble_text = "\n".join(articles[0]).strip()
        if len(preamble_text) < 1200:
            articles = articles[1:]

    final_chunks: list[str] = []
    for art_lines in articles:
        art_text = "\n".join(art_lines).strip()
        if not art_text:
            continue
        first_line = art_lines[0].strip()
        sub_chunks = _split_long_article_by_clauses(
            article_text=art_text,
            max_chars=max_c,
            overlap_chars=overlap_c,
            article_header=first_line,
        )
        final_chunks.extend(sub_chunks)

    return final_chunks


def estimate_token_count(text: str) -> int:
    """Ước lượng số lượng token của đoạn văn bản tiếng Việt."""
    if not text:
        return 0
    words = text.split()
    return max(1, int(len(words) * 1.35))


class DocumentProcessor:
    """
    Lớp DocumentProcessor theo đúng Sơ đồ lớp UML (Class Diagram):
    - chunkSize: Integer
    - overlap: Integer
    + readDocument(filename, file_bytes)
    + splitIntoChunks(text)
    + generateEmbedding(chunks, embed_fn)
    """

    def __init__(
        self,
        chunk_size: int | None = None,
        overlap: int | None = None,
    ) -> None:
        self.chunkSize: int = chunk_size or settings.CHUNK_MAX_CHARS
        self.overlap: int = (
            overlap if overlap is not None else settings.CHUNK_OVERLAP_CHARS
        )

    def readDocument(self, filename: str, file_bytes: bytes) -> str:
        raw_text = extract_text_from_bytes(filename, file_bytes)
        return clean_legal_text(raw_text)

    def splitIntoChunks(self, text: str) -> list[str]:
        return split_legal_text_by_article(
            text, max_chars=self.chunkSize, overlap_chars=self.overlap
        )

    def generateEmbedding(
        self, chunks: list[str], embed_fn: Callable[[list[str]], list[list[float]]]
    ) -> list[list[float]]:
        return embed_fn(chunks)


document_processor = DocumentProcessor()