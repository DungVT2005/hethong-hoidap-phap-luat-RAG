"""
Dịch vụ nghiệp vụ RAG (RAGService theo sơ đồ lớp UML):
- Tự chứa đầy đủ hàm phân tích câu hỏi (`parse_legal_query`), hàm trích xuất đúng Khoản/Điểm trọng tâm
  (`_extract_focus_content_from_chunk_with_meta`) và hàm định dạng căn cứ pháp lý (`build_citation_label`,
  `format_law_title_for_citation`) ngay trong file này để KHÔNG BAO GIỜ bị lỗi `ImportError`.
- Khi hỏi một nội dung/khái niệm/quy định nhỏ (ví dụ: "Ngành, nghề ưu đãi đầu tư là gì"),
  hệ thống CHỈ trích xuất đúng Khoản/Điểm quy định về nội dung đó (ví dụ: Khoản 1 Điều 15, đầy đủ các điểm a..i),
  tuyệt đối KHÔNG kéo theo các Khoản khác không liên quan (như Khoản 2 về Địa bàn ưu đãi đầu tư).
- Thể hiện rõ ràng căn cứ ở ngay đầu câu trả lời:
  "Theo quy định tại Khoản X, Điều Y của Luật Z:"
"""
from __future__ import annotations

import re
import unicodedata
import uuid
from typing import Any

from app.config import settings
from app.database import HAS_SQLALCHEMY
from app.document_processor import (
    DocumentProcessor,
    clean_legal_text,
    document_processor,
    estimate_token_count,
)
from app.gemini_client import GeminiClient, gemini_client
from app.mappers import (
    map_conversation_to_dict,
    map_document_to_dict,
    map_source_to_dict,
)
from app.models import (
    Answer,
    AnswerSource,
    ChatHistory,
    DocumentChunk,
    Question,
    SourceDocument,
    extract_article_heading,
)
from app.vector_store import VectorStore, vector_store

_QUERY_STOPWORDS = {
    "là", "và", "của", "có", "được", "trong", "cho", "các", "với", "những",
    "một", "này", "đó", "khi", "thì", "mà", "như", "về", "tại", "theo",
    "để", "đến", "từ", "hay", "hoặc", "nếu", "nhưng", "vì", "do", "bởi",
    "bao", "nhiêu", "nào", "thế", "sao", "quy", "định", "gì", "ai", "đâu",
    "cho", "tôi", "hỏi", "biết", "hãy", "nêu", "trình", "bày", "cụ", "thể",
    "chi", "tiết", "nội", "dung", "thuộc", "gồm", "bao", "những", "trường",
    "hợp", "căn", "cứ", "mục", "điều", "khoản", "điểm",
}


def _norm_for_match(text: str) -> str:
    text = unicodedata.normalize("NFC", (text or "").lower())
    text = re.sub(
        r"[^\w\sđáàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵ]",
        " ",
        text,
    )
    return re.sub(r"\s+", " ", text).strip()


def parse_legal_query(question: str) -> dict[str, Any]:
    """
    Phân tích cấu trúc câu hỏi pháp luật của người dùng:
    - target_articles: Danh sách số hiệu Điều được hỏi trực tiếp (vd: ['15'], ['40'], ['48']).
    - target_clauses: Danh sách số hiệu Khoản được hỏi trực tiếp (vd: ['1'], ['2']).
    - target_points: Danh sách Điểm được hỏi trực tiếp (vd: ['a'], ['b']).
    - doc_hint: Tên loại/văn bản luật được nhắc tới trong câu hỏi (vd: 'luật đầu tư').
    - topic_core: Cụm từ khóa nội dung thực chất sau khi đã loại bỏ từ để hỏi & phần dẫn chiếu.
    - topic_tokens: Danh sách từ khóa đơn phục vụ đối sánh.
    - topic_bigrams: Danh sách các cụm từ ghép 2 âm tiết liên tiếp (vd: 'ngành nghề', 'ưu đãi', 'thông nước').
    - tail_entity: Cụm danh từ trọng tâm ở cuối câu hỏi (ví dụ sau chữ 'của': 'thông nước').
    """
    raw_lower = unicodedata.normalize("NFC", (question or "").lower()).strip()
    q_norm = _norm_for_match(raw_lower)

    # 1. Bóc tách số hiệu Điều
    target_articles: list[str] = []
    for m in re.finditer(r"\bđiều\s+(\d+[a-z0-9]*)\b", q_norm):
        art_num = m.group(1).strip()
        if art_num not in target_articles:
            target_articles.append(art_num)

    # 2. Bóc tách số hiệu Khoản
    target_clauses: list[str] = []
    for m in re.finditer(r"\bkhoản\s+(\d{1,3})\b", q_norm):
        cl_num = m.group(1).strip()
        if cl_num not in target_clauses:
            target_clauses.append(cl_num)

    # 3. Bóc tách ký hiệu Điểm (điểm a, điểm b, điểm đ)
    target_points: list[str] = []
    for m in re.finditer(r"\bđiểm\s+([a-zđ])\b", q_norm):
        pt_char = m.group(1).strip()
        if pt_char not in target_points:
            target_points.append(pt_char)

    # 4. Bóc tách gợi ý tên văn bản pháp luật (doc_hint)
    doc_hint = ""
    doc_match = re.search(
        r"\b((?:bộ\s+luật|luật|nghị\s+định|thông\s+tư|pháp\s+lệnh|hiến\s+pháp)\s+"
        r"[a-z0-9đáàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵ\s\-/]{1,35}?)"
        r"(?=\s*(?:,|\.|;|\?|\bđiều\b|\bkhoản\b|\bquy\s+định\b|\blà\s+gì\b|\bnhư\s+thế\s+nào\b|\bcó\s+những\b|\bgồm\b|\bthì\b|$))",
        raw_lower,
    )
    if doc_match:
        candidate_hint = _norm_for_match(doc_match.group(1))
        candidate_hint = re.sub(
            r"\b(điều|khoản|điểm|là|gì|quy|định|như|thế|nào)\b.*$", "", candidate_hint
        ).strip()
        if len(candidate_hint.split()) >= 2:
            doc_hint = candidate_hint

    # 5. Xây dựng topic_core
    work = raw_lower
    work = re.sub(
        r"^\s*(?:trong|theo|tại|căn\s+cứ|ở)\s+(?:quy\s+định\s+(?:của|tại)\s+)?(?:bộ\s+luật|luật|nghị\s+định|thông\s+tư)[^,\.;\?\n]*[,\.;]\s*",
        " ",
        work,
    )
    work_norm = _norm_for_match(work)
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
    topic_core = re.sub(r"^(?:của|trong|về|tại|theo|là|có|được)\s+", "", topic_core).strip()
    topic_core = re.sub(r"\s+(?:của|trong|về|tại|theo|là|gì|nào|đó|này)$", "", topic_core).strip()

    # Nhận diện thực thể đích sau chữ "của" (ví dụ: "tên khoa học của thông nước" -> tail_entity = "thông nước")
    tail_entity = ""
    if " của " in topic_core:
        after_cua = topic_core.split(" của ")[-1].strip()
        if len(after_cua.split()) >= 1 and len(after_cua) >= 3:
            tail_entity = after_cua

    topic_tokens = [
        t for t in topic_core.split() if t not in _QUERY_STOPWORDS and len(t) > 1
    ]
    if not topic_tokens:
        topic_core = ""

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
        "tail_entity": tail_entity,
    }


def format_law_title_for_citation(doc_title: str, doc_content: str = "") -> str:
    """
    Chuẩn hóa tên văn bản luật để hiển thị rõ ràng trong câu trả lời:
    - Nếu doc_title chỉ là tên file như 'Luật-143-2025-QH15.pdf', tự động dò tên Luật chính thức
      trong phần mở đầu của văn bản (vd: 'LUẬT ĐẦU TƯ') để hiển thị:
      'Luật Đầu tư số 143/2025/QH15 (Luật-143-2025-QH15.pdf)'.
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
                    titled = " ".join(w.capitalize() for w in words)
                    titled = re.sub(r"^Luật\s+đầu\s+tư$", "Luật Đầu tư", titled, flags=re.I)
                    titled = re.sub(r"^Bộ\s+luật\s+lao\s+động$", "Bộ luật Lao động", titled, flags=re.I)
                    titled = re.sub(r"^Bộ\s+luật\s+dân\s+sự$", "Bộ luật Dân sự", titled, flags=re.I)
                    detected_law_name = titled
                    break

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
    intro_norm = _norm_for_match(intro_line)
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
            pt_norm = _norm_for_match(pt)
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
            ln_norm = _norm_for_match(ln)
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
                p_norm = _norm_for_match(part)
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
        header_and_preamble_norm = _norm_for_match(f"{header_line} {preamble_block}")
        specific_beyond_header = [
            t for t in q_tokens if f" {t} " not in f" {header_and_preamble_norm} "
        ]

        for clause in clause_blocks:
            m_cl = re.match(r"^(\d{1,3})\.\s+", clause)
            cl_num = m_cl.group(1) if m_cl else ""
            cl_lines = [ln.strip() for ln in clause.split("\n") if ln.strip()]
            cl_intro = cl_lines[0] if cl_lines else clause
            cl_intro_norm = _norm_for_match(cl_intro)
            cl_full_norm = _norm_for_match(clause)

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
    focused_text, _, _ = _extract_focus_content_from_chunk_with_meta(
        question, chunk_content
    )
    return focused_text


def _extract_article_number(article_label: str) -> str:
    """Lấy số hiệu chuẩn từ nhãn Điều (ví dụ: 'Điều 40' -> '40')."""
    m = re.search(r"^(?:Điều|ĐIỀU)\s+(\d+[a-zA-Z0-9]*)\b", (article_label or "").strip())
    return m.group(1).lower() if m else ""


def _merge_article_subchunks(subchunk_texts: list[str]) -> str:
    """
    Ghép nối các đoạn con (sub-chunks) của cùng một Điều luật theo đúng thứ tự
    từ Khoản 1 đến Khoản cuối cùng của Điều đó (dừng ngay nếu gặp Phụ lục / Danh mục).
    """
    if not subchunk_texts:
        return ""
    if len(subchunk_texts) == 1:
        return subchunk_texts[0].strip()

    first_lines = [ln.strip() for ln in subchunk_texts[0].split("\n") if ln.strip()]
    header_line = first_lines[0] if first_lines else ""
    header_prefix_norm = _norm_for_match(re.sub(r"\(tiếp theo\).*$", "", header_line))

    merged_lines: list[str] = []
    seen_clauses: set[str] = set()

    for idx, chunk_txt in enumerate(subchunk_texts):
        # Dừng ghép nếu đoạn con thực chất là phần Phụ lục / Danh mục ở cuối văn bản bị gắn nhầm nhãn Điều cuối
        if idx > 0 and re.search(r"(?m)^(?:PHỤ\s+LỤC|Phụ\s+lục|DANH\s+MỤC)\b", chunk_txt):
            chunk_txt = re.split(
                r"(?m)^(?=(?:PHỤ\s+LỤC|Phụ\s+lục|DANH\s+MỤC)\b)", chunk_txt, maxsplit=1
            )[0].strip()
            if not chunk_txt:
                break

        lines = [ln.strip() for ln in chunk_txt.strip().split("\n") if ln.strip()]
        if not lines:
            continue

        start_idx = 0
        if idx > 0:
            first_ln_norm = _norm_for_match(re.sub(r"\(tiếp theo\).*$", "", lines[0]))
            if (
                header_prefix_norm
                and (
                    first_ln_norm == header_prefix_norm
                    or first_ln_norm.startswith(header_prefix_norm)
                    or header_prefix_norm.startswith(first_ln_norm)
                )
            ) or re.match(r"^(?:Điều|ĐIỀU)\s+\d+", lines[0]):
                start_idx = 1

        body_part = "\n".join(lines[start_idx:]).strip()
        if not body_part:
            continue

        if idx == 0:
            merged_lines.append(header_line)
            body_after_header = "\n".join(lines[1:]).strip()
            if body_after_header:
                for cl in re.split(r"(?m)^(?=\d{1,3}\.\s+)", body_after_header):
                    cl_s = cl.strip()
                    if not cl_s:
                        continue
                    cl_key = _norm_for_match(cl_s[:120])
                    seen_clauses.add(cl_key)
                    merged_lines.append(cl_s)
        else:
            clause_pieces = [
                c.strip()
                for c in re.split(r"(?m)^(?=\d{1,3}\.\s+)", body_part)
                if c and c.strip()
            ]
            if len(clause_pieces) > 1 or re.match(r"^\d{1,3}\.\s+", body_part):
                for cl_s in clause_pieces:
                    cl_key = _norm_for_match(cl_s[:120])
                    if cl_key not in seen_clauses:
                        seen_clauses.add(cl_key)
                        merged_lines.append(cl_s)
            else:
                cl_key = _norm_for_match(body_part[:120])
                if cl_key not in seen_clauses:
                    seen_clauses.add(cl_key)
                    merged_lines.append(body_part)

    return "\n".join(merged_lines).strip()


def _extract_article_directly_from_fulltext(full_text: str, target_art_num: str) -> str:
    """
    Trích xuất trực tiếp toàn văn 'Điều <target_art_num>' từ toàn văn văn bản gốc
    (`source_documents.content`), dừng ngay khi gặp Điều tiếp theo, hoặc gặp PHỤ LỤC / DANH MỤC /
    dòng thông qua cuối luật (tránh lỗi Điều 52 nuốt trọn phần Phụ lục ở cuối file PDF).
    """
    if not full_text or not target_art_num:
        return ""
    cleaned = clean_legal_text(full_text)
    pattern = re.compile(
        rf"(?m)^((?:Điều|ĐIỀU)\s+{re.escape(target_art_num)}\s*[\.\:\-]\s*[^\n]+"
        rf"(?:\n(?!\s*(?:"
        rf"(?:Điều|ĐIỀU)\s+\d+[a-zA-Z0-9]*\s*[\.\:\-]\s*[A-ZÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬĐÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ]"
        rf"|(?:PHỤ\s+LỤC|Phụ\s+lục|DANH\s+MỤC)\b"
        rf"|(?:Luật|Bộ\s+luật|Nghị\s+quyết)\s+này\s+được\s+Quốc\s+hội"
        rf")).*)*)"
    )
    matches = [m.group(1).strip() for m in pattern.finditer(cleaned)]
    if not matches:
        return ""
    matches.sort(key=len, reverse=True)
    best = matches[0]
    best_lines = [
        ln
        for ln in best.split("\n")
        if not re.match(r"^\s*(?:CHƯƠNG|Chương|MỤC|Mục|PHẦN|Phần)\s+[IVXLCDM\d]+", ln)
    ]
    return "\n".join(best_lines).strip()


def _score_document_hint_match(
    doc_title: str, doc_type: str, doc_content: str, doc_hint: str
) -> float:
    """Chấm điểm mức độ khớp giữa tên văn bản mà người dùng nhắc tới (`doc_hint`) với văn bản trong CSDL."""
    if not doc_hint:
        return 0.0

    hint_norm = _norm_for_match(doc_hint)
    title_norm = _norm_for_match(doc_title)

    generic_doc_words = {
        "bộ", "luật", "nghị", "định", "thông", "tư", "pháp", "lệnh", "hiến", "pháp",
        "số", "năm", "của", "về", "và", "văn", "bản", "pdf", "docx", "txt", "md",
        "qh", "qh13", "qh14", "qh15", "nd", "nđ", "cp", "tt",
    }
    specific_hint_tokens = [
        t
        for t in hint_norm.split()
        if t not in generic_doc_words and not t.isdigit() and len(t) > 1
    ]
    if not specific_hint_tokens:
        return 0.0

    spec_phrase = " ".join(specific_hint_tokens)

    if hint_norm in title_norm or spec_phrase in title_norm:
        return 0.55

    title_specific_tokens = [
        t
        for t in title_norm.split()
        if t not in generic_doc_words
        and not t.isdigit()
        and not re.match(r"^(?:qh|nđ|nd|cp|tt)\d*$", t)
        and len(t) > 1
    ]
    if title_specific_tokens:
        overlap = sum(1 for t in specific_hint_tokens if t in title_specific_tokens)
        if overlap == 0:
            return -0.50
        return 0.40 * (overlap / len(specific_hint_tokens))

    raw_content = doc_content or ""
    preamble_split = re.split(r"(?m)^\s*(?:Điều|ĐIỀU)\s+1\s*[\.\:]", raw_content, maxsplit=1)
    preamble_norm = _norm_for_match(preamble_split[0][:1500]) if preamble_split else ""
    head_norm = _norm_for_match(raw_content[:2500])

    if hint_norm in preamble_norm or spec_phrase in preamble_norm:
        return 0.55

    phrase_occurrences = len(re.findall(rf"\b{re.escape(spec_phrase)}\b", head_norm))
    if phrase_occurrences >= 3:
        return 0.50
    if phrase_occurrences >= 1 and hint_norm in head_norm:
        return 0.45

    return -0.35


class RAGService:
    """Lớp RAGService theo đúng Sơ đồ lớp UML (Class Diagram)."""

    def __init__(
        self,
        v_store: VectorStore = vector_store,
        ai_client: GeminiClient = gemini_client,
        doc_proc: DocumentProcessor = document_processor,
    ) -> None:
        self.vectorDB = v_store
        self.aiService = ai_client
        self.docProcessor = doc_proc

    def ingestDocument(
        self,
        db: Any,
        filename: str,
        file_bytes: bytes,
        title: str | None = None,
        document_type: str | None = "Luật",
        issuing_agency: str | None = "",
        issue_date: str | None = "",
        created_by: str | None = None,
        document_url: str | None = None,
    ) -> dict[str, Any]:
        cleaned_text = self.docProcessor.readDocument(filename, file_bytes)
        if not cleaned_text:
            raise ValueError("File văn bản rỗng hoặc không trích xuất được nội dung.")

        chunk_texts = self.docProcessor.splitIntoChunks(cleaned_text)
        if not chunk_texts:
            raise ValueError("Không thể chia đoạn văn bản từ tài liệu đã tải lên.")

        embeddings = self.aiService.embed_documents(chunk_texts)
        if len(embeddings) != len(chunk_texts):
            raise RuntimeError("Số lượng vector embedding không khớp với số đoạn văn bản.")

        doc_id = str(uuid.uuid4())
        final_title = (title or "").strip() or filename
        final_type = (document_type or "").strip() or "Văn bản"
        final_agency = (issuing_agency or "").strip()
        final_issue_date = (issue_date or "").strip()

        chunk_ids: list[str] = []
        metadatas: list[dict[str, Any]] = []
        added_to_vector_store = False

        try:
            source_doc = SourceDocument(
                document_id=doc_id,
                title=final_title,
                document_type=final_type,
                issue_date=final_issue_date,
                issuing_agency=final_agency,
                document_url=document_url,
                content=cleaned_text,
                file_name=filename,
                created_by=created_by,
            )
            db.add(source_doc)

            for idx, c_text in enumerate(chunk_texts):
                cid = str(uuid.uuid4())
                chunk_ids.append(cid)
                article_label = extract_article_heading(c_text, idx)
                token_cnt = estimate_token_count(c_text)

                chunk_obj = DocumentChunk(
                    chunk_id=cid,
                    document_id=doc_id,
                    chunk_index=idx,
                    content=c_text,
                    token_count=token_cnt,
                )
                db.add(chunk_obj)

                metadatas.append(
                    {
                        "document_id": doc_id,
                        "chunk_index": idx,
                        "title": final_title,
                        "document_type": final_type,
                        "article": article_label,
                    }
                )

            db.flush()

            self.vectorDB.storeEmbedding(
                ids=chunk_ids,
                embeddings=embeddings,
                documents=chunk_texts,
                metadatas=metadatas,
            )
            added_to_vector_store = True

            db.commit()
            return map_document_to_dict(source_doc, chunk_count=len(chunk_ids))

        except Exception as exc:
            db.rollback()
            if added_to_vector_store and chunk_ids:
                try:
                    self.vectorDB.delete(ids=chunk_ids, document_id=doc_id)
                except Exception:
                    pass
            raise RuntimeError(f"Lỗi nạp văn bản vào hệ thống RAG: {exc}") from exc

    def _load_all_docs_and_chunks(self, db: Any) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
        docs_map: dict[str, dict[str, Any]] = {}
        chunks_list: list[dict[str, Any]] = []

        if HAS_SQLALCHEMY:
            for d in db.query(SourceDocument).all():
                docs_map[d.document_id] = {
                    "document_id": d.document_id,
                    "title": d.title or "Văn bản pháp luật",
                    "document_type": d.document_type or "Văn bản",
                    "issuing_agency": d.issuing_agency or "",
                    "issue_date": d.issue_date or "",
                    "content": d.content or "",
                }
            for c in (
                db.query(DocumentChunk)
                .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
                .all()
            ):
                chunks_list.append(
                    {
                        "chunk_id": c.chunk_id,
                        "document_id": c.document_id,
                        "chunk_index": c.chunk_index,
                        "content": c.content or "",
                    }
                )
        else:
            for d in db.fetchall_dicts("SELECT * FROM source_documents"):
                docs_map[d["document_id"]] = {
                    "document_id": d["document_id"],
                    "title": d.get("title") or "Văn bản pháp luật",
                    "document_type": d.get("document_type") or "Văn bản",
                    "issuing_agency": d.get("issuing_agency") or "",
                    "issue_date": d.get("issue_date") or "",
                    "content": d.get("content") or "",
                }
            for c in db.fetchall_dicts(
                "SELECT * FROM document_chunks ORDER BY document_id, chunk_index ASC"
            ):
                chunks_list.append(
                    {
                        "chunk_id": c["chunk_id"],
                        "document_id": c["document_id"],
                        "chunk_index": int(c.get("chunk_index", 0)),
                        "content": c.get("content") or "",
                    }
                )

        return docs_map, chunks_list

    def _reconstruct_full_article(
        self,
        document_id: str,
        article_label: str,
        all_chunks: list[dict[str, Any]],
        docs_map: dict[str, dict[str, Any]],
    ) -> tuple[str, str, int]:
        target_num = _extract_article_number(article_label)
        matching_subchunks: list[dict[str, Any]] = []

        for c in all_chunks:
            if c["document_id"] != document_id:
                continue
            c_label = extract_article_heading(c["content"], c["chunk_index"])
            c_num = _extract_article_number(c_label)
            if (target_num and c_num == target_num) or (
                c_label.lower() == article_label.lower()
            ):
                matching_subchunks.append(c)

        matching_subchunks.sort(key=lambda x: x["chunk_index"])

        if matching_subchunks:
            merged_text = _merge_article_subchunks(
                [c["content"] for c in matching_subchunks]
            )
            first_chunk = matching_subchunks[0]
            if target_num and document_id in docs_map:
                raw_extracted = _extract_article_directly_from_fulltext(
                    docs_map[document_id].get("content", ""), target_num
                )
                if len(raw_extracted) > len(merged_text) + 40:
                    merged_text = raw_extracted
            return merged_text, first_chunk["chunk_id"], first_chunk["chunk_index"]

        if target_num and document_id in docs_map:
            raw_extracted = _extract_article_directly_from_fulltext(
                docs_map[document_id].get("content", ""), target_num
            )
            if raw_extracted:
                doc_chunks = [c for c in all_chunks if c["document_id"] == document_id]
                rep_cid = doc_chunks[0]["chunk_id"] if doc_chunks else None
                return raw_extracted, rep_cid, 0

        return "", "", 0

    def searchDocuments(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        query_vector = self.aiService.embed_query(query)
        candidate_k = max(25, (top_k or settings.RAG_TOP_K) * 5)
        return self.vectorDB.search(query_vector, top_k=candidate_k)

    def getRelevantDocs(
        self, db: Any, raw_hits: list[dict[str, Any]], query: str = ""
    ) -> list[dict[str, Any]]:
        parsed = parse_legal_query(query)
        target_articles: list[str] = parsed["target_articles"]
        doc_hint: str = parsed["doc_hint"]
        q_core: str = parsed["topic_core"]
        q_tokens: list[str] = parsed["topic_tokens"]
        q_bigrams: list[str] = parsed["topic_bigrams"]
        tail_entity: str = parsed["tail_entity"]

        docs_map, all_chunks = self._load_all_docs_and_chunks(db)
        if not docs_map:
            return []

        doc_bonus_map: dict[str, float] = {}
        display_title_map: dict[str, str] = {}
        for doc_id, d_info in docs_map.items():
            doc_bonus_map[doc_id] = _score_document_hint_match(
                d_info["title"], d_info["document_type"], d_info["content"], doc_hint
            )
            display_title_map[doc_id] = format_law_title_for_citation(
                d_info["title"], d_info["content"]
            )

        # NHÁNH A: NGƯỜI DÙNG HỎI ĐÍCH DANH SỐ ĐIỀU (VD: "ĐIỀU 15", "ĐIỀU 40", "KHOẢN 1 ĐIỀU 15")
        if target_articles:
            exact_results: list[dict[str, Any]] = []
            for art_num in target_articles:
                target_label = f"Điều {art_num}"
                for doc_id, d_info in docs_map.items():
                    full_art_text, rep_chunk_id, first_idx = self._reconstruct_full_article(
                        document_id=doc_id,
                        article_label=target_label,
                        all_chunks=all_chunks,
                        docs_map=docs_map,
                    )
                    if not full_art_text:
                        continue

                    doc_bonus = doc_bonus_map.get(doc_id, 0.0)
                    raw_score = 0.90 + doc_bonus

                    if q_tokens:
                        c_norm = _norm_for_match(full_art_text)
                        tok_hits = sum(1 for t in q_tokens if f" {t} " in f" {c_norm} ")
                        raw_score += 0.08 * (tok_hits / len(q_tokens))

                    focused_excerpt, matched_clauses, matched_points = (
                        _extract_focus_content_from_chunk_with_meta(query, full_art_text)
                    )
                    canonical_label = extract_article_heading(full_art_text, first_idx)
                    citation_label = build_citation_label(
                        canonical_label, matched_clauses, matched_points
                    )

                    exact_results.append(
                        {
                            "rank": 1,
                            "chunk_id": rep_chunk_id,
                            "document_id": doc_id,
                            "title": d_info["title"],
                            "display_title": display_title_map[doc_id],
                            "document_type": d_info["document_type"],
                            "issuing_agency": d_info["issuing_agency"],
                            "issue_date": d_info["issue_date"],
                            "article": canonical_label,
                            "citation_label": citation_label,
                            "matched_clauses": matched_clauses,
                            "matched_points": matched_points,
                            "chunk_index": first_idx,
                            "content": focused_excerpt,
                            "full_content": full_art_text,
                            "raw_score": raw_score,
                            "score": round(min(0.9999, max(0.1, raw_score)), 4),
                        }
                    )

            if exact_results:
                exact_results.sort(key=lambda x: x["raw_score"], reverse=True)
                top_raw = exact_results[0]["raw_score"]
                filtered_exact = [
                    r for r in exact_results if r["raw_score"] >= top_raw - 0.15
                ][: max(len(target_articles), 1)]
                for idx, item in enumerate(filtered_exact, start=1):
                    item["rank"] = idx
                    item.pop("raw_score", None)
                return filtered_exact

        # NHÁNH B: NGƯỜI DÙNG HỎI THEO CHỦ ĐỀ / KHÁI NIỆM / QUY ĐỊNH CỤ THỂ
        vector_score_by_chunk: dict[str, float] = {}
        for hit in raw_hits:
            cid = hit.get("chunk_id")
            if cid:
                vector_score_by_chunk[cid] = max(
                    vector_score_by_chunk.get(cid, 0.0), float(hit.get("score", 0.0))
                )

        candidate_by_key: dict[tuple[str, str], dict[str, Any]] = {}

        for c in all_chunks:
            cid = c["chunk_id"]
            doc_id = c["document_id"]
            c_text = c["content"]
            if not c_text or doc_id not in docs_map:
                continue

            doc_bonus = doc_bonus_map.get(doc_id, 0.0)
            if doc_hint and doc_bonus < -0.2:
                continue

            base_vec_score = vector_score_by_chunk.get(cid, 0.0)
            c_norm = _norm_for_match(c_text)
            first_line_norm = _norm_for_match(c_text.split("\n", 1)[0])

            # Nếu câu hỏi có cụm danh từ thực thể đích sau chữ "của" (vd: "tên khoa học của thông nước"),
            # kiểm tra xem cụm thực thể đích đó có xuất hiện trong đoạn văn bản không
            has_tail_entity = True
            if tail_entity and len(tail_entity.split()) >= 2:
                has_tail_entity = f" {tail_entity} " in f" {c_norm} "

            # Đếm số cụm từ ghép 2 âm tiết (bigrams) khớp chính xác
            matched_bgs = sum(
                1 for bg in q_bigrams if f" {bg} " in f" {c_norm} "
            )
            bg_ratio = (matched_bgs / len(q_bigrams)) if q_bigrams else 0.0

            lexical_bonus = 0.0
            if q_core and len(q_core) >= 4:
                if q_core in first_line_norm:
                    lexical_bonus += 0.48
                if re.search(rf"\b\d{{1,3}}\s+{re.escape(q_core)}\s+(?:là|bao gồm|gồm)\b", c_norm) or (
                    f"{q_core} là " in c_norm or f"{q_core} bao gồm" in c_norm
                ):
                    lexical_bonus += 0.46
                elif q_core in c_norm:
                    lexical_bonus += 0.28

            if q_bigrams:
                lexical_bonus += 0.24 * bg_ratio

            if q_tokens:
                matched_toks = sum(1 for t in q_tokens if f" {t} " in f" {c_norm} ")
                tok_ratio = matched_toks / len(q_tokens)
                # Chỉ cộng điểm từ đơn nếu có ít nhất 1 cụm từ ghép 2 âm tiết khớp (tránh cộng điểm nhầm các âm tiết rời rạc như 'nhà nước' + 'thông báo')
                if (not q_bigrams or matched_bgs > 0) and tok_ratio >= 0.5:
                    lexical_bonus += 0.14 * tok_ratio

            # Nếu câu hỏi có cụm thực thể đích (vd: "thông nước") mà đoạn văn hoàn toàn không chứa cụm đó -> giảm điểm mạnh
            if tail_entity and len(tail_entity.split()) >= 2 and not has_tail_entity:
                base_vec_score *= 0.45
                lexical_bonus = 0.0

            if base_vec_score <= 0.0 and lexical_bonus < 0.18:
                continue

            doc_tie_bonus = 0.08 if doc_bonus > 0 else 0.0
            raw_combined = base_vec_score + lexical_bonus + doc_tie_bonus
            combined_score = round(min(0.9999, max(0.05, raw_combined)), 4)

            art_label = extract_article_heading(c_text, c["chunk_index"])
            # Nếu đoạn văn nằm trong Phụ lục / Danh mục thì phân biệt theo chunk_id để không gộp nhầm vào Điều 52
            is_appendix_chunk = bool(
                re.search(r"(?m)^(?:PHỤ\s+LỤC|Phụ\s+lục|DANH\s+MỤC)\b", c_text)
            )
            group_key = (doc_id, cid if is_appendix_chunk else art_label)

            if (
                group_key not in candidate_by_key
                or raw_combined > candidate_by_key[group_key]["raw_score"]
            ):
                candidate_by_key[group_key] = {
                    "chunk_id": cid,
                    "document_id": doc_id,
                    "article": art_label,
                    "chunk_index": c["chunk_index"],
                    "raw_chunk_content": c_text,
                    "raw_score": raw_combined,
                    "lexical_bonus": lexical_bonus,
                    "matched_bgs": matched_bgs,
                    "score": combined_score,
                }

        if not candidate_by_key:
            return []

        ranked_candidates = sorted(
            candidate_by_key.values(), key=lambda x: x["raw_score"], reverse=True
        )

        top_cand = ranked_candidates[0]
        top_raw = top_cand["raw_score"]

        # Ngưỡng bảo vệ chống trả lời nhầm Điều luật không liên quan khi câu hỏi nằm ngoài kho văn bản
        if q_bigrams and top_cand["matched_bgs"] == 0 and top_raw < 0.55:
            return []
        if top_raw < 0.28:
            return []

        # Chỉ giữ lại ứng viên thực sự sát với ứng viên số 1 (tránh gắn kèm các điều khác không liên quan)
        cutoff = max(0.32, top_raw * 0.80)
        selected_candidates = [
            item for item in ranked_candidates if item["raw_score"] >= cutoff
        ][:2]

        enriched: list[dict[str, Any]] = []
        for idx, cand in enumerate(selected_candidates, start=1):
            doc_id = cand["document_id"]
            art_label = cand["article"]
            d_info = docs_map[doc_id]
            raw_chunk_text = cand["raw_chunk_content"]

            full_art_text, rep_cid, first_idx = self._reconstruct_full_article(
                document_id=doc_id,
                article_label=art_label,
                all_chunks=all_chunks,
                docs_map=docs_map,
            )

            # Kiểm tra xem nội dung khớp câu hỏi nằm trong full_art_text hay nằm riêng trong raw_chunk_text
            # (trường hợp CSDL cũ gộp Phụ lục vào cuối Điều 52)
            source_text_for_focus = full_art_text or raw_chunk_text
            if full_art_text and raw_chunk_text and q_bigrams:
                full_norm = _norm_for_match(full_art_text)
                raw_norm = _norm_for_match(raw_chunk_text)
                full_bg_hits = sum(1 for bg in q_bigrams if f" {bg} " in f" {full_norm} ")
                raw_bg_hits = sum(1 for bg in q_bigrams if f" {bg} " in f" {raw_norm} ")
                if raw_bg_hits > full_bg_hits:
                    source_text_for_focus = raw_chunk_text
                    rep_cid = cand["chunk_id"]
                    first_idx = cand["chunk_index"]

            focused_excerpt, matched_clauses, matched_points = (
                _extract_focus_content_from_chunk_with_meta(query, source_text_for_focus)
            )
            citation_label = build_citation_label(
                art_label, matched_clauses, matched_points
            )

            enriched.append(
                {
                    "rank": idx,
                    "chunk_id": rep_cid or cand["chunk_id"],
                    "document_id": doc_id,
                    "title": d_info["title"],
                    "display_title": display_title_map[doc_id],
                    "document_type": d_info["document_type"],
                    "issuing_agency": d_info["issuing_agency"],
                    "issue_date": d_info["issue_date"],
                    "article": art_label,
                    "citation_label": citation_label,
                    "matched_clauses": matched_clauses,
                    "matched_points": matched_points,
                    "chunk_index": first_idx,
                    "content": focused_excerpt,
                    "full_content": source_text_for_focus,
                    "score": cand["score"],
                }
            )

        return enriched

    def buildContext(self, retrieved_chunks: list[dict[str, Any]]) -> str:
        if not retrieved_chunks:
            return "Không có văn bản pháp luật nào được tìm thấy trong cơ sở dữ liệu."

        # Chỉ đưa đoạn nguồn sát nhất (và nguồn #2 nếu điểm tương đồng gần ngang bằng nguồn #1)
        # để mô hình AI tập trung trả lời đúng Điều/Khoản được hỏi, không lan man sang Điều khác.
        top_score = float(retrieved_chunks[0].get("score", 0.0))
        focused_list = [retrieved_chunks[0]]
        if (
            len(retrieved_chunks) > 1
            and float(retrieved_chunks[1].get("score", 0.0)) >= top_score - 0.04
        ):
            focused_list.append(retrieved_chunks[1])

        blocks: list[str] = []
        for item in focused_list:
            disp_title = item.get("display_title") or item["title"]
            cit_label = item.get("citation_label") or item["article"]
            header = (
                f"--- [Nguồn #{item['rank']}] Văn bản: {disp_title} | "
                f"Vị trí: {cit_label} (Độ tương đồng: {item['score']:.2f}) ---"
            )
            blocks.append(f"{header}\n{item['content']}")
        return "\n\n".join(blocks)

    def answerQuestion(
        self, db: Any, user_id: str, question_content: str
    ) -> dict[str, Any]:
        question_obj = Question(
            question_id=str(uuid.uuid4()),
            user_id=user_id,
            content=question_content.strip(),
            status="PROCESSING",
        )
        db.add(question_obj)
        db.commit()

        try:
            raw_hits = self.searchDocuments(
                question_obj.content, top_k=settings.RAG_TOP_K
            )
            retrieved_chunks = self.getRelevantDocs(
                db, raw_hits, query=question_obj.content
            )

            context_text = self.buildContext(retrieved_chunks)

            answer_text, model_used = self.aiService.generate_answer(
                question=question_obj.content,
                context_text=context_text,
                retrieved_chunks=retrieved_chunks,
            )

            # Nếu chạy chế độ local-rag, đảm bảo hiển thị đúng câu mở đầu "Theo quy định tại Khoản X, Điều Y của Luật Z:"
            # kèm đúng phần nội dung trọng tâm đã lọc (không chép kèm các khoản không liên quan)
            if "(local-rag)" in (model_used or "") and retrieved_chunks:
                top_item = retrieved_chunks[0]
                disp_title = top_item.get("display_title") or top_item["title"]
                cit_label = top_item.get("citation_label") or top_item["article"]
                answer_text = (
                    f"Theo quy định tại {cit_label} của {disp_title}:\n\n"
                    f"{top_item['content']}"
                )

            answer_obj = Answer(
                answer_id=str(uuid.uuid4()),
                question_id=question_obj.question_id,
                content=answer_text,
                model_name=model_used,
            )
            db.add(answer_obj)
            db.flush()

            sources_response: list[dict[str, Any]] = []
            seen_article_keys: set[tuple[str, str]] = set()

            for item in retrieved_chunks:
                art_key = (item["document_id"], item["article"])
                if art_key in seen_article_keys:
                    continue
                seen_article_keys.add(art_key)

                ans_source = AnswerSource(
                    answer_id=answer_obj.answer_id,
                    document_id=item["document_id"],
                    chunk_id=item["chunk_id"],
                    rank_no=len(sources_response) + 1,
                    score=item["score"],
                )
                db.add(ans_source)

                src_dict = map_source_to_dict(
                    document_id=item["document_id"],
                    title=item.get("display_title") or item["title"],
                    chunk_id=item["chunk_id"],
                    chunk_content=item["content"],
                    chunk_index=item["chunk_index"],
                    score=item["score"],
                    rank_no=len(sources_response) + 1,
                )
                if item.get("citation_label"):
                    src_dict["article"] = item["citation_label"]
                sources_response.append(src_dict)

            history_obj = ChatHistory(
                history_id=str(uuid.uuid4()),
                user_id=user_id,
                question_id=question_obj.question_id,
                answer_id=answer_obj.answer_id,
            )
            db.add(history_obj)

            question_obj.status = "COMPLETED"
            db.add(question_obj)
            db.commit()

            return map_conversation_to_dict(
                history_id=history_obj.history_id,
                question=question_obj,
                answer=answer_obj,
                sources=sources_response,
            )

        except Exception as exc:
            db.rollback()
            try:
                question_obj.status = "FAILED"
                db.add(question_obj)
                db.commit()
            except Exception:
                db.rollback()
            raise RuntimeError(str(exc)) from exc


rag_service = RAGService()