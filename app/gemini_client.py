"""
Khách hàng AI & Embedding (AIService & Embedding theo sơ đồ lớp UML):
- Nạp mô hình SentenceTransformer theo cơ chế Lazy-Loading (chỉ nạp khi thực sự gọi embedding)
  để tránh lỗi treo tiến trình con (SpawnProcess) của Uvicorn WatchFiles trên Windows + Python 3.14.
- Tích hợp bộ phân tích câu hỏi pháp luật (`parse_legal_query`), bộ lọc đúng Khoản/Điểm trọng tâm
  (`_extract_focus_content_from_chunk_with_meta`) và định dạng trích dẫn rõ "Khoản mấy, Điều mấy, Luật nào".
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import unicodedata
from typing import Any

# Tắt cảnh báo HF_TOKEN và đa luồng tokenizer gây treo tiến trình SpawnProcess trên Windows
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import httpx

from app.config import ENV_FILE, settings

SYSTEM_INSTRUCTION_LEGAL_RAG = (
    "Bạn là LuậtAI — trợ lý tư vấn pháp luật Việt Nam chuyên nghiệp.\n"
    "Nguyên tắc bắt buộc khi trả lời:\n"
    "1. Mở đầu câu trả lời bằng cụm căn cứ pháp lý rõ ràng theo mẫu: "
    "'Theo quy định tại [Khoản ...,] Điều ... của [Tên Luật / Văn bản]:'.\n"
    "2. CHỈ trả lời đúng nội dung, đúng Khoản hoặc Điểm mà người dùng đang hỏi dựa trên [NGỮ CẢNH PHÁP LUẬT]. "
    "Đảm bảo trình bày đầy đủ các điểm (a, b, c...) nằm trong đúng Khoản được hỏi.\n"
    "3. TUYỆT ĐỐI KHÔNG chép kèm các Khoản khác, Mục khác hoặc Điều khác không liên quan đến câu hỏi "
    "(ví dụ: khi người dùng hỏi 'Ngành, nghề ưu đãi đầu tư là gì' tại Khoản 1 Điều 15 thì chỉ trả lời Khoản 1 Điều 15, "
    "không liệt kê thêm Khoản 2 về Địa bàn ưu đãi đầu tư hay Khoản 3).\n"
    "4. Chỉ khi người dùng hỏi tổng quát toàn bộ một Điều luật (ví dụ: 'Điều 40 quy định gì?') "
    "thì mới trình bày toàn bộ các khoản của Điều luật đó.\n"
    "5. Trình bày bằng văn bản thuần (plain text) rõ ràng, sạch đẹp, KHÔNG dùng ký hiệu đánh dấu sao (**).\n"
    "6. Nếu ngữ cảnh không chứa quy định trả lời cho câu hỏi, hãy thông báo ngắn gọn là hiện tại kho văn bản "
    "chưa có quy định về nội dung này, tuyệt đối không trích dẫn một Điều luật không liên quan."
)

_VN_STOPWORDS = {
    "là", "và", "của", "có", "được", "trong", "cho", "các", "với", "những",
    "một", "này", "đó", "khi", "thì", "mà", "như", "về", "tại", "theo",
    "để", "đến", "từ", "hay", "hoặc", "nếu", "nhưng", "vì", "do", "bởi",
    "bao", "nhiêu", "nào", "thế", "sao", "quy", "định", "gì", "ai", "đâu",
    "cho", "tôi", "hỏi", "biết", "hãy", "nêu", "trình", "bày", "cụ", "thể",
    "chi", "tiết", "nội", "dung", "thuộc", "gồm", "bao", "những", "trường",
    "hợp", "căn", "cứ", "mục", "điều", "khoản", "điểm",
}

_LEGAL_SYNONYM_EXPANSIONS = [
    (("thử việc tối đa", "bao lâu"), "điều 25 thời gian thử việc không quá 180 ngày 60 ngày 30 ngày 06 ngày"),
    (("nghỉ phép năm", "phép năm"), "điều 113 nghỉ hằng năm hưởng nguyên lương 12 ngày"),
    (("đơn phương chấm dứt", "chấm dứt hợp đồng"), "điều 35 điều 36 quyền đơn phương chấm dứt hợp đồng lao động báo trước"),
    (("quyền thừa kế theo pháp luật", "hàng thừa kế"), "điều 650 điều 651 người thừa kế theo pháp luật hàng thừa kế"),
    (("khi nào người điều khiển xe bị xử phạt", "vượt đèn đỏ", "nồng độ cồn"), "điều 6 điều 7 xử phạt người điều khiển xe vi phạm quy tắc giao thông đường bộ phạt tiền"),
    (("độ tuổi kết hôn", "điều kiện kết hôn"), "điều 8 điều kiện kết hôn nam từ đủ 20 tuổi nữ từ đủ 18 tuổi"),
]


def _normalize_vn_text(text: str) -> str:
    text = unicodedata.normalize("NFC", (text or "").lower())
    text = re.sub(
        r"[^\w\sđáàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵ]",
        " ",
        text,
    )
    return re.sub(r"\s+", " ", text).strip()


def _remove_accents(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    nfd = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


def parse_legal_query(question: str) -> dict[str, Any]:
    """
    Phân tích cấu trúc câu hỏi pháp luật của người dùng:
    - target_articles: Danh sách số hiệu Điều được hỏi trực tiếp (vd: ['15'], ['40'], ['48']).
    - target_clauses: Danh sách số hiệu Khoản được hỏi trực tiếp (vd: ['1'], ['2']).
    - target_points: Danh sách Điểm được hỏi trực tiếp (vd: ['a'], ['b']).
    - doc_hint: Tên loại/văn bản luật được nhắc tới trong câu hỏi (vd: 'luật đầu tư').
    - topic_core: Cụm từ khóa nội dung thực chất sau khi loại bỏ từ để hỏi & phần dẫn chiếu.
    - topic_tokens: Danh sách từ khóa đơn phục vụ đối sánh.
    - topic_bigrams: Danh sách các cụm từ ghép 2 âm tiết liên tiếp (vd: 'ngành nghề', 'ưu đãi', 'thông nước').
    """
    raw_lower = unicodedata.normalize("NFC", (question or "").lower()).strip()
    q_norm = _normalize_vn_text(raw_lower)

    target_articles: list[str] = []
    for m in re.finditer(r"\bđiều\s+(\d+[a-z0-9]*)\b", q_norm):
        art_num = m.group(1).strip()
        if art_num not in target_articles:
            target_articles.append(art_num)

    target_clauses: list[str] = []
    for m in re.finditer(r"\bkhoản\s+(\d{1,3})\b", q_norm):
        cl_num = m.group(1).strip()
        if cl_num not in target_clauses:
            target_clauses.append(cl_num)

    target_points: list[str] = []
    for m in re.finditer(r"\bđiểm\s+([a-zđ])\b", q_norm):
        pt_char = m.group(1).strip()
        if pt_char not in target_points:
            target_points.append(pt_char)

    doc_hint = ""
    doc_match = re.search(
        r"\b((?:bộ\s+luật|luật|nghị\s+định|thông\s+tư|pháp\s+lệnh|hiến\s+pháp)\s+"
        r"[a-z0-9đáàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵ\s\-/]{1,35}?)"
        r"(?=\s*(?:,|\.|;|\?|\bđiều\b|\bkhoản\b|\bquy\s+định\b|\blà\s+gì\b|\bnhư\s+thế\s+nào\b|\bcó\s+những\b|\bgồm\b|\bthì\b|$))",
        raw_lower,
    )
    if doc_match:
        candidate_hint = _normalize_vn_text(doc_match.group(1))
        candidate_hint = re.sub(
            r"\b(điều|khoản|điểm|là|gì|quy|định|như|thế|nào)\b.*$", "", candidate_hint
        ).strip()
        if len(candidate_hint.split()) >= 2:
            doc_hint = candidate_hint

    work = raw_lower
    work = re.sub(
        r"^\s*(?:trong|theo|tại|căn\s+cứ|ở)\s+(?:quy\s+định\s+(?:của|tại)\s+)?(?:bộ\s+luật|luật|nghị\s+định|thông\s+tư)[^,\.;\?\n]*[,\.;]\s*",
        " ",
        work,
    )
    work_norm = _normalize_vn_text(work)
    if doc_hint:
        work_norm = re.sub(
            rf"\b(?:trong|theo|tại|của|ở)?\s*{re.escape(doc_hint)}\b",
            " ",
            work_norm,
        )

    work_norm = re.sub(r"\bđiều\s+\d+[a-z0-9]*\b", " ", work_norm)
    work_norm = re.sub(r"\bkhoản\s+\d{1,3}\b", " ", work_norm)
    work_norm = re.sub(r"\bđiểm\s+[a-zđ]\b", " ", work_norm)

    work_norm = re.sub(
        r"\b(cho tôi hỏi|cho biết|hãy nêu|trình bày|nội dung của|nội dung|chi tiết|cụ thể|"
        r"là gì|như thế nào|như nào|ra sao|được quy định|quy định về|quy định gì|quy định|"
        r"những gì|bao lâu|khi nào|ở đâu|tối đa|bao nhiêu|gồm những gì|bao gồm những gì|bao gồm)\b",
        " ",
        work_norm,
    )
    topic_core = re.sub(r"\s+", " ", work_norm).strip()
    # Bỏ các hư từ đứng ở đầu hoặc cuối topic_core (vd: "của", "trong", "về", "là")
    topic_core = re.sub(r"^(?:của|trong|về|tại|theo|là|có|được)\s+", "", topic_core).strip()
    topic_core = re.sub(r"\s+(?:của|trong|về|tại|theo|là|gì|nào|đó|này)$", "", topic_core).strip()

    topic_tokens = [
        t for t in topic_core.split() if t not in _VN_STOPWORDS and len(t) > 1
    ]
    if not topic_tokens:
        topic_core = ""

    # Tạo danh sách cụm từ ghép 2 âm tiết (bigrams) từ các từ liền kề trong topic_core (bỏ hư từ nối 'của', 'và', 'trong')
    core_words = [
        w for w in topic_core.split() if w not in {"của", "và", "trong", "với", "tại", "theo", "về", "là"} and len(w) > 1
    ]
    topic_bigrams: list[str] = []
    for i in range(len(core_words) - 1):
        bg = f"{core_words[i]} {core_words[i + 1]}"
        if bg not in topic_bigrams:
            topic_bigrams.append(bg)

    return {
        "target_articles": target_articles,
        "target_clauses": target_clauses,
        "target_points": target_points,
        "doc_hint": doc_hint,
        "topic_core": topic_core,
        "topic_tokens": topic_tokens,
        "topic_bigrams": topic_bigrams,
    }


def format_law_title_for_citation(doc_title: str, doc_content: str = "") -> str:
    """
    Chuẩn hóa tên văn bản luật để hiển thị rõ ràng trong câu trả lời:
    - Nếu doc_title chỉ là tên file như 'Luật-143-2025-QH15.pdf', tự động dò tên Luật chính thức
      trong phần mở đầu của văn bản (vd: 'LUẬT ĐẦU TƯ') để hiển thị:
      'Luật Đầu tư (Luật số 143/2025/QH15 — Luật-143-2025-QH15.pdf)'.
    """
    raw_title = (doc_title or "Văn bản pháp luật").strip()
    detected_law_name = ""

    if doc_content:
        head_text = unicodedata.normalize("NFC", doc_content[:2000])
        for line in head_text.split("\n"):
            s = line.strip()
            m_law = re.match(
                r"^((?:BỘ\s+LUẬT|LUẬT|NGHỊ\s+ĐỊNH|THÔNG\s+TƯ|PHÁP\s+LỆNH)\s+[A-ZÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬĐÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ\s,\-]{3,60})$",
                s,
            )
            if m_law and "CỘNG HÒA" not in s and "ĐỘC LẬP" not in s:
                words = m_law.group(1).strip().split()
                if len(words) >= 2:
                    # Viết hoa chữ cái đầu: "LUẬT ĐẦU TƯ" -> "Luật Đầu tư"
                    titled = " ".join(w.capitalize() if i > 0 else w.capitalize() for i, w in enumerate(words))
                    titled = re.sub(r"^Luật\s+đầu\s+tư$", "Luật Đầu tư", titled, flags=re.I)
                    titled = re.sub(r"^Bộ\s+luật\s+lao\s+động$", "Bộ luật Lao động", titled, flags=re.I)
                    titled = re.sub(r"^Bộ\s+luật\s+dân\s+sự$", "Bộ luật Dân sự", titled, flags=re.I)
                    detected_law_name = titled
                    break

    # Kiểm tra nếu raw_title là tên file (.pdf, .docx, .txt, .md) hoặc dạng Luật-143-2025-QH15
    is_filename_style = bool(
        re.search(r"\.(?:pdf|docx|txt|md)$", raw_title, flags=re.I)
        or re.search(r"\d+-\d{4}-QH\d+", raw_title, flags=re.I)
    )
    if is_filename_style:
        m_num = re.search(r"(\d+)[/\-](\d{4})[/\-](QH\d+|NĐ-CP|ND-CP|TT-[A-Z]+)", raw_title, flags=re.I)
        law_num_str = f"số {m_num.group(1)}/{m_num.group(2)}/{m_num.group(3).upper()}" if m_num else ""
        if detected_law_name and detected_law_name.lower() not in raw_title.lower():
            if law_num_str:
                return f"{detected_law_name} {law_num_str} ({raw_title})"
            return f"{detected_law_name} ({raw_title})"
        if law_num_str and "/" not in raw_title:
            prefix = "Nghị định" if "NĐ" in law_num_str or "ND" in law_num_str else "Luật"
            return f"{prefix} {law_num_str} ({raw_title})"

    return raw_title


def _extract_focus_content_from_chunk_with_meta(
    question: str, chunk_content: str
) -> tuple[str, list[str], list[str]]:
    """
    Trích xuất ĐÚNG Khoản / Điểm / Đoạn nội dung trọng tâm trả lời trực tiếp cho câu hỏi
    (không kéo theo các khoản hoặc mục khác không liên quan trong cùng Điều luật):
    - Trả về bộ 3: `(focused_text, matched_clause_numbers, matched_point_letters)`.
      Ví dụ: khi hỏi "Ngành, nghề ưu đãi đầu tư là gì" trên Điều 15, hàm chỉ trích xuất
      Khoản 1 Điều 15 (gồm các điểm a..i), loại bỏ Khoản 2 (Địa bàn ưu đãi) và Khoản 3,
      đồng thời trả về `matched_clause_numbers = ['1']`.
    """
    text = (chunk_content or "").strip()
    if not text:
        return "", [], []

    # 1. Tách bỏ phần thông qua cuối luật ("Luật này được Quốc hội... thông qua...") nếu bị dính
    text = re.split(
        r"(?m)^\s*(?:Luật|Bộ\s+luật|Nghị\s+quyết)\s+này\s+được\s+Quốc\s+hội\s+nước\s+Cộng\s+hòa",
        text,
        maxsplit=1,
    )[0].strip()

    parsed = parse_legal_query(question)
    target_articles: list[str] = parsed["target_articles"]
    target_clauses: list[str] = parsed["target_clauses"]
    target_points: list[str] = parsed["target_points"]
    q_core: str = parsed["topic_core"]
    q_tokens: list[str] = parsed["topic_tokens"]
    q_bigrams: list[str] = parsed["topic_bigrams"]

    # 2. Nếu đoạn văn bản bị dính cả Điều cuối (vd Điều 52) và PHỤ LỤC / DANH MỤC ở sau: tách riêng!
    appendix_parts = re.split(
        r"(?m)^(?=(?:PHỤ\s+LỤC|Phụ\s+lục|DANH\s+MỤC)\b)", text
    )
    if len(appendix_parts) > 1:
        if target_articles and not q_tokens:
            text = appendix_parts[0].strip()
        elif q_tokens:
            best_part = appendix_parts[0].strip()
            best_part_score = -1.0
            for part in appendix_parts:
                p_norm = _normalize_vn_text(part)
                p_score = sum(4.0 for bg in q_bigrams if f" {bg} " in f" {p_norm} ")
                p_score += sum(1.5 for t in q_tokens if f" {t} " in f" {p_norm} ")
                if q_core and q_core in p_norm:
                    p_score += 15.0
                if p_score > best_part_score:
                    best_part_score = p_score
                    best_part = part.strip()
            text = best_part

    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if not lines:
        return "", [], []

    first_line_is_header = bool(
        re.match(
            r"^(?:Điều|ĐIỀU|PHỤ\s+LỤC|Phụ\s+lục|DANH\s+MỤC|Danh\s+mục|MỤC|Mục|CHƯƠNG|Chương)\b",
            lines[0],
        )
    )
    header_line = lines[0] if first_line_is_header else ""
    body_lines = lines[1:] if first_line_is_header else lines
    body_text = "\n".join(body_lines).strip()

    if not body_text:
        return text, [], []

    # 3. Chia body_text thành các Khoản đánh số ở đầu dòng (1., 2., 3., ...)
    clause_blocks = [
        c.strip()
        for c in re.split(r"(?m)^(?=\d{1,3}\.\s+)", body_text)
        if c and c.strip()
    ]

    # Trường hợp A: Người dùng hỏi đích danh số Khoản (ví dụ: "Khoản 1 Điều 15", "Khoản 2 Điều 40")
    if target_clauses and len(clause_blocks) > 1:
        matched_clauses: list[str] = []
        matched_nums: list[str] = []
        for clause in clause_blocks:
            m_cl = re.match(r"^(\d{1,3})\.\s+", clause)
            if m_cl and m_cl.group(1) in target_clauses:
                matched_clauses.append(clause)
                matched_nums.append(m_cl.group(1))
        if matched_clauses:
            # Nếu người dùng hỏi thêm Điểm cụ thể trong Khoản đó (vd: "Điểm a Khoản 1 Điều 15")
            if target_points and len(matched_clauses) == 1:
                cl_txt, pt_list = _filter_points_in_clause(
                    matched_clauses[0], target_points, q_core, q_tokens, q_bigrams
                )
                out = f"{header_line}\n{cl_txt}".strip() if header_line else cl_txt
                return out, matched_nums, pt_list
            out = (
                f"{header_line}\n" + "\n".join(matched_clauses)
                if header_line
                else "\n".join(matched_clauses)
            )
            return out.strip(), matched_nums, []

    # Trường hợp B: Người dùng hỏi toàn bộ một Điều luật theo số Điều (vd: "Điều 40 là gì", "Điều 15 quy định gì")
    if target_articles and not q_tokens:
        return text, [], []

    if not q_tokens:
        return text, [], []

    # Trường hợp C: Điều luật có nhiều Khoản (1., 2., 3....) -> Chấm điểm từng Khoản để CHỈ lấy đúng Khoản được hỏi
    if len(clause_blocks) > 1:
        scored_clauses: list[tuple[float, str, str]] = []
        core_words = [
            w for w in q_core.split() if w not in {"của", "và", "trong", "với", "tại", "theo", "về", "là"} and len(w) > 1
        ]

        for clause in clause_blocks:
            m_cl = re.match(r"^(\d{1,3})\.\s+", clause)
            cl_num = m_cl.group(1) if m_cl else ""
            cl_lines = [ln.strip() for ln in clause.split("\n") if ln.strip()]
            cl_intro = cl_lines[0] if cl_lines else clause
            cl_intro_norm = _normalize_vn_text(cl_intro)
            cl_full_norm = _normalize_vn_text(clause)

            # Kiểm tra xem khoản này có phải chỉ là khoản dẫn chiếu / giao thẩm quyền ("Căn cứ... quy định tại khoản 1 và khoản 2...")
            is_ref_clause = bool(
                re.search(
                    r"\b(?:quy định tại khoản|theo quy định tại khoản|quy định tại các khoản|chính phủ quy định chi tiết)\b",
                    cl_intro_norm,
                )
            )

            score = 0.0

            # 1) Khớp trực tiếp chủ ngữ định nghĩa ở đầu Khoản (vd: "1. Ngành, nghề ưu đãi đầu tư là...")
            if q_core and re.match(
                rf"^\d{{1,3}}\s+{re.escape(q_core)}\s+(?:là|bao gồm|gồm|được|có|áp dụng|thực hiện|không)\b",
                cl_intro_norm,
            ):
                score += 48.0
            elif q_core and re.match(rf"^\d{{1,3}}\s+{re.escape(q_core)}\b", cl_intro_norm):
                score += 40.0
            elif q_core and len(core_words) >= 2 and q_core in cl_intro_norm:
                score += 10.0 if is_ref_clause else 28.0
            elif q_core and len(core_words) >= 2 and q_core in cl_full_norm:
                score += 15.0

            # 2) Kiểm tra chủ ngữ của Khoản để phạt các Khoản nói về chủ đề khác trong cùng Điều
            # (Ví dụ: Điều 15 có Khoản 1 là "Ngành, nghề ưu đãi đầu tư là..." và Khoản 2 là "Địa bàn ưu đãi đầu tư bao gồm:")
            m_subj = re.match(
                r"^\d{1,3}\s+(.{3,65}?)\s+(?:là|bao gồm|gồm)\b", cl_intro_norm
            )
            if m_subj and core_words:
                subj_norm = m_subj.group(1).strip()
                if not subj_norm.startswith(("căn cứ", "trường hợp", "việc ", "nhà đầu tư", "người ")):
                    subj_hits = sum(
                        1 for w in core_words if f" {w} " in f" {subj_norm} "
                    )
                    subj_ratio = subj_hits / len(core_words)
                    if subj_ratio >= 0.85:
                        score += 22.0
                    elif subj_ratio < 0.70:
                        score -= 20.0

            # 3) Điểm thưởng cụm từ ghép 2 âm tiết (bigrams)
            for bg in q_bigrams:
                if f" {bg} " in f" {cl_intro_norm} ":
                    score += 5.5
                elif f" {bg} " in f" {cl_full_norm} ":
                    score += 3.2

            # 4) Điểm khớp từng từ khóa
            intro_hits = sum(
                1 for t in q_tokens if f" {t} " in f" {cl_intro_norm} "
            )
            full_hits = sum(
                1 for t in q_tokens if f" {t} " in f" {cl_full_norm} "
            )
            score += intro_hits * 2.5 + full_hits * 1.2

            # 5) Giảm điểm của khoản dẫn chiếu phụ nếu người dùng không hỏi về thẩm quyền ban hành/sửa đổi
            if is_ref_clause and not any(
                k in q_tokens for k in ("chính", "phủ", "sửa", "đổi", "bổ", "sung", "thẩm", "quyền")
            ):
                score *= 0.30

            scored_clauses.append((score, cl_num, clause))

        max_score = max((s for s, _, _ in scored_clauses), default=0.0)
        if max_score >= 4.0:
            threshold = max(4.5, max_score * 0.65)
            selected_items = [
                (num, cl) for s, num, cl in scored_clauses if s >= threshold
            ]

            if selected_items:
                # Nếu chỉ chọn 1 Khoản, kiểm tra xem người dùng hỏi cả Khoản đó hay chỉ hỏi 1 Điểm/dòng nhỏ bên trong
                if len(selected_items) == 1:
                    sel_num, sel_clause = selected_items[0]
                    narrowed_clause, pt_list = _filter_points_in_clause(
                        sel_clause, target_points, q_core, q_tokens, q_bigrams
                    )
                    out_txt = (
                        f"{header_line}\n{narrowed_clause}".strip()
                        if header_line and narrowed_clause.startswith(f"{sel_num}.")
                        else narrowed_clause
                    )
                    return out_txt, ([sel_num] if sel_num else []), pt_list

                # Nếu chọn nhiều Khoản liên quan (nhưng ít hơn tổng số Khoản của Điều)
                if len(selected_items) < len(clause_blocks):
                    sel_nums = [num for num, _ in selected_items if num]
                    sel_texts = [cl for _, cl in selected_items]
                    out_txt = (
                        f"{header_line}\n" + "\n".join(sel_texts)
                        if header_line
                        else "\n".join(sel_texts)
                    )
                    return out_txt.strip(), sel_nums, []

    # Trường hợp D: Đoạn văn bản không chia theo Khoản 1., 2. (ví dụ: Phụ lục, Danh mục, Bảng hoặc Điều chỉ có 1 khối)
    narrowed_body, pt_list = _filter_points_in_clause(
        body_text, target_points, q_core, q_tokens, q_bigrams
    )
    if narrowed_body != body_text:
        out_txt = f"{header_line}\n{narrowed_body}".strip() if header_line else narrowed_body
        return out_txt, [], pt_list

    return text, [], []


def _filter_points_in_clause(
    clause_text: str,
    target_points: list[str],
    q_core: str,
    q_tokens: list[str],
    q_bigrams: list[str],
) -> tuple[str, list[str]]:
    """
    Kiểm tra bên trong một Khoản (hoặc một khối văn bản):
    - Nếu người dùng hỏi đích danh Điểm (vd: 'điểm a') -> chỉ lấy điểm đó.
    - Nếu dòng mở đầu Khoản (intro line) đã bao phủ >= 65% từ khóa câu hỏi (ví dụ: hỏi 'Ngành, nghề ưu đãi đầu tư là gì'
      và dòng đầu Khoản 1 là '1. Ngành, nghề ưu đãi đầu tư là các ngành, nghề... sau đây:') -> GIỮ NGUYÊN toàn bộ
      các điểm a), b), c)... của Khoản đó để câu trả lời đầy đủ 100%.
    - Ngược lại, nếu dòng mở đầu Khoản KHÔNG chứa từ khóa đặc thù mà từ khóa nằm ở một Điểm hoặc một dòng cụ thể
      bên dưới (ví dụ hỏi 1 mục nhỏ trong danh sách/bảng) -> chỉ trích xuất đúng Điểm / dòng khớp từ khóa đó.
    """
    cl_lines = [ln.strip() for ln in clause_text.split("\n") if ln.strip()]
    if len(cl_lines) <= 1:
        return clause_text, []

    intro_line = cl_lines[0]
    intro_norm = _normalize_vn_text(intro_line)
    rest_text = "\n".join(cl_lines[1:]).strip()

    point_blocks = [
        p.strip()
        for p in re.split(r"(?m)^(?=[a-zđ]\)\s+)", rest_text)
        if p and p.strip()
    ]

    if target_points and len(point_blocks) > 1:
        matched_pts: list[str] = []
        matched_letters: list[str] = []
        for pt in point_blocks:
            m_pt = re.match(r"^([a-zđ])\)\s+", pt)
            if m_pt and m_pt.group(1) in target_points:
                matched_pts.append(pt)
                matched_letters.append(m_pt.group(1))
        if matched_pts:
            return f"{intro_line}\n" + "\n".join(matched_pts), matched_letters

    if not q_tokens:
        return clause_text, []

    intro_tok_hits = sum(1 for t in q_tokens if f" {t} " in f" {intro_norm} ")
    intro_coverage = intro_tok_hits / len(q_tokens)

    if intro_coverage >= 0.65 or (q_core and len(q_tokens) >= 2 and q_core in intro_norm):
        return clause_text, []

    specific_tokens = [
        t for t in q_tokens if f" {t} " not in f" {intro_norm} "
    ]
    if not specific_tokens:
        return clause_text, []

    if len(point_blocks) > 1 and re.match(r"^[a-zđ]\)\s+", point_blocks[0]):
        scored_pts: list[tuple[float, str, str]] = []
        for pt in point_blocks:
            m_pt = re.match(r"^([a-zđ])\)\s+", pt)
            pt_letter = m_pt.group(1) if m_pt else ""
            pt_norm = _normalize_vn_text(pt)
            s = 0.0
            if q_core and q_core in pt_norm:
                s += 20.0
            for bg in q_bigrams:
                if f" {bg} " in f" {pt_norm} ":
                    s += 6.0
            spec_hits = sum(1 for t in specific_tokens if f" {t} " in f" {pt_norm} ")
            s += spec_hits * 4.0
            scored_pts.append((s, pt_letter, pt))

        max_pt_s = max((s for s, _, _ in scored_pts), default=0.0)
        if max_pt_s >= 6.0:
            sel_pts = [
                (ltr, pt)
                for s, ltr, pt in scored_pts
                if s >= max(4.0, max_pt_s * 0.65)
            ]
            if sel_pts and len(sel_pts) < len(point_blocks):
                return (
                    f"{intro_line}\n" + "\n".join(pt for _, pt in sel_pts),
                    [ltr for ltr, _ in sel_pts if ltr],
                )
        return clause_text, []

    # Nếu là danh sách dòng / mục trong Phụ lục hoặc khối văn bản có nhiều dòng con
    if len(cl_lines) >= 3:
        scored_lines: list[tuple[float, int, str]] = []
        for idx, ln in enumerate(cl_lines):
            ln_norm = _normalize_vn_text(ln)
            s = 0.0
            if q_core and q_core in ln_norm:
                s += 25.0
            for bg in q_bigrams:
                if f" {bg} " in f" {ln_norm} ":
                    s += 8.0
            spec_hits = sum(1 for t in specific_tokens if f" {t} " in f" {ln_norm} ")
            if spec_hits >= 2 or (len(specific_tokens) == 1 and spec_hits == 1):
                s += spec_hits * 3.5
            scored_lines.append((s, idx, ln))

        max_ln_s = max((s for s, _, _ in scored_lines), default=0.0)
        if max_ln_s >= 7.0:
            selected_indices: set[int] = set()
            if intro_line.endswith(":"):
                selected_indices.add(0)
            for s, idx, _ in scored_lines:
                if s >= max(5.5, max_ln_s * 0.65):
                    selected_indices.add(idx)
                    if idx + 1 < len(cl_lines) and cl_lines[idx].endswith(":"):
                        selected_indices.add(idx + 1)
            if selected_indices and len(selected_indices) < len(cl_lines):
                ordered = [cl_lines[i] for i in sorted(selected_indices)]
                return "\n".join(ordered), []

    return clause_text, []


def _extract_focus_content_from_chunk_with_meta(
    question: str, chunk_content: str
) -> tuple[str, list[str], list[str]]:
    """
    Trích xuất ĐÚNG Khoản / Điểm / Đoạn nội dung trọng tâm trả lời trực tiếp cho câu hỏi
    (không kéo theo các khoản hoặc mục khác không liên quan trong cùng Điều luật):
    - Trả về bộ 3: `(focused_text, matched_clause_numbers, matched_point_letters)`.
    """
    text = (chunk_content or "").strip()
    if not text:
        return "", [], []

    text = re.split(
        r"(?m)^\s*(?:Luật|Bộ\s+luật|Nghị\s+quyết)\s+này\s+được\s+Quốc\s+hội\s+nước\s+Cộng\s+hòa",
        text,
        maxsplit=1,
    )[0].strip()

    parsed = parse_legal_query(question)
    target_articles: list[str] = parsed["target_articles"]
    target_clauses: list[str] = parsed["target_clauses"]
    target_points: list[str] = parsed["target_points"]
    q_core: str = parsed["topic_core"]
    q_tokens: list[str] = parsed["topic_tokens"]
    q_bigrams: list[str] = parsed["topic_bigrams"]

    appendix_parts = re.split(
        r"(?m)^(?=(?:PHỤ\s+LỤC|Phụ\s+lục|DANH\s+MỤC)\b)", text
    )
    if len(appendix_parts) > 1:
        if target_articles and not q_tokens:
            text = appendix_parts[0].strip()
        elif q_tokens:
            best_part = appendix_parts[0].strip()
            best_part_score = -1.0
            for part in appendix_parts:
                p_norm = _normalize_vn_text(part)
                p_score = sum(4.0 for bg in q_bigrams if f" {bg} " in f" {p_norm} ")
                p_score += sum(1.5 for t in q_tokens if f" {t} " in f" {p_norm} ")
                if q_core and q_core in p_norm:
                    p_score += 15.0
                if p_score > best_part_score:
                    best_part_score = p_score
                    best_part = part.strip()
            text = best_part

    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if not lines:
        return "", [], []

    first_line_is_header = bool(
        re.match(
            r"^(?:Điều|ĐIỀU|PHỤ\s+LỤC|Phụ\s+lục|DANH\s+MỤC|Danh\s+mục|MỤC|Mục|CHƯƠNG|Chương)\b",
            lines[0],
        )
    )
    header_line = lines[0] if first_line_is_header else ""
    body_lines = lines[1:] if first_line_is_header else lines
    body_text = "\n".join(body_lines).strip()

    if not body_text:
        return text, [], []

    raw_blocks = [
        c.strip()
        for c in re.split(r"(?m)^(?=\d{1,3}\.\s+)", body_text)
        if c and c.strip()
    ]

    # Tách đoạn dẫn nhập mở đầu Điều (preamble trước Khoản 1, ví dụ ở Điều 25 Bộ luật Lao động)
    preamble_block = ""
    clause_blocks: list[str] = []
    if raw_blocks and not re.match(r"^\d{1,3}\.\s+", raw_blocks[0]):
        preamble_block = raw_blocks[0]
        clause_blocks = raw_blocks[1:]
    else:
        clause_blocks = raw_blocks

    # Trường hợp A: Người dùng hỏi đích danh số Khoản (ví dụ: "Khoản 1 Điều 15")
    if target_clauses and len(clause_blocks) >= 1:
        matched_clauses: list[str] = []
        matched_nums: list[str] = []
        for clause in clause_blocks:
            m_cl = re.match(r"^(\d{1,3})\.\s+", clause)
            if m_cl and m_cl.group(1) in target_clauses:
                matched_clauses.append(clause)
                matched_nums.append(m_cl.group(1))
        if matched_clauses:
            prefix_parts = [p for p in (header_line, preamble_block) if p]
            prefix_str = "\n".join(prefix_parts)
            if target_points and len(matched_clauses) == 1:
                cl_txt, pt_list = _filter_points_in_clause(
                    matched_clauses[0], target_points, q_core, q_tokens, q_bigrams
                )
                out = f"{prefix_str}\n{cl_txt}".strip() if prefix_str else cl_txt
                return out, matched_nums, pt_list
            out = (
                f"{prefix_str}\n" + "\n".join(matched_clauses)
                if prefix_str
                else "\n".join(matched_clauses)
            )
            return out.strip(), matched_nums, []

    # Trường hợp B: Người dùng hỏi toàn bộ một Điều luật theo số Điều (vd: "Điều 40 là gì")
    if target_articles and not q_tokens:
        return text, [], []

    if not q_tokens:
        return text, [], []

    # Trường hợp C: Điều luật có các Khoản đánh số (1., 2., 3....)
    if len(clause_blocks) >= 1:
        if len(clause_blocks) == 1:
            sel_clause = clause_blocks[0]
            m_cl = re.match(r"^(\d{1,3})\.\s+", sel_clause)
            sel_num = m_cl.group(1) if m_cl else ""
            narrowed_clause, pt_list = _filter_points_in_clause(
                sel_clause, target_points, q_core, q_tokens, q_bigrams
            )
            prefix_parts = [p for p in (header_line, preamble_block) if p]
            prefix_str = "\n".join(prefix_parts)
            out_txt = f"{prefix_str}\n{narrowed_clause}".strip() if prefix_str else narrowed_clause
            return out_txt, ([sel_num] if sel_num and pt_list else []), pt_list

        scored_clauses: list[tuple[float, str, str]] = []
        core_words = [
            w for w in q_core.split() if w not in {"của", "và", "trong", "với", "tại", "theo", "về", "là"} and len(w) > 1
        ]
        header_and_preamble_norm = _normalize_vn_text(f"{header_line} {preamble_block}")
        specific_beyond_header = [
            t for t in q_tokens if f" {t} " not in f" {header_and_preamble_norm} "
        ]

        for clause in clause_blocks:
            m_cl = re.match(r"^(\d{1,3})\.\s+", clause)
            cl_num = m_cl.group(1) if m_cl else ""
            cl_lines = [ln.strip() for ln in clause.split("\n") if ln.strip()]
            cl_intro = cl_lines[0] if cl_lines else clause
            cl_intro_norm = _normalize_vn_text(cl_intro)
            cl_full_norm = _normalize_vn_text(clause)

            is_ref_clause = bool(
                re.search(
                    r"\b(?:quy định tại khoản|theo quy định tại khoản|quy định tại các khoản|chính phủ quy định chi tiết)\b",
                    cl_intro_norm,
                )
            )

            score = 0.0

            if q_core and re.match(
                rf"^\d{{1,3}}\s+{re.escape(q_core)}\s+(?:là|bao gồm|gồm|được|có|áp dụng|thực hiện|không)\b",
                cl_intro_norm,
            ):
                score += 48.0
            elif q_core and re.match(rf"^\d{{1,3}}\s+{re.escape(q_core)}\b", cl_intro_norm):
                score += 40.0
            elif q_core and len(core_words) >= 2 and q_core in cl_intro_norm:
                score += 10.0 if is_ref_clause else 28.0
            elif q_core and len(core_words) >= 2 and q_core in cl_full_norm:
                score += 15.0

            m_subj = re.match(
                r"^\d{1,3}\s+(.{3,65}?)\s+(?:là|bao gồm|gồm)\b", cl_intro_norm
            )
            if m_subj and core_words:
                subj_norm = m_subj.group(1).strip()
                if not subj_norm.startswith(("căn cứ", "trường hợp", "việc ", "nhà đầu tư", "người ")):
                    subj_hits = sum(
                        1 for w in core_words if f" {w} " in f" {subj_norm} "
                    )
                    subj_ratio = subj_hits / len(core_words)
                    if subj_ratio >= 0.85:
                        score += 22.0
                    elif subj_ratio < 0.70:
                        score -= 20.0

            for bg in q_bigrams:
                if f" {bg} " in f" {cl_intro_norm} ":
                    score += 5.5
                elif f" {bg} " in f" {cl_full_norm} ":
                    score += 3.2

            intro_hits = sum(
                1 for t in q_tokens if f" {t} " in f" {cl_intro_norm} "
            )
            full_hits = sum(
                1 for t in q_tokens if f" {t} " in f" {cl_full_norm} "
            )
            score += intro_hits * 2.5 + full_hits * 1.2

            if specific_beyond_header:
                spec_hits = sum(
                    1 for t in specific_beyond_header if f" {t} " in f" {cl_full_norm} "
                )
                score += spec_hits * 6.0

            if is_ref_clause and not any(
                k in q_tokens for k in ("chính", "phủ", "sửa", "đổi", "bổ", "sung", "thẩm", "quyền")
            ):
                score *= 0.30

            scored_clauses.append((score, cl_num, clause))

        max_score = max((s for s, _, _ in scored_clauses), default=0.0)
        min_score = min((s for s, _, _ in scored_clauses), default=0.0)

        # Nếu có câu dẫn nhập kết thúc bằng ':' (như Điều 25) và mọi khoản đều có điểm ngang nhau (người dùng hỏi chung cả Điều)
        if preamble_block.endswith(":") and (max_score - min_score < 3.0) and not specific_beyond_header:
            return text, [], []

        if max_score >= 4.0:
            threshold = max(4.5, max_score * 0.65)
            selected_items = [
                (num, cl) for s, num, cl in scored_clauses if s >= threshold
            ]

            if selected_items:
                prefix_parts = [header_line] if header_line else []
                if preamble_block and preamble_block.endswith(":"):
                    prefix_parts.append(preamble_block)
                prefix_str = "\n".join(prefix_parts)

                if len(selected_items) == 1:
                    sel_num, sel_clause = selected_items[0]
                    narrowed_clause, pt_list = _filter_points_in_clause(
                        sel_clause, target_points, q_core, q_tokens, q_bigrams
                    )
                    out_txt = (
                        f"{prefix_str}\n{narrowed_clause}".strip()
                        if prefix_str
                        else narrowed_clause
                    )
                    return out_txt, ([sel_num] if sel_num else []), pt_list

                if len(selected_items) < len(clause_blocks):
                    sel_nums = [num for num, _ in selected_items if num]
                    sel_texts = [cl for _, cl in selected_items]
                    out_txt = (
                        f"{prefix_str}\n" + "\n".join(sel_texts)
                        if prefix_str
                        else "\n".join(sel_texts)
                    )
                    return out_txt.strip(), sel_nums, []

    # Trường hợp D: Đoạn văn bản không chia theo Khoản 1., 2.
    narrowed_body, pt_list = _filter_points_in_clause(
        body_text, target_points, q_core, q_tokens, q_bigrams
    )
    if narrowed_body != body_text:
        out_txt = f"{header_line}\n{narrowed_body}".strip() if header_line else narrowed_body
        return out_txt, [], pt_list

    return text, [], []


def _extract_focus_content_from_chunk(question: str, chunk_content: str) -> str:
    """Hàm tương thích ngược: trả về chuỗi nội dung trọng tâm đã lọc."""
    focused_text, _, _ = _extract_focus_content_from_chunk_with_meta(
        question, chunk_content
    )
    return focused_text


def build_citation_label(
    article_label: str,
    matched_clauses: list[str] | None = None,
    matched_points: list[str] | None = None,
) -> str:
    """
    Tạo nhãn vị trí điều luật cụ thể, ví dụ:
    - 'Điểm a, Khoản 1, Điều 15'
    - 'Khoản 1, Điều 15'
    - 'Điều 15'
    """
    parts: list[str] = []
    if matched_points:
        if len(matched_points) == 1:
            parts.append(f"Điểm {matched_points[0]}")
        else:
            parts.append("Điểm " + ", ".join(matched_points))
    if matched_clauses:
        if len(matched_clauses) == 1:
            parts.append(f"Khoản {matched_clauses[0]}")
        else:
            parts.append("Khoản " + ", ".join(matched_clauses))
    if article_label:
        parts.append(article_label)
    return ", ".join(parts) if parts else "Điều luật"


class LocalEmbeddingEngine:
    """
    Bộ tạo Embedding trực tiếp trên máy cục bộ (Local Embedding) với cơ chế Lazy-Loading
    giúp khởi động Uvicorn trên Windows nhanh tức thì và không bị treo SpawnProcess.
    """

    EMBED_DIM = 384

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or settings.LOCAL_EMBEDDING_MODEL
        self._st_model: Any = None
        self._initialized: bool = False
        self._backend_name: str = f"local-embedding ({self.model_name})"

    def _ensure_backend_loaded(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        try:
            import logging
            logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
            logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
            from sentence_transformers import SentenceTransformer

            self._st_model = SentenceTransformer(self.model_name)
            self._backend_name = f"sentence-transformers ({self.model_name})"
        except Exception:
            self._st_model = None
            self._backend_name = "local-vietnamese-384d-embedding"

    @property
    def backend_name(self) -> str:
        return self._backend_name

    def _offline_vietnamese_embed(self, text: str) -> list[float]:
        raw_text = (text or "").strip()
        first_line = raw_text.split("\n", 1)[0].strip()

        expanded_parts = [raw_text]
        if first_line:
            expanded_parts.append(first_line)
            expanded_parts.append(first_line)
            expanded_parts.append(first_line)

        lower_raw = raw_text.lower()
        for triggers, expansion in _LEGAL_SYNONYM_EXPANSIONS:
            if any(t in lower_raw for t in triggers):
                expanded_parts.append(expansion)
                expanded_parts.append(expansion)

        norm = _normalize_vn_text(" ".join(expanded_parts))
        tokens = [t for t in norm.split() if t and t not in _VN_STOPWORDS]
        if not tokens:
            tokens = norm.split()

        vec = [0.0] * self.EMBED_DIM
        if not tokens:
            vec[0] = 1.0
            return vec

        features: list[tuple[str, float]] = []

        for tok in tokens:
            weight = 2.2 if tok.isdigit() else 1.8
            features.append((f"u:{tok}", weight))
            no_acc = _remove_accents(tok)
            if no_acc != tok:
                features.append((f"ua:{no_acc}", 1.0))

        for i in range(len(tokens) - 1):
            bg = f"{tokens[i]}_{tokens[i + 1]}"
            features.append((f"b:{bg}", 3.2))
            bg_no_acc = _remove_accents(bg)
            if bg_no_acc != bg:
                features.append((f"ba:{bg_no_acc}", 1.6))

        for i in range(len(tokens) - 2):
            tg = f"{tokens[i]}_{tokens[i + 1]}_{tokens[i + 2]}"
            features.append((f"t:{tg}", 2.6))

        tf_counts: dict[str, float] = {}
        for feat, w in features:
            tf_counts[feat] = tf_counts.get(feat, 0.0) + w

        for feat, total_w in tf_counts.items():
            scaled_w = 1.0 + math.log(max(1.0, total_w))
            digest = hashlib.md5(feat.encode("utf-8")).digest()
            idx1 = int.from_bytes(digest[0:2], "little") % self.EMBED_DIM
            sign1 = 1.0 if (digest[2] & 1) == 0 else -1.0
            idx2 = int.from_bytes(digest[4:6], "little") % self.EMBED_DIM
            sign2 = 1.0 if (digest[6] & 1) == 0 else -1.0
            vec[idx1] += sign1 * scaled_w
            vec[idx2] += sign2 * (scaled_w * 0.7)

        norm_val = math.sqrt(sum(v * v for v in vec))
        if norm_val > 1e-12:
            vec = [round(v / norm_val, 6) for v in vec]
        else:
            vec[0] = 1.0
        return vec

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self._ensure_backend_loaded()
        if self._st_model is not None:
            embeddings = self._st_model.encode(
                texts, normalize_embeddings=True, show_progress_bar=False
            )
            return [list(map(float, emb)) for emb in embeddings]
        return [self._offline_vietnamese_embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        self._ensure_backend_loaded()
        if self._st_model is not None:
            emb = self._st_model.encode(
                [text], normalize_embeddings=True, show_progress_bar=False
            )[0]
            return list(map(float, emb))
        return self._offline_vietnamese_embed(text)


class Embedding:
    """Lớp Embedding theo Sơ đồ lớp UML."""

    def __init__(
        self,
        embedding_id: str = "",
        chunk_id: str = "",
        vector: list[float] | None = None,
        model: str = "local",
    ) -> None:
        self.embeddingId = embedding_id
        self.chunkId = chunk_id
        self.vector = vector or []
        self.model = model

    def generate(self, text: str, engine: LocalEmbeddingEngine) -> list[float]:
        self.vector = engine.embed_query(text)
        self.model = engine.backend_name
        return self.vector


class GeminiClient:
    """
    Lớp AIService / GeminiClient:
    - Tạo Embedding trực tiếp tại Local (`EMBEDDING_PROVIDER=local`) để tiết kiệm quota API.
    - Gọi Google Gemini API (`generate_answer`) hoặc trích xuất trọng tâm để sinh câu trả lời chính xác.
    """

    def __init__(self) -> None:
        self.apiKey: str = settings.GEMINI_API_KEY
        self.model: str = settings.GEMINI_MODEL
        self.embeddingProvider: str = settings.EMBEDDING_PROVIDER
        self.localEngine = LocalEmbeddingEngine(settings.LOCAL_EMBEDDING_MODEL)

    def _refresh_api_key_from_env(self) -> None:
        if self._has_valid_api_key():
            return
        if ENV_FILE.exists():
            try:
                for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
                    line = raw_line.strip()
                    if line.startswith("GEMINI_API_KEY="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val and val != "YOUR_GEMINI_API_KEY_HERE":
                            self.apiKey = val
                            settings.GEMINI_API_KEY = val
                            os.environ["GEMINI_API_KEY"] = val
                        break
            except Exception:
                pass

    def _has_valid_api_key(self) -> bool:
        key = (self.apiKey or "").strip()
        return bool(key and key != "YOUR_GEMINI_API_KEY_HERE")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.embeddingProvider == "gemini" and self._has_valid_api_key():
            try:
                return [
                    self._call_gemini_embedding_api(t, task_type="RETRIEVAL_DOCUMENT")
                    for t in texts
                ]
            except Exception:
                return self.localEngine.embed_documents(texts)
        return self.localEngine.embed_documents(texts)

    def embed_query(self, query: str) -> list[float]:
        if self.embeddingProvider == "gemini" and self._has_valid_api_key():
            try:
                return self._call_gemini_embedding_api(query, task_type="RETRIEVAL_QUERY")
            except Exception:
                return self.localEngine.embed_query(query)
        return self.localEngine.embed_query(query)

    def _call_gemini_embedding_api(self, text: str, task_type: str) -> list[float]:
        emb_model = settings.GEMINI_EMBEDDING_MODEL
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{emb_model}:embedContent?key={self.apiKey}"
        )
        payload = {
            "model": f"models/{emb_model}",
            "taskType": task_type,
            "content": {"parts": [{"text": text}]},
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return [float(x) for x in data["embedding"]["values"]]

    def _candidate_models(self) -> list[str]:
        candidates = [
            self.model,
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
        ]
        unique: list[str] = []
        for m in candidates:
            m_clean = (m or "").strip()
            if m_clean and m_clean not in unique:
                unique.append(m_clean)
        return unique

    def callAPI(
        self, prompt: str, system_instruction: str = SYSTEM_INSTRUCTION_LEGAL_RAG
    ) -> tuple[str, str]:
        last_error: Exception | None = None

        for model_name in self._candidate_models():
            try:
                url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model_name}:generateContent?key={self.apiKey}"
                )
                payload = {
                    "systemInstruction": {"parts": [{"text": system_instruction}]},
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": settings.GEMINI_TEMPERATURE,
                        "maxOutputTokens": settings.GEMINI_MAX_OUTPUT_TOKENS,
                    },
                }
                with httpx.Client(timeout=45.0) as client:
                    resp = client.post(url, json=payload)
                    if resp.status_code == 404:
                        last_error = RuntimeError(
                            f"Model '{model_name}' không tồn tại (HTTP 404)."
                        )
                        continue
                    if resp.status_code >= 400:
                        err_detail = resp.text
                        try:
                            err_json = resp.json()
                            err_detail = err_json.get("error", {}).get(
                                "message", resp.text
                            )
                        except Exception:
                            pass
                        raise RuntimeError(
                            f"Lỗi gọi Gemini API ({resp.status_code}): {err_detail}"
                        )

                    data = resp.json()
                    candidates = data.get("candidates") or []
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts") or []
                        text_out = "".join(p.get("text", "") for p in parts).strip()
                        if text_out:
                            text_out = text_out.replace("**", "")
                            return text_out, model_name
            except Exception as exc:
                last_error = exc
                err_str = str(exc)
                if any(
                    code in err_str
                    for code in ("400", "401", "403", "429", "API key")
                ):
                    break

        raise RuntimeError(f"Không thể sinh câu trả lời từ Gemini API: {last_error}")

    def _build_extractive_legal_answer(
        self, question: str, retrieved_chunks: list[dict[str, Any]]
    ) -> str:
        if not retrieved_chunks:
            return (
                "Hiện tại trong kho dữ liệu pháp luật của hệ thống chưa có văn bản hoặc "
                "Điều luật nào quy định trực tiếp về nội dung bạn hỏi."
            )

        top = retrieved_chunks[0]
        display_title = top.get("display_title") or top.get("title", "Văn bản pháp luật")
        article_label = top.get("article", "Điều luật")
        raw_content = (top.get("content") or "").strip()

        focused_content, matched_clauses, matched_points = (
            _extract_focus_content_from_chunk_with_meta(question, raw_content)
        )
        citation_loc = top.get("citation_label") or build_citation_label(
            article_label, matched_clauses, matched_points
        )

        return (
            f"Theo quy định tại {citation_loc} của {display_title}:\n\n"
            f"{focused_content}"
        )

    def generate_answer(
        self,
        question: str,
        context_text: str,
        retrieved_chunks: list[dict[str, Any]],
    ) -> tuple[str, str]:
        if not retrieved_chunks:
            return (
                "Hiện tại hệ thống chưa tìm thấy văn bản hoặc Điều luật nào trong kho dữ liệu "
                "quy định về nội dung câu hỏi của bạn.",
                self.model,
            )

        self._refresh_api_key_from_env()

        top = retrieved_chunks[0]
        citation_loc = top.get("citation_label") or top.get("article", "Điều luật")
        display_title = top.get("display_title") or top.get("title", "Văn bản pháp luật")

        user_prompt = (
            f"[NGỮ CẢNH PHÁP LUẬT ĐÃ LỌC ĐÚNG TRỌNG TÂM]\n"
            f"{context_text}\n\n"
            f"[CÂU HỎI CỦA NGƯỜI DÙNG]\n"
            f"{question}\n\n"
            f"Yêu cầu bắt buộc:\n"
            f"- Mở đầu bằng: 'Theo quy định tại {citation_loc} của {display_title}:'\n"
            f"- Chỉ trả lời đúng nội dung được hỏi dựa trên đoạn ngữ cảnh đã lọc ở trên (giữ đầy đủ các điểm a, b, c... của khoản đó).\n"
            f"- Tuyệt đối không gắn thêm các khoản hoặc mục khác không được hỏi."
        )

        if self._has_valid_api_key():
            try:
                return self.callAPI(
                    user_prompt, system_instruction=SYSTEM_INSTRUCTION_LEGAL_RAG
                )
            except Exception:
                if settings.ALLOW_EXTRACTIVE_FALLBACK:
                    return (
                        self._build_extractive_legal_answer(question, retrieved_chunks),
                        f"{self.model} (local-rag)",
                    )
                raise

        if settings.ALLOW_EXTRACTIVE_FALLBACK:
            answer_text = self._build_extractive_legal_answer(
                question, retrieved_chunks
            )
            return answer_text, f"{self.model} (local-rag)"

        raise RuntimeError(
            "Chưa cấu hình GEMINI_API_KEY trong file .env. Vui lòng cập nhật GEMINI_API_KEY để gọi Gemini API."
        )


gemini_client = GeminiClient()