"""Các tác vụ AI dùng Claude API: bóc kịch bản đối thủ, viết lại cho sản phẩm nhà, ghép cảnh."""

import base64
import json

import anthropic

from .store import get_settings

MODEL = "claude-opus-5"

BEAT_SCHEMA = {
    "type": "object",
    "properties": {
        "shot": {"type": "string", "description": "Mô tả cảnh quay: quay gì, góc máy, hành động"},
        "voice": {"type": "string", "description": "Lời thoại/giọng đọc của cảnh, rỗng nếu không có"},
        "text": {"type": "string", "description": "Chữ hiện trên màn hình, rỗng nếu không có"},
        "text_pos": {"type": "string", "enum": ["top", "center", "bottom"]},
        "duration": {"type": "number", "description": "Độ dài cảnh (giây)"},
    },
    "required": ["shot", "voice", "text", "text_pos", "duration"],
    "additionalProperties": False,
}

SCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "hook_type": {"type": "string"},
        "why_it_works": {"type": "string"},
        "beats": {"type": "array", "items": BEAT_SCHEMA},
        "caption": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "summary", "hook_type", "why_it_works", "beats", "caption", "hashtags"],
    "additionalProperties": False,
}

REWRITE_SCHEMA = {
    "type": "object",
    "properties": {
        **SCRIPT_SCHEMA["properties"],
        "alt_hooks": {
            "type": "array",
            "description": "Các phương án hook khác cho cảnh đầu",
            "items": {
                "type": "object",
                "properties": {"text": {"type": "string"}, "voice": {"type": "string"}},
                "required": ["text", "voice"],
                "additionalProperties": False,
            },
        },
        "needs_info": {
            "type": "array",
            "description": "Thông tin còn thiếu mà người bán cần bổ sung (giá, khổ, bình luận thật...)",
            "items": {"type": "string"},
        },
    },
    "required": SCRIPT_SCHEMA["required"] + ["alt_hooks", "needs_info"],
    "additionalProperties": False,
}

SYSTEM = (
    "Bạn là chuyên gia nội dung video bán hàng TikTok Shop Việt Nam, làm việc cho một shop tự quay "
    "video sản phẩm. Viết tiếng Việt tự nhiên, ngắn gọn, đúng giọng người bán hàng trên TikTok."
)


class AIError(RuntimeError):
    pass


def _client():
    key = get_settings().get("anthropic_api_key") or None
    try:
        return anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
    except anthropic.AnthropicError as err:
        raise AIError("Chưa có Anthropic API key. Nhập key trong mục Cài đặt.") from err


def _image(path):
    with open(path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


def _ask(content, schema):
    """Gọi Claude với đầu ra JSON theo schema, trả về dict."""
    client = _client()
    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            thinking={"type": "adaptive"},
            system=SYSTEM,
            output_config={"format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": content}],
        )
    except anthropic.AuthenticationError as err:
        raise AIError("Anthropic API key không hợp lệ. Kiểm tra lại trong Cài đặt.") from err
    except anthropic.RateLimitError as err:
        raise AIError("Claude API đang giới hạn tần suất, thử lại sau ít phút.") from err
    except anthropic.APIStatusError as err:
        raise AIError(f"Claude API lỗi {err.status_code}: {err.message}") from err
    except anthropic.APIConnectionError as err:
        raise AIError("Không kết nối được Claude API, kiểm tra mạng.") from err
    if response.stop_reason == "refusal":
        raise AIError("Claude từ chối xử lý yêu cầu này.")
    if response.stop_reason == "max_tokens":
        raise AIError("Kết quả quá dài, bị cắt giữa chừng. Thử lại với video ngắn hơn.")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        return json.loads(text)
    except json.JSONDecodeError as err:
        raise AIError("Claude trả về dữ liệu không đọc được.") from err


def transcribe(wav_path):
    """Chuyển giọng nói thành chữ bằng faster-whisper nếu đã cài; trả về None nếu không có."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(wav_path, language="vi")
    return "\n".join(f"[{s.start:.1f}s–{s.end:.1f}s] {s.text.strip()}" for s in segments)


def analyze_competitor(frames, scenes, duration, transcript, notes=""):
    """Bóc kịch bản từ video đối thủ: khung hình theo thời gian + lời thoại (nếu có)."""
    content = [{"type": "text", "text": (
        f"Đây là một video TikTok bán hàng của đối thủ, dài {duration:.1f} giây.\n"
        f"Các mốc chuyển cảnh (giây): {', '.join(f'{t:.1f}' for t in scenes) or 'không phát hiện'}.\n"
        f"Lời thoại tự động (có thể sai chính tả):\n{transcript or '(không có hoặc chưa chuyển thành chữ)'}\n"
        f"Ghi chú của người dùng: {notes or '(không có)'}\n\n"
        "Khung hình theo thời gian:")}]
    for t, path in frames:
        content.append({"type": "text", "text": f"Giây {t:.1f}:"})
        content.append(_image(path))
    content.append({"type": "text", "text": (
        "Hãy bóc tách kịch bản của video này thành các cảnh (beats) theo đúng thứ tự và nhịp cắt thật. "
        "Với mỗi cảnh: mô tả cảnh quay đủ để người khác quay lại được (quay gì, góc máy, hành động), "
        "lời thoại đúng như trong video (sửa lỗi chính tả rõ ràng của bản chuyển chữ), chữ trên màn hình "
        "đọc được từ khung hình và vị trí của nó, độ dài cảnh. Không bịa lời thoại hay chữ không có trong video. "
        "Nêu kiểu hook, tóm tắt, và vì sao video này hiệu quả. Caption và hashtags: đoán theo nội dung "
        "nếu không thấy.")})
    return _ask(content, SCRIPT_SCHEMA)


def rewrite_script(script, product):
    """Giữ cấu trúc kịch bản, viết lại lời và chữ cho sản phẩm của shop."""
    facts = "\n".join(f"- {k}: {v}" for k, v in product.items() if v)
    content = [{"type": "text", "text": (
        "Kịch bản gốc (JSON):\n" + json.dumps(script, ensure_ascii=False, indent=1) + "\n\n"
        "Thông tin sản phẩm của shop:\n" + (facts or "(chưa có)") + "\n\n"
        "Viết lại kịch bản này cho sản phẩm của shop:\n"
        "- Giữ cấu trúc: kiểu hook, số cảnh, nhịp và độ dài từng cảnh, vị trí CTA. Điều chỉnh mô tả cảnh "
        "quay cho phù hợp sản phẩm của shop.\n"
        "- Viết lời thoại mới, không chép nguyên văn đối thủ. Mỗi câu lời thoại đọc vừa độ dài cảnh "
        "(khoảng 4 tiếng mỗi giây). Chữ trên màn hình ngắn, tối đa khoảng 8 từ mỗi dòng.\n"
        "- Chỉ dùng thông tin sản phẩm đã cho. Không bịa giá, khuyến mãi, số liệu, đánh giá hay bình luận "
        "của khách; thiếu thông tin nào thì bỏ qua và liệt kê vào needs_info.\n"
        "- Không hứa công dụng, tài lộc hay sức khoẻ. Cảnh cuối có CTA bấm giỏ hàng.\n"
        "- Đưa thêm 3 phương án hook khác cho cảnh đầu trong alt_hooks.")}]
    return _ask(content, REWRITE_SCHEMA)


def match_clips(beats, shots):
    """Chọn đoạn source phù hợp cho từng cảnh. shots: [{id, label, thumb, start, end}]."""
    content = [{"type": "text", "text": "Các đoạn video nguồn shop đã quay (mỗi đoạn một ảnh giữa đoạn):"}]
    for shot in shots:
        content.append({"type": "text", "text": f"{shot['id']}: {shot['label']}"})
        content.append(_image(shot["thumb"]))
    lines = "\n".join(f"Cảnh {i}: {b.get('shot') or '(không mô tả)'} — lời: {b.get('voice') or '-'}"
                      for i, b in enumerate(beats))
    content.append({"type": "text", "text": (
        f"Kịch bản cần dựng:\n{lines}\n\n"
        "Chọn cho mỗi cảnh một đoạn nguồn phù hợp nhất với mô tả. Một đoạn có thể dùng lại nếu không có "
        "lựa chọn khác, nhưng ưu tiên đa dạng. Nếu không có đoạn nào hợp, chọn 'none' và mô tả cảnh cần "
        "quay bổ sung.")})
    ids = [s["id"] for s in shots] + ["none"]
    schema = {
        "type": "object",
        "properties": {
            "matches": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "beat": {"type": "integer"},
                    "shot_id": {"type": "string", "enum": ids},
                    "reason": {"type": "string"},
                },
                "required": ["beat", "shot_id", "reason"],
                "additionalProperties": False,
            }},
            "missing": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["matches", "missing"],
        "additionalProperties": False,
    }
    return _ask(content, schema)
