"""Kiểm thử nhanh các phần dễ hỏng của app (không cần ffmpeg, mạng hay API key).

Chạy:  python -m unittest discover -s tests -v
"""

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp()
# Phải đặt trước khi import app để không đụng dữ liệu thật
os.environ["VIDEO_APP_DATA"] = os.path.join(_TMP, "data")
os.environ["VIDEO_APP_CONFIG"] = os.path.join(_TMP, "config")
sys.path.insert(0, ROOT)

import make_videos  # noqa: E402
from app import ai, assemble, batch, diag, docs, fonts, jobs, library, media, store, tts  # noqa: E402


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "tools", f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Voice(unittest.TestCase):
    def test_speaker_labels_and_quotes_are_not_read_aloud(self):
        self.assertEqual(assemble.speakable('Khách: "Em ơi, có đủ 365 tờ không?"'), "Em ơi, có đủ 365 tờ không?")
        self.assertEqual(assemble.speakable('Shop: "Dạ đủ." Khách: "Lấy hai!"'), "Dạ đủ. Lấy hai!")

    def test_placeholders_block_render(self):
        with self.assertRaises(ValueError) as ctx:
            assemble.check_placeholders([{"voice": "Cỡ [kiểm tra], nẹp [kiểm tra].", "text": ""}], True)
        self.assertIn("Cảnh 1", str(ctx.exception))
        assemble.check_placeholders([{"voice": "Cỡ 30 nhân 40.", "text": "44K"}], True)
        # Tắt giọng đọc thì lời đọc không bị đọc lên nên không chặn, nhưng chữ trên màn hình vẫn bị chặn
        assemble.check_placeholders([{"voice": "[kiểm tra]", "text": ""}], False)
        with self.assertRaises(ValueError):
            assemble.check_placeholders([{"voice": "", "text": "[giá giỏ]"}], False)

    def test_subtitle_chunks_are_short(self):
        chunks = assemble.split_subtitle("Mẫu này em còn ít, cỡ lớn đã hết rồi. Anh chị bấm giỏ hàng giữ một cuốn trước nha!")
        self.assertTrue(all(len(c.split()) <= 6 for c in chunks))
        self.assertEqual(" ".join(chunks).split(), "Mẫu này em còn ít, cỡ lớn đã hết rồi. Anh chị bấm giỏ hàng giữ một cuốn trước nha!".split())


class Clips(unittest.TestCase):
    source = {"path": "x.mp4", "info": {"duration": 40.0}}

    def test_extension_never_leaves_its_scene(self):
        clip = {"start": 5.0, "end": 8.0, "scene_start": 3.0, "scene_end": 9.0}
        out = assemble.fit_clip(clip, self.source, 10.0)
        self.assertGreaterEqual(out["start"], 3.0)
        self.assertLessEqual(out["end"], 9.0)
        self.assertLess(out["speed"], 1.0)  # cảnh gốc chỉ 6s nên phải quay chậm cho đủ 10s
        self.assertGreater(out["speed"], 0.49)

    def test_long_enough_clip_is_trimmed_not_slowed(self):
        out = assemble.fit_clip({"start": 2.0, "end": 12.0, "scene_start": 2.0, "scene_end": 20.0}, self.source, 8.0)
        self.assertEqual(round(out["end"] - out["start"], 3), 8.0)
        self.assertNotIn("speed", out)
        # né vài khung hình ngay chỗ cắt cảnh, nơi hình hay bị nhoè
        self.assertGreater(out["start"], 2.0)
        self.assertEqual(round(out["start"], 3), round(2.0 + assemble.EDGE, 3))

    def test_a_tight_scene_is_used_whole_instead_of_losing_frames(self):
        out = assemble.fit_clip({"start": 3.0, "end": 6.0, "scene_start": 3.0, "scene_end": 6.0}, self.source, 3.0)
        self.assertEqual((out["start"], out["end"]), (3.0, 6.0))

    def test_short_scene_gets_freeze_padding_after_max_slowdown(self):
        out = assemble.fit_clip({"start": 0.0, "end": 2.0, "scene_start": 0.0, "scene_end": 2.0}, self.source, 10.0)
        self.assertEqual(out["speed"], assemble.MIN_SPEED)
        self.assertGreater(out["pad"], 0)


class Matching(unittest.TestCase):
    def shots(self, n):
        return [{"id": f"s_{i}", "source_id": "s", "start": i * 3.0, "end": i * 3.0 + 3} for i in range(n)]

    def test_simple_match_uses_different_shots_and_balances_usage(self):
        beats = [{}] * 4
        used = {}
        first = ai.simple_match(beats, self.shots(4), used)
        self.assertEqual(len({m["shot_id"] for m in first["matches"]}), 4)
        for m in first["matches"]:
            used[m["shot_id"]] = used.get(m["shot_id"], 0) + 1
        second = ai.simple_match(beats, self.shots(8), used)  # 4 đoạn mới chưa dùng được ưu tiên
        self.assertTrue(all(int(m["shot_id"].split("_")[1]) >= 4 for m in second["matches"]))


class Scripts(unittest.TestCase):
    def setUp(self):  # mỗi test một thư viện kịch bản trống
        shutil.rmtree(os.path.join(store.DATA_DIR, "scripts"), ignore_errors=True)
        os.makedirs(os.path.join(store.DATA_DIR, "scripts"))
        if os.path.exists(store.IMPORTED_FILE):
            os.remove(store.IMPORTED_FILE)

    def test_weekly_scripts_load_once_and_deleted_ones_stay_deleted(self):
        added = library.seed_weekly()
        self.assertEqual(added, 40)
        self.assertEqual(library.seed_weekly(), 0)
        victim = next(s for s in store.scripts.list() if s.get("code") == "L1")
        store.scripts.delete(victim["id"])
        self.assertEqual(library.seed_weekly(), 0)
        self.assertFalse(any(s.get("code") == "L1" for s in store.scripts.list()))

    def test_weekly_scripts_are_listed_in_plan_order(self):
        library.seed_templates()
        library.seed_weekly()
        listed = store.scripts.list()
        self.assertEqual([s["code"] for s in listed[:4]], ["L1", "L2", "L3", "L4"])  # mới nhất lên đầu = đúng thứ tự kế hoạch
        self.assertEqual({s["origin"] for s in listed[-3:]}, {"template"})

    def test_blank_detection_uses_voice_and_text_only(self):
        script = {"beats": [{"voice": "Cỡ [kiểm tra].", "text": "", "shot": "[kiểm tra cỡ]"},
                            {"voice": "ok", "text": "[giá giỏ]"}]}
        self.assertEqual(batch.script_blanks(script), ["[kiểm tra]", "[giá giỏ]"])
        self.assertEqual(batch.script_blanks({"beats": [{"voice": "ok", "text": "", "shot": "[kiểm tra cỡ]"}]}), [])


class DocParser(unittest.TestCase):
    XML = """<doc>
      <paragraph heading='2'><text>3. Lịch bloc (1 video)</text></paragraph>
      <paragraph heading='3'><text>L1 · Đếm ngược Tết</text></paragraph>
      <paragraph><text>NS #1 · Bloc 14,5×20,5 · Bối cảnh: bàn làm việc · Mở đầu: con số → Chốt: khan hiếm</text></paragraph>
      <table>
        <row><cell><paragraph><text>Mốc</text></paragraph></cell><cell><paragraph><text>Phần</text></paragraph></cell>
             <cell><paragraph><text>Lời thoại</text></paragraph></cell><cell><paragraph><text>Hình ảnh</text></paragraph></cell></row>
        <row><cell><paragraph><text>0–3s</text></paragraph></cell><cell><paragraph><text>Mở đầu</text></paragraph></cell>
             <cell><paragraph><text>Lịch bloc 2027, 44 nghìn!</text></paragraph></cell>
             <cell><paragraph><text>Giơ lịch. Chữ to "44K" hiện giữa màn hình</text></paragraph></cell></row>
        <row><cell><paragraph><text>3–10s</text></paragraph></cell><cell><paragraph><text>Chốt</text></paragraph></cell>
             <cell><paragraph><text>Cỡ [kiểm tra] đủ 365 tờ.</text></paragraph></cell>
             <cell><paragraph><text>Chỉ giỏ [kiểm tra tồn kho]</text></paragraph></cell></row>
      </table></doc>"""

    def test_parses_script_beats_text_and_notes(self):
        tool = load_tool("parse_ke_hoach_doc")
        (script,) = tool.build(tool.parse_doc(self.XML), "tuan-test")
        self.assertEqual((script["code"], script["channel"], script["product"]), ("L1", "NS", "Bloc 14,5×20,5"))
        self.assertEqual([b["duration"] for b in script["beats"]], [3.0, 7.0])
        self.assertEqual(script["beats"][0]["text"], "44K")
        self.assertEqual(script["beats"][0]["text_pos"], "top")
        self.assertEqual(script["beats"][-1]["text_pos"], "center")
        self.assertTrue(any("[kiểm tra]" in n for n in script["needs_info"]))      # ô trong lời đọc
        self.assertTrue(any("tồn kho" in n for n in script["needs_info"]))         # ghi chú khi quay


class Environment(unittest.TestCase):
    def test_missing_ffmpeg_filters_are_reported(self):
        class Out:
            stdout = " T.. boxblur  V->V  x\n ... concat  V->N  x\n"
        real_run, real_cache = make_videos.subprocess.run, make_videos._FFMPEG_PROBLEMS
        try:
            make_videos._FFMPEG_PROBLEMS = None
            make_videos.subprocess.run = lambda *a, **k: Out()
            problems = make_videos.ffmpeg_problems()
        finally:
            make_videos.subprocess.run, make_videos._FFMPEG_PROBLEMS = real_run, real_cache
        self.assertTrue(any(p.startswith("ass:") for p in problems))
        self.assertFalse(any(p.startswith("boxblur:") for p in problems))

    def test_settings_live_outside_the_served_data_dir(self):
        store.save_settings({"anthropic_api_key": "sk-ant-test"})
        self.assertFalse(os.path.abspath(store.SETTINGS_FILE).startswith(os.path.abspath(store.DATA_DIR) + os.sep))

    def test_web_server_hides_data_files_and_blocks_cross_site_writes(self):
        try:
            from starlette.testclient import TestClient
        except Exception:  # thiếu httpx
            self.skipTest("cần httpx để thử máy chủ web: pip install httpx")
        from app.server import app
        store.save_settings({"anthropic_api_key": "sk-ant-test"})
        os.makedirs(store.DATA_DIR, exist_ok=True)
        for name, mode, body in (("settings.json", "w", "{}"), ("imported_keys.json", "w", "{}"), ("ok.jpg", "wb", b"jpg")):
            with open(os.path.join(store.DATA_DIR, name), mode) as f:
                f.write(body)
        with TestClient(app) as client:
            self.assertEqual(client.get("/data/settings.json").status_code, 404)
            self.assertEqual(client.get("/data/imported_keys.json").status_code, 404)
            self.assertEqual(client.get("/data/ok.jpg").status_code, 200)
            self.assertNotIn("sk-ant-test", client.get("/api/state").text)
            evil = client.put("/api/settings", json={"shop_name": "x"}, headers={"origin": "http://evil.example"})
            self.assertEqual(evil.status_code, 403)
            ok = client.put("/api/settings", json={"shop_name": "x"}, headers={"origin": "http://testserver"})
            self.assertEqual(ok.status_code, 200)


def make_docx(path):
    import zipfile
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    def p(text, style=None):
        ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'

    rows = [["Mốc", "Phần", "Lời thoại", "Hình ảnh"], ["0–3s", "Mở đầu", "Chào anh chị", "Cầm lịch"]]
    table = "<w:tbl>" + "".join("<w:tr>" + "".join(f"<w:tc>{p(c)}</w:tc>" for c in r) + "</w:tr>" for r in rows) + "</w:tbl>"
    xml = f'<?xml version="1.0"?><w:document xmlns:w="{w}"><w:body>{p("M1 · Lịch", "Heading3")}{p("NS #1")}{table}</w:body></w:document>'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml)


class Documents(unittest.TestCase):
    def test_docx_headings_and_tables_become_text(self):
        path = os.path.join(_TMP, "t.docx")
        make_docx(path)
        doc = docs.load_file(path)
        self.assertEqual(doc.kind, "text")
        self.assertIn("### M1 · Lịch", doc.text)
        self.assertIn("0–3s | Mở đầu | Chào anh chị | Cầm lịch", doc.text)

    def test_html_tables_and_headings(self):
        text = docs.html_text("<h3>L1 · A</h3><table><tr><td>0–3s</td><td>Mở đầu</td></tr></table><script>x()</script>")
        self.assertIn("### L1 · A", text)
        self.assertIn("0–3s", text)
        self.assertNotIn("x()", text)

    def test_format_is_detected_by_content_not_extension(self):
        self.assertEqual(docs.from_bytes(b"%PDF-1.7 ...").kind, "pdf")
        self.assertEqual(docs.from_bytes("<html><body><p>Xin chào</p></body></html>".encode()).text, "Xin chào")
        with self.assertRaises(docs.DocError):
            docs.from_bytes(b"")

    def test_google_docs_links_become_text_exports(self):
        self.assertEqual(docs.export_url("https://docs.google.com/document/d/AbC-123/edit?usp=sharing"),
                         "https://docs.google.com/document/d/AbC-123/export?format=txt")
        self.assertEqual(docs.export_url("https://example.com/a"), "https://example.com/a")

    def test_internal_addresses_are_refused(self):
        os.environ.pop("VIDEO_APP_ALLOW_LOCAL_URLS", None)
        for url in ("http://127.0.0.1:8000/x", "http://localhost/x", "ftp://example.com/x", "file:///etc/passwd"):
            with self.assertRaises(docs.DocError):
                docs.fetch_url(url)


class Import(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(os.path.join(store.DATA_DIR, "scripts"), ignore_errors=True)
        os.makedirs(os.path.join(store.DATA_DIR, "scripts"))
        self.real = ai.extract_scripts
        self.calls = 0

        def fake(doc):
            self.calls += 1
            return [{"code": "M1", "title": "Lịch quăn mép", "channel": "NS", "product": "Lịch laminate", "summary": "", "hook_type": "",
                     "caption": "", "hashtags": [], "beats": [
                         {"part": "Mở đầu", "shot": "Cầm lịch", "voice": "Lịch quăn mép!", "text": "44K", "duration": 3},
                         {"part": "Thông số", "shot": "Đo", "voice": "Cỡ [kiểm tra].", "text": "", "duration": 0},
                         {"part": "Chốt", "shot": "Chỉ giỏ", "voice": "Bấm giỏ hàng nha!", "text": "", "duration": 4}]}]
        ai.extract_scripts = fake
        os.environ["ANTHROPIC_API_KEY"] = "x"

    def tearDown(self):
        ai.extract_scripts = self.real
        os.environ.pop("ANTHROPIC_API_KEY", None)

    def test_import_adds_then_updates_same_code(self):
        first = library.import_document(docs.Doc("text", "bất kỳ"))
        self.assertEqual((first["added"], first["updated"]), (1, 0))
        second = library.import_document(docs.Doc("text", "bất kỳ"))
        self.assertEqual((second["added"], second["updated"]), (0, 1))
        (script,) = store.scripts.list()
        self.assertEqual(script["title"], "M1 · Lịch quăn mép")
        self.assertEqual([b["text_pos"] for b in script["beats"]], ["top", "bottom", "center"])
        self.assertGreater(script["beats"][1]["duration"], 0)  # thiếu thời lượng thì ước lượng từ lời thoại
        self.assertTrue(any("[kiểm tra]" in n for n in script["needs_info"]))

    def test_app_json_imports_without_ai(self):
        ai.extract_scripts = lambda doc: self.fail("không được gọi AI cho file JSON")
        payload = '{"scripts": [{"title": "Thử", "beats": [{"voice": "Xin chào", "shot": "a"}]}]}'
        self.assertEqual(library.import_document(docs.Doc("text", payload))["added"], 1)

    def test_pdf_or_text_needs_an_api_key(self):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        store.save_settings({"anthropic_api_key": ""})
        with self.assertRaises(docs.DocError):
            library.import_document(docs.Doc("text", "kịch bản thường"))
        self.assertEqual(self.calls, 0)


class Adaptation(unittest.TestCase):
    """Kịch bản chỉ để tham khảo: cảnh chưa có video khớp được viết lại, cảnh đã khớp thì giữ nguyên."""

    def setUp(self):
        self.shots = [{"id": f"s_{i}", "source_id": "s", "start": i * 3.0, "end": i * 3.0 + 3, "length": 3.0, "desc": f"đoạn {i}",
                       "note": "", "thumb": "", "scene_start": 0.0, "scene_end": 30.0} for i in range(6)]
        self.beats = [{"shot": f"cảnh {i}", "voice": f"Lời gốc {i}.", "text": "", "text_pos": "top", "duration": 5, "part": ""}
                      for i in range(5)]
        self.script = {"title": "T", "product": "Lịch", "summary": ""}
        self.real = (ai.match_clips, ai.adapt_beats)
        self.adapt_calls = []

    def tearDown(self):
        ai.match_clips, ai.adapt_beats = self.real

    def matches(self, fits):
        ai.match_clips = lambda beats, shots, script, used: {
            "matches": [{"beat": i, "shot_id": "none" if f == "khong" else f"s_{i}", "fit": f, "reason": ""} for i, f in enumerate(fits)],
            "missing": ["cảnh gốc cần quay"]}

    def adapt(self, items, suggest=("gợi ý",)):
        def fake(script, beats, shots, used, fix):
            self.adapt_calls.append(sorted(fix))
            return {"beats": items, "suggest_filming": list(suggest)}
        ai.adapt_beats = fake

    def item(self, beat, usable=True, voice="Lời mới.", shot="s_5"):
        return {"beat": beat, "usable": usable, "shot_id": shot if usable else "none", "voice": voice if usable else "",
                "text": "", "text_pos": "bottom", "reason": "r"}

    def run_plan(self, adapt=True):
        return batch.plan_beats(self.script, self.beats, self.shots, {}, True, adapt, review=False)

    def test_all_good_matches_are_untouched_and_ai_is_not_asked_to_rewrite(self):
        self.matches(["tot"] * 5)
        self.adapt([])
        plan = self.run_plan()
        self.assertEqual(self.adapt_calls, [])
        self.assertEqual([p["voice"] for p in plan["picks"]], [f"Lời gốc {i}." for i in range(5)])

    def test_only_unmatched_beats_are_rewritten_even_if_the_model_overreaches(self):
        self.matches(["tot", "tot", "khong", "tot", "tot"])
        self.adapt([self.item(2), self.item(0, voice="Model tự ý sửa cảnh tốt.")])
        plan = self.run_plan()
        voices = [p["voice"] for p in plan["picks"]]
        self.assertEqual(self.adapt_calls, [[2]])
        self.assertEqual(voices[2], "Lời mới.")
        self.assertEqual(voices[0], "Lời gốc 0.")  # cảnh đã khớp tốt không bị đụng vào
        self.assertEqual([c["beat"] for c in plan["changes"]], [2])
        self.assertEqual(plan["missing"], ["gợi ý"])
        self.assertEqual(plan["blocked"], "")

    def test_unusable_middle_beat_is_dropped(self):
        self.matches(["tot", "tot", "khong", "tot", "tot"])
        self.adapt([self.item(2, usable=False)])
        plan = self.run_plan()
        self.assertEqual(len(plan["picks"]), 4)
        self.assertEqual([c["kind"] for c in plan["changes"]], ["drop"])
        self.assertEqual(plan["blocked"], "")

    def test_unusable_first_or_last_beat_is_kept_with_a_warning(self):
        self.matches(["khong", "tot", "tot", "tot", "tot"])
        self.adapt([self.item(0, usable=False)])
        plan = self.run_plan()
        self.assertEqual(len(plan["picks"]), 5)  # mở đầu và chốt không bỏ được
        self.assertEqual(plan["changes"], [])
        self.assertTrue(any("Cảnh 1" in w for w in plan["warnings"]))

    def test_script_is_blocked_when_half_the_beats_have_no_footage(self):
        self.matches(["khong", "tot", "khong", "tot", "khong"])
        self.adapt([self.item(0, usable=False), self.item(2, usable=False), self.item(4, usable=False)])
        self.assertIn("Chưa có video quay", self.run_plan()["blocked"])

    def test_script_is_blocked_when_footage_does_not_cover_the_product(self):
        self.matches(["tot", "khong", "khong", "khong", "khong"])
        self.adapt([self.item(i, usable=False) for i in range(1, 5)])
        plan = self.run_plan()
        self.assertIn("Chưa có video quay", plan["blocked"])

    def test_without_adapt_original_script_is_kept_with_warnings(self):
        self.matches(["tot", "khong", "tot", "tam", "tot"])
        self.adapt([self.item(1)])
        plan = self.run_plan(adapt=False)
        self.assertEqual(self.adapt_calls, [])
        self.assertEqual([p["voice"] for p in plan["picks"]], [f"Lời gốc {i}." for i in range(5)])
        self.assertTrue(any("Cảnh 2" in w for w in plan["warnings"]))

    def test_rewritten_line_with_an_unfilled_blank_is_blocked(self):
        self.matches(["tot", "khong", "tot", "tot", "tot"])
        self.adapt([self.item(1, voice="Cỡ [kiểm tra] nhé.")])
        self.assertIn("Còn ô chưa điền", self.run_plan()["blocked"])

    def test_ai_failure_while_rewriting_falls_back_to_the_original(self):
        self.matches(["tot", "khong", "tot", "tot", "tot"])

        def boom(*a, **k):
            raise ai.AIError("hết hạn mức")
        ai.adapt_beats = boom
        plan = self.run_plan()
        self.assertEqual(plan["blocked"], "")
        self.assertTrue(any("viết lại cảnh lỗi" in w for w in plan["warnings"]))


class BurnedSubtitles(unittest.TestCase):
    """Đoạn quay đã có phụ đề cháy sẵn: không phù hợp thì bỏ, phù hợp thì giữ nhưng chữ mới tránh chỗ đó."""

    def shot(self, i, sub="", ok=True, pos="bottom"):
        return {"id": f"s_{i}", "source_id": "s", "start": i * 3.0, "end": i * 3.0 + 3, "length": 3.0,
                "desc": f"đoạn {i}", "note": "", "thumb": "", "scene_start": 0.0, "scene_end": 30.0,
                "sub": sub, "sub_pos": pos if sub else "none", "sub_ok": ok}

    def test_any_leftover_sticker_or_drawing_is_dropped(self):
        # mặc định khắt khe: chữ nhỏ như "nụ" hay vòng tròn đỏ của video cũ cũng phải bỏ
        shots = [self.shot(0), self.shot(1, "Giá chỉ 39k hôm nay thôi nha", ok=False), self.shot(2, "nụ"),
                 {**self.shot(3), "marks": "vòng tròn đỏ khoanh sản phẩm"}]
        keep, dropped = library.usable_shots(shots)
        self.assertEqual(keep, [])   # 3/4 đoạn dính chữ: cả file là bản đã dựng
        self.assertEqual([s["id"] for s in dropped], ["s_0", "s_1", "s_2", "s_3"])
        # chế độ nới lỏng: chỉ bỏ đoạn AI nói là không phù hợp
        keep, dropped = library.usable_shots(shots, "lenient")
        self.assertEqual([s["id"] for s in keep], ["s_0", "s_2", "s_3"])

    def test_a_whole_file_that_looks_already_edited_is_dropped(self):
        # video đã dựng thì chữ rải khắp file: bắt được đoạn này vẫn sót đoạn kia, nên bỏ cả file
        shots = [self.shot(0), self.shot(1, "Giá sốc 39k"), self.shot(2, "Bấm giỏ ngay"), self.shot(3)]
        keep, dropped = library.usable_shots(shots)
        self.assertEqual(keep, [])
        self.assertEqual(len(dropped), 4)
        self.assertEqual(library.edited_sources(shots), {"s": (2, 4)})

    def test_one_stray_sticker_does_not_condemn_the_whole_file(self):
        shots = [self.shot(i) for i in range(9)] + [self.shot(9, "nụ")]
        keep, dropped = library.usable_shots(shots)
        self.assertEqual(len(keep), 9)
        self.assertEqual([s["id"] for s in dropped], ["s_9"])

    def test_nothing_clean_left_still_makes_a_video_by_cropping_the_old_text_away(self):
        # tất cả đoạn đều của bản đã dựng: vẫn dựng, nhưng cắt bỏ dải chữ cũ khỏi khung hình
        shots = [self.shot(i, "một câu lời thoại dài", ok=False) for i in range(4)]
        beats = [{"voice": f"Lời đọc số {i} đủ dài để đọc nha anh chị.", "text": "", "text_pos": "top",
                  "duration": 3} for i in range(4)]
        plan = batch.plan_beats({"title": "T"}, beats, shots, {}, False, True)
        self.assertEqual(plan["blocked"], "")
        self.assertEqual(len(plan["picks"]), 4)
        self.assertTrue(plan["salvage"])
        self.assertTrue(any("xào nấu" in w for w in plan["warnings"]))
        clip = library.clip_from_shot(plan["picks"][0]["shot"], "", plan["salvage"])
        self.assertEqual(clip["crop"], {"bottom": library.CROP["bottom"]})
        self.assertNotIn("avoid", clip)   # chữ cũ bị cắt mất rồi nên không phải né nữa

    def test_text_stuck_in_the_middle_of_the_frame_is_still_skipped(self):
        shots = [self.shot(0, "nụ", pos="center"), self.shot(1, "LỊCH 2027", pos="bottom")]
        keep, dropped = library.usable_shots(shots, "salvage")
        self.assertEqual([s["id"] for s in keep], ["s_1"])
        self.assertEqual([s["id"] for s in dropped], ["s_0"])

    def test_matching_never_sees_the_dropped_shots_and_says_so(self):
        shots = [self.shot(i) for i in range(4)] + [self.shot(9, "Bấm giỏ hàng ngay", ok=False)]
        beats = [{"voice": f"Lời {i}.", "text": "", "text_pos": "top", "duration": 3} for i in range(4)]
        seen = []

        def fake(beats_, shots_, used_=None):
            seen.extend(s["id"] for s in shots_)
            return {"matches": [{"beat": i, "shot_id": f"s_{i}", "fit": "tot", "reason": ""} for i in range(len(beats_))],
                    "missing": []}
        real = ai.simple_match
        ai.simple_match = fake
        try:
            plan = batch.plan_beats({"title": "T"}, beats, shots, {}, False, True)
        finally:
            ai.simple_match = real
        self.assertNotIn("s_9", seen)
        self.assertTrue(any("chữ hoặc nét chèn sẵn" in w for w in plan["warnings"]))

    def test_new_text_moves_away_from_the_burned_in_text(self):
        # chữ cháy sẵn ở đáy: chữ trên màn hình giữ chỗ cũ, phụ đề lời đọc được nâng lên
        self.assertEqual(assemble.caption_plan("top", ["bottom"], True), ("top", 0.0, assemble.SUB_LIFT))
        # chữ cháy sẵn đúng chỗ chữ mới: chữ mới dời sang chỗ còn trống
        pos, lift, sub_lift = assemble.caption_plan("top", ["top"], False)
        self.assertEqual((pos, lift, sub_lift), ("center", 0.0, 0.0))
        # không có chữ cháy sẵn thì giữ nguyên như trước, chỉ nâng chữ nếu nó nằm cùng đáy với phụ đề
        self.assertEqual(assemble.caption_plan("center", [], True), ("center", 0.0, 0.0))
        self.assertEqual(assemble.caption_plan("bottom", [], True)[1], assemble.SUB_LIFT)

    def test_lift_pushes_the_subtitle_line_up_in_the_ass_file(self):
        path = os.path.join(_TMP, "lift.ass")
        make_videos.build_ass({**make_videos.DEFAULTS, "captions": [
            {"start": 0, "end": 1, "text": "thường", "pos": "sub"},
            {"start": 1, "end": 2, "text": "nâng lên", "pos": "sub", "lift": 0.15}]}, 1080, 1920, 2.0, path)
        with open(path, encoding="utf-8") as f:
            rows = [line for line in f if line.startswith("Dialogue")]
        margins = [int(l.split(",")[7]) for l in rows]
        self.assertEqual(margins[0], 0)              # dùng lề của style
        self.assertGreater(margins[1], round(1920 * 0.15))


class Suggested(unittest.TestCase):
    """Kịch bản app tự viết từ chính video đã quay: mỗi cảnh gắn sẵn đoạn, không ghép lại nữa."""

    def setUp(self):
        shutil.rmtree(os.path.join(store.DATA_DIR, "scripts"), ignore_errors=True)
        os.makedirs(os.path.join(store.DATA_DIR, "scripts"))
        self.shots = [{"id": f"s_{i}", "source_id": "s", "start": i * 4.0, "end": i * 4.0 + 4, "length": 4.0,
                       "desc": f"đoạn {i}", "note": "", "thumb": "", "scene_start": 0.0, "scene_end": 40.0,
                       "sub": "", "sub_pos": "none", "sub_ok": True} for i in range(5)]

    def test_bound_beats_use_their_own_shot_without_asking_ai_again(self):
        beats = [{"voice": f"Lời {i}.", "text": "", "text_pos": "top", "duration": 3, "shot_id": f"s_{i}"}
                 for i in range(4)]
        real = ai.match_clips
        ai.match_clips = lambda *a, **k: self.fail("kịch bản đã gắn đoạn thì không được ghép lại")
        try:
            plan = batch.plan_beats({"title": "T"}, beats, self.shots, {}, True, True, review=False)
        finally:
            ai.match_clips = real
        self.assertEqual([p["shot"]["id"] for p in plan["picks"]], ["s_0", "s_1", "s_2", "s_3"])
        self.assertEqual([p["voice"] for p in plan["picks"]], [f"Lời {i}." for i in range(4)])
        self.assertEqual(plan["blocked"], "")

    def test_a_deleted_source_falls_back_to_normal_matching(self):
        beats = [{"voice": f"Lời {i}.", "text": "", "text_pos": "top", "duration": 3, "shot_id": "mat_roi"}
                 for i in range(4)]
        plan = batch.plan_beats({"title": "T"}, beats, self.shots, {}, False, False)
        self.assertEqual(len(plan["picks"]), 4)
        self.assertTrue(all(p["shot"]["id"] in {s["id"] for s in self.shots} for p in plan["picks"]))

    def test_written_scripts_are_stored_with_their_clips(self):
        real = (ai.is_ready, ai.suggest_scripts, library.ensure_shot_labels, library.collect_shots,
                library.review_beats)
        library.review_beats = lambda script, beats, shots, log=print, rounds=2: {
            "beats": beats, "changes": [], "note": "", "blocked": "", "seconds": 30.0}
        source = store.sources.save({"name": "quay.mov", "status": "ready", "path": "x.mov",
                                     "info": {"duration": 20.0}, "shots": []})
        ai.is_ready = lambda: True
        library.ensure_shot_labels = lambda ids, log=print: 0
        library.collect_shots = lambda ids: self.shots
        ai.suggest_scripts = lambda shots, count, note, channel, samples: {"scripts": [{
            "title": "Hậu trường xưởng in", "product": "Liễn", "summary": "", "hook_type": "Hậu trường",
            "why_it_works": "", "caption": "", "hashtags": [],
            "beats": [{"part": "Mở đầu", "shot_id": f"s_{i}", "voice": f"Câu {i}.", "text": "", "text_pos": "top",
                       "duration": 3} for i in range(4)] + [{"part": "Chốt", "shot_id": "khong_co",
                       "voice": "Bỏ cảnh này.", "text": "", "text_pos": "center", "duration": 3}]}]}
        try:
            result = library.suggest_from_sources({"count": 1, "note": "Liễn 39k"})
        finally:
            (ai.is_ready, ai.suggest_scripts, library.ensure_shot_labels, library.collect_shots,
             library.review_beats) = real
            store.sources.delete(source["id"])
        self.assertEqual(result["added"], 1)
        (script,) = store.scripts.list()
        self.assertEqual(script["origin"], "auto")
        self.assertEqual(len(script["beats"]), 4)  # cảnh gắn đoạn không tồn tại bị bỏ
        self.assertEqual([b["shot_id"] for b in script["beats"]], ["s_0", "s_1", "s_2", "s_3"])
        self.assertTrue(all(b["clip"]["source_id"] == "s" for b in script["beats"]))


class BeatSanity(unittest.TestCase):
    """Lời và chữ trên màn hình phải đúng chỗ, và chữ đi kèm lời."""

    def test_a_stray_fragment_in_the_voice_field_is_put_back_where_it_belongs(self):
        # lỗi thật gặp phải: AI để "nu" vào ô lời còn câu nói thì nằm ở ô chữ
        out = library.tidy_beat({"voice": "nu", "text": "Đừng chốt lịch bloc Tết 2027 nếu chưa soi kỹ ba điều này."})
        self.assertTrue(out["voice"].startswith("Đừng chốt lịch bloc"))
        self.assertLessEqual(len(out["text"].split()), library.MAX_TEXT_WORDS)
        self.assertNotEqual(out["text"], "nu")

    def test_a_fragment_with_nothing_to_swap_is_thrown_away(self):
        self.assertEqual(library.tidy_beat({"voice": "nu", "text": ""})["voice"], "")
        self.assertEqual(library.fix_beats([{"voice": "nu", "text": "x"}]), [])
        # câu ngắn thật thì vẫn giữ
        self.assertEqual(library.tidy_beat({"voice": "Bấm giỏ hàng nha!", "text": ""})["voice"], "Bấm giỏ hàng nha!")

    def test_text_is_written_from_the_line_when_the_model_leaves_it_empty(self):
        out = library.tidy_beat({"voice": "Anh chị ơi, thứ hai là kèm đủ hai con ốc vít xoắn này nha.", "text": ""})
        self.assertTrue(out["text"])
        self.assertLessEqual(len(out["text"].split()), 5)
        self.assertIn(out["text"].lower().split()[0], out["voice"].lower())

    def test_no_text_over_a_clip_where_someone_is_already_talking(self):
        beat = {"voice": "Em xoay nghiêng cho anh chị thấy độ dày của bloc nha.", "text": "Độ dày bloc"}
        self.assertEqual(library.tidy_beat(beat, {"talking": True})["text"], "")
        self.assertTrue(library.tidy_beat(beat, {"talking": False})["text"])

    def test_text_never_repeats_the_text_burned_into_the_clip(self):
        beat = {"voice": "Lịch bloc đại khổ mười bốn phẩy năm nhân hai mươi phẩy năm nha.", "text": "Lịch 2027"}
        out = library.tidy_beat(beat, {"sub": "LỊCH 2027 BLOC ĐẠI 14,5X20,5CM"})
        self.assertEqual(out["text"], "")


class CutQuality(unittest.TestCase):
    """Cắt ghép: lời phải vừa đoạn quay, và né khung hình sát chỗ chuyển cảnh."""

    def shot(self, span):
        return {"id": "s_0", "source_id": "s", "start": 0.0, "end": min(3.0, span), "length": min(3.0, span),
                "desc": "đoạn", "note": "", "thumb": "", "scene_start": 0.0, "scene_end": span,
                "sub": "", "sub_pos": "none", "marks": "", "sub_ok": True, "talking": False}

    def test_a_line_longer_than_its_clip_is_flagged(self):
        long_line = " ".join(["từ"] * 40)          # khoảng 10 giây lời đọc
        beats = [{"voice": long_line, "text": "", "text_pos": "top", "duration": 3, "shot_id": "s_0"}] * 3
        plan = batch.plan_beats({"title": "T"}, beats, [self.shot(3.0)], {}, False, False, review=False)
        self.assertTrue(any("lời dài hơn đoạn quay" in w for w in plan["warnings"]))

    def test_a_line_that_fits_is_not_flagged(self):
        beats = [{"voice": "Câu này đọc chừng ba giây thôi nha anh chị.", "text": "", "text_pos": "top",
                  "duration": 3, "shot_id": "s_0"}] * 3
        plan = batch.plan_beats({"title": "T"}, beats, [self.shot(20.0)], {}, False, False, review=False)
        self.assertFalse(any("lời dài hơn" in w for w in plan["warnings"]))


_SAMPLES = {}


def sample_movs():
    """(file .MOV nhỏ đọc được, file .MOV cắt dở), tạo một lần cho cả bộ test."""
    if not _SAMPLES:
        import subprocess
        folder = tempfile.mkdtemp()
        good = os.path.join(folder, "IMG_1327.MOV")
        subprocess.run([make_videos.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                        "-i", "testsrc2=size=320x568:duration=3:rate=24", "-f", "lavfi",
                        "-i", "sine=frequency=440:duration=3", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-shortest", "-f", "mov", good], check=True)
        broken = os.path.join(folder, "IMG_1329.MOV")
        with open(good, "rb") as f, open(broken, "wb") as out:
            out.write(f.read(4000))   # chép dở dang từ điện thoại
        _SAMPLES.update(folder=folder, good=good, broken=broken)
    return _SAMPLES


class MovFiles(unittest.TestCase):
    """Video quay bằng iPhone (.MOV, có khi viết hoa, nặng cả trăm MB) phải chọn được, tải được và báo lỗi rõ khi hỏng."""

    @classmethod
    def setUpClass(cls):
        cls.folder, cls.good, cls.broken = (sample_movs()[k] for k in ("folder", "good", "broken"))

    def client(self):
        try:
            from starlette.testclient import TestClient
        except Exception:
            self.skipTest("cần httpx để thử máy chủ web: pip install httpx")
        from app.server import app
        return TestClient(app)

    def wait(self, client, item, seconds=60):
        import time
        for _ in range(seconds * 4):
            job = jobs.get(item["job"])
            if job["status"] != "running":
                break
            time.sleep(0.25)
        return job, next(x for x in client.get("/api/sources").json() if x["id"] == item["id"])

    def test_extension_check_ignores_case_and_falls_back_to_the_browser_type(self):
        for name in ("IMG_1327.MOV", "a.mov", "b.Mp4", "c.3GP", "d.MTS"):
            self.assertTrue(media.is_video_name(name), name)
        self.assertTrue(media.is_video_name("khongduoi", "video/quicktime"))
        for name in ("a.jpg", "b.pdf", "c.docx", ""):
            self.assertFalse(media.is_video_name(name), name)

    def test_every_file_picker_lists_the_extensions_explicitly(self):
        # Windows hay ẩn .mov khi chỉ khai video/*, nên khai rõ từng đuôi, cả viết hoa
        with open(os.path.join(ROOT, "app", "static", "index.html"), encoding="utf-8") as f:
            html = f.read()
        for field in ('id="bt-file"', 'id="src-file"', 'id="imp-file"'):
            tag = html[html.index(field):].split(">", 1)[0]
            for ext in media.VIDEO_EXT:
                self.assertIn(ext + ",", tag + ",", f"{field} thiếu {ext}")
                self.assertIn(ext.upper(), tag, f"{field} thiếu {ext.upper()}")

    def test_server_advertises_the_same_list_to_the_page(self):
        with self.client() as client:
            self.assertEqual(client.get("/api/state").json()["video_ext"], list(media.VIDEO_EXT))

    def test_an_uppercase_mov_uploads_and_becomes_ready(self):
        with self.client() as client, open(self.good, "rb") as f:
            res = client.post("/api/sources", files=[("files", ("IMG_1327.MOV", f, "video/quicktime"))])
            self.assertEqual(res.status_code, 200)
            job, source = self.wait(client, res.json()[0])
        self.assertEqual(job["status"], "done", job.get("error"))
        self.assertEqual(source["status"], "ready")
        self.assertGreater(len(source["shots"]), 0)
        self.assertEqual((source["info"]["width"], source["info"]["height"]), (320, 568))

    def test_a_half_copied_mov_reports_an_error_instead_of_hanging(self):
        with self.client() as client, open(self.broken, "rb") as f:
            res = client.post("/api/sources", files=[("files", ("IMG_1329.MOV", f, "video/quicktime"))])
            job, source = self.wait(client, res.json()[0])
        self.assertEqual(job["status"], "error")           # trước đây treo mãi ở "running"
        self.assertEqual(source["status"], "error")
        self.assertIn("không đọc được video", source["error"].lower())

    def test_pictures_and_documents_are_refused_up_front(self):
        with self.client() as client:
            res = client.post("/api/sources", files=[("files", ("anh.jpg", b"x", "image/jpeg"))])
        self.assertEqual(res.status_code, 400)
        self.assertIn("không phải video", res.json()["detail"])
        self.assertIn("MOV", res.json()["detail"])

    def test_unreadable_media_raises_an_error_not_a_process_exit(self):
        with self.assertRaises(make_videos.ProbeError):
            make_videos.probe(self.broken)

    def test_a_background_job_that_exits_is_reported_not_left_running(self):
        def quits(log=print):
            raise SystemExit("thoát giữa chừng")
        job = jobs.submit("test", quits)
        import time
        for _ in range(40):
            if job["status"] != "running":
                break
            time.sleep(0.1)
        self.assertEqual(job["status"], "error")
        self.assertIn("thoát giữa chừng", job["error"])

    def test_big_hdr_clips_are_shrunk_before_the_slow_colour_conversion(self):
        info = {"width": 2160, "height": 3840}
        self.assertEqual(make_videos.hdr_prescale(info, 1080, 1920, "blur"), "scale=1080:1920:flags=bicubic,")
        self.assertEqual(make_videos.hdr_prescale({"width": 3840, "height": 2160}, 1080, 1920, "blur"),
                         "scale=1080:608:flags=bicubic,")
        self.assertEqual(make_videos.hdr_prescale({"width": 1080, "height": 1920}, 1080, 1920, "blur"), "")
        # cắt mất 22% chiều cao thì phần còn lại phải phóng lên 1920 px: khung thu nhỏ trước phải cao
        # 1920 / 0,78 = 2462 px, nhỏ hơn thế là hình bị mờ
        self.assertEqual(make_videos.hdr_prescale(info, 1080, 1920, "crop", {"bottom": 0.22}),
                         "scale=1384:2462:flags=bicubic,")

    def test_the_render_graph_shrinks_before_tonemapping_and_scene_detection_runs_small(self):
        seen = []

        class Done:
            returncode, stderr = 0, ""

        real = make_videos.subprocess.run
        make_videos.subprocess.run = lambda cmd, **k: (seen.append(cmd), Done())[1]
        try:
            info = {"duration": 6.0, "width": 2160, "height": 3840, "has_audio": False, "hdr": True}
            make_videos.render("x.MOV", info, {**make_videos.DEFAULTS, "clips": [{"start": 0, "end": 3}]},
                               "9:16", "out.mp4", self.folder)
            make_videos.detect_scenes("x.MOV", 0.3, 320)
        finally:
            make_videos.subprocess.run = real
        graph = seen[0][seen[0].index("-filter_complex") + 1]
        self.assertLess(graph.index("scale=1080:1920"), graph.index("zscale"))
        scene = seen[1][seen[1].index("-vf") + 1]
        self.assertLess(scene.index("scale=320"), scene.index("select="))

    def test_hdr_previews_also_shrink_first(self):
        chain = media._vf({"hdr": True}, "scale=240:-2")
        self.assertLess(chain.index("scale=240"), chain.index("zscale"))
        self.assertEqual(media._vf({"hdr": False}, "scale=240:-2"), "scale=240:-2")


class ProbeKinds(unittest.TestCase):
    """probe() đo cả video, file âm thanh (giọng đọc) lẫn ảnh (logo). Lỗi thật: bản 10.13 bắt mọi file phải có hình
    và có độ dài, làm hỏng nút Nghe thử và mọi video dựng có chèn logo."""

    @classmethod
    def setUpClass(cls):
        import subprocess
        cls.folder = tempfile.mkdtemp()
        cls.mp3 = os.path.join(cls.folder, "giong.mp3")
        cls.png = os.path.join(cls.folder, "logo.png")
        run = lambda *a: subprocess.run([make_videos.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *a], check=True)
        run("-f", "lavfi", "-i", "sine=frequency=440:duration=2", cls.mp3)
        run("-f", "lavfi", "-i", "color=c=red:s=300x120", "-frames:v", "1", cls.png)

    def test_an_audio_file_has_a_length_but_no_picture(self):
        info = make_videos.probe(self.mp3)
        self.assertAlmostEqual(info["duration"], 2.0, delta=0.15)
        self.assertIsNone(info["width"])
        self.assertTrue(info["has_audio"])

    def test_a_logo_image_has_a_size_but_no_length(self):
        info = make_videos.probe(self.png)
        self.assertEqual((info["width"], info["height"]), (300, 120))
        self.assertEqual(info["duration"], 0.0)

    def test_a_source_video_must_have_a_picture_and_a_length(self):
        with self.assertRaises(make_videos.ProbeError) as ctx:
            make_videos.probe_video(self.mp3)
        self.assertIn("chỉ có âm thanh", str(ctx.exception))
        self.assertEqual(make_videos.probe_video(sample_movs()["good"])["height"], 568)

    def test_a_file_that_cannot_be_read_at_all_is_still_an_error(self):
        with self.assertRaises(make_videos.ProbeError):
            make_videos.probe(sample_movs()["broken"])

    def test_a_voice_file_gets_its_length_through_the_listen_button(self):
        # Nghe thử: nhà cung cấp giọng trả về .mp3, app đo độ dài bằng probe()
        real = tts._edge
        tts._edge = lambda text, voice, rate, out: shutil.copyfile(self.mp3, out)
        try:
            path, seconds = tts.synthesize("Xin chào, đây là giọng đọc thử.", "edge", "vi-VN-HoaiMyNeural", 0, {})
        finally:
            tts._edge = real
        self.assertTrue(path.endswith(".mp3"))
        self.assertAlmostEqual(seconds, 2.0, delta=0.15)

    def test_the_preview_endpoint_answers_for_an_mp3_voice(self):
        try:
            from starlette.testclient import TestClient
        except Exception:
            self.skipTest("cần httpx")
        from app.server import app
        real = tts._edge
        tts._edge = lambda text, voice, rate, out: shutil.copyfile(self.mp3, out)
        try:
            with TestClient(app) as client:
                res = client.post("/api/tts/preview", json={"text": "Nghe thử giọng này nha anh chị.", "provider": "edge",
                                                            "voice": "vi-VN-HoaiMyNeural", "rate": 0})
        finally:
            tts._edge = real
        self.assertEqual(res.status_code, 200, res.text)
        self.assertGreater(res.json()["duration"], 1.5)

    def test_a_video_with_a_logo_renders(self):
        out = os.path.join(self.folder, "co_logo.mp4")
        info = make_videos.probe_video(sample_movs()["good"])
        opts = {**make_videos.DEFAULTS, "clips": [{"start": 0, "end": 2}], "logo": self.png, "captions": []}
        total = make_videos.render(sample_movs()["good"], info, opts, "9:16", out, self.folder)
        self.assertGreater(total, 1.5)
        self.assertGreater(os.path.getsize(out), 1000)

    def test_an_audio_only_upload_is_reported_as_a_source_error(self):
        try:
            from starlette.testclient import TestClient
        except Exception:
            self.skipTest("cần httpx")
        from app.server import app
        import time
        with TestClient(app) as client:
            res = client.post("/api/sources/stream?name=ghi_am.mov", content=open(self.mp3, "rb").read())
            self.assertEqual(res.status_code, 200)
            item = res.json()[0]
            for _ in range(80):
                if jobs.get(item["job"])["status"] != "running":
                    break
                time.sleep(0.25)
            source = next(x for x in client.get("/api/sources").json() if x["id"] == item["id"])
        self.assertEqual(source["status"], "error")
        self.assertIn("chỉ có âm thanh", source["error"])


class Speed(unittest.TestCase):
    """Phân tích video và viết kịch bản chậm vì chờ AI lần lượt, và vì mở lại file 4K gốc cho từng ảnh."""

    def setUp(self):
        shutil.rmtree(os.path.join(store.DATA_DIR, "sources"), ignore_errors=True)
        os.makedirs(os.path.join(store.DATA_DIR, "sources"))
        os.environ["ANTHROPIC_API_KEY"] = "x"
        self.real = (ai.label_shots, library._strip, ai.review_plan)

    def tearDown(self):
        ai.label_shots, library._strip, ai.review_plan = self.real
        os.environ.pop("ANTHROPIC_API_KEY", None)

    def source(self, n=40):
        shots = [{"start": i * 3.0, "end": i * 3.0 + 3, "thumb": "t.jpg", "scene": i, "scene_start": i * 3.0,
                  "scene_end": i * 3.0 + 3} for i in range(n)]
        return store.sources.save({"name": "a.mov", "status": "ready", "path": "x.mov", "info": {"duration": n * 3.0},
                                   "shots": shots, "note": ""})

    # ---- mô tả đoạn quay chạy song song ----
    def test_labelling_sends_requests_at_the_same_time_and_labels_every_shot_once(self):
        import threading
        import time
        src = self.source(40)
        flight = {"now": 0, "peak": 0, "calls": 0}
        lock = threading.Lock()

        def fake(items, note=""):
            with lock:
                flight["now"] += 1
                flight["calls"] += 1
                flight["peak"] = max(flight["peak"], flight["now"])
            time.sleep(0.25)
            with lock:
                flight["now"] -= 1
            return {k: {"index": k, "desc": f"cảnh {k}", "product": "", "sub": "", "sub_pos": "none", "marks": "",
                        "sub_ok": True, "talking": False} for k, _ in items}
        ai.label_shots, library._strip = fake, lambda src_, k: "strip.jpg"
        started = time.time()
        total = library.ensure_shot_labels([src["id"]])
        took = time.time() - started
        shots = store.sources.get(src["id"])["shots"]
        self.assertEqual(total, 40)
        self.assertEqual(flight["calls"], 4)                       # 40 đoạn, mỗi yêu cầu 12 đoạn... gộp theo nguồn
        self.assertTrue(all(sh["desc"] == f"cảnh {k}" and sh["sub_checked"] for k, sh in enumerate(shots)))
        self.assertGreaterEqual(flight["peak"], 3)                 # thật sự có nhiều yêu cầu cùng bay
        self.assertLess(took, 0.25 * flight["calls"])              # nhanh hơn gửi lần lượt

    def test_results_of_concurrent_requests_do_not_overwrite_each_other(self):
        src = self.source(50)
        ai.label_shots = lambda items, note="": {k: {"index": k, "desc": f"d{k}", "product": "", "sub": "",
                                                    "sub_pos": "none", "marks": "", "sub_ok": True, "talking": False}
                                                  for k, _ in items}
        library._strip = lambda src_, k: "s.jpg"
        library.ensure_shot_labels([src["id"]], chunk=3, workers=6)
        self.assertEqual([sh["desc"] for sh in store.sources.get(src["id"])["shots"]], [f"d{k}" for k in range(50)])

    def test_a_shared_failure_stops_sending_the_rest_and_keeps_what_was_done(self):
        src = self.source(48)
        calls = []

        def fake(items, note=""):
            calls.append(1)
            if len(calls) > 2:
                raise ai.AIError("Tài khoản Anthropic đã hết tiền.")
            return {k: {"index": k, "desc": "ok", "product": "", "sub": "", "sub_pos": "none", "marks": "",
                        "sub_ok": True, "talking": False} for k, _ in items}
        ai.label_shots, library._strip = fake, lambda src_, k: "s.jpg"
        with self.assertRaises(ai.AIError):
            library.ensure_shot_labels([src["id"]], chunk=4, workers=1)
        done = [sh for sh in store.sources.get(src["id"])["shots"] if sh.get("sub_checked")]
        self.assertEqual(len(done), 8)                              # 2 yêu cầu đầu đã lưu
        self.assertLess(len(calls), 12)                             # không gửi nốt cả 12 yêu cầu

    def test_already_described_shots_are_not_sent_again(self):
        src = self.source(6)
        s = store.sources.get(src["id"])
        for sh in s["shots"]:
            sh.update(desc="đã có", sub_checked=True)
        store.sources.save(s)
        ai.label_shots = lambda *a, **k: self.fail("không được gọi AI cho đoạn đã mô tả")
        self.assertEqual(library.ensure_shot_labels([src["id"]]), 0)

    # ---- ảnh 3 khung lấy từ bản xem thử nhỏ ----
    def test_three_frame_strips_come_from_the_small_preview_not_the_4k_original(self):
        seen = []
        real = media.shot_strip
        media.shot_strip = lambda path, info, start, end, out, width=320: seen.append((path, info["hdr"]))
        try:
            src = {"path": os.path.join(_TMP, "goc.mov"), "proxy": os.path.join(_TMP, "proxy.mp4"),
                   "info": {"duration": 9.0, "hdr": True}, "shots": [{"start": 0, "end": 3, "thumb": "t.jpg"}]}
            open(src["proxy"], "wb").close()
            self.real[1](src, 0)                                    # _strip thật
        finally:
            media.shot_strip = real
        self.assertEqual(seen, [(src["proxy"], False)])             # bản nhỏ, và không đổi màu HDR lần thứ hai

    # ---- mô hình nhanh để nhìn ảnh ----
    def test_the_fast_model_is_the_default_for_looking_at_pictures_and_best_is_a_setting(self):
        store.save_settings({"ai_speed": "fast"})
        self.assertEqual(ai.label_model(), ai.LABEL_MODEL_FAST)
        store.save_settings({"ai_speed": "best"})
        self.assertEqual(ai.label_model(), ai.MODEL)
        store.save_settings({"ai_speed": "fast"})

    def test_a_fast_model_the_account_cannot_use_falls_back_to_the_main_one(self):
        import httpx
        import anthropic
        tried = []

        class Messages:
            def create(self, **kw):
                tried.append(kw["model"])
                if kw["model"] != ai.MODEL:
                    raise anthropic.NotFoundError("model", response=httpx.Response(404, request=httpx.Request("POST", "http://x")),
                                                  body={"error": {"message": "model not found"}})
                return type("R", (), {"stop_reason": "end_turn", "content": [type("B", (), {"type": "text", "text": '{"ok": 1}'})()]})()
        real = ai._client
        ai._client = lambda: type("C", (), {"beta": type("B", (), {"messages": Messages()})()})()
        try:
            out = ai._ask([{"type": "text", "text": "x"}], {"type": "object"}, model="claude-mô-hình-không-có")
        finally:
            ai._client = real
        self.assertEqual(out, {"ok": 1})
        self.assertEqual(tried, ["claude-mô-hình-không-có", ai.MODEL])

    def test_the_main_model_failing_is_reported_not_retried_with_itself(self):
        import httpx
        import anthropic
        tried = []

        class Messages:
            def create(self, **kw):
                tried.append(kw["model"])
                raise anthropic.NotFoundError("model", response=httpx.Response(404, request=httpx.Request("POST", "http://x")),
                                              body={"error": {"message": "nope"}})
        real = ai._client
        ai._client = lambda: type("C", (), {"beta": type("B", (), {"messages": Messages()})()})()
        try:
            with self.assertRaises(ai.AIError):
                ai._ask([{"type": "text", "text": "x"}], {"type": "object"})
        finally:
            ai._client = real
        self.assertEqual(tried, [ai.MODEL])

    # ---- bộ nhớ đệm cho kho đoạn quay ----
    def test_the_shot_inventory_is_identical_between_calls_so_it_can_be_cached(self):
        shots = [{"id": f"s_{i}", "source_id": "s", "start": 0.0, "end": 3.0, "length": 3.0, "desc": f"đoạn {i}",
                  "note": "", "thumb": "t.jpg", "scene_start": 0.0, "scene_end": 3.0} for i in range(5)]
        sent = []
        real = ai._ask
        ai._ask = lambda content, schema, **kw: (sent.append(content), {"matches": [], "missing": []})[1]
        try:
            ai.match_clips([{"voice": "a", "shot": "x", "duration": 3}], shots, {"title": "Kịch bản A"}, {"s_1": 3})
            ai.match_clips([{"voice": "b", "shot": "y", "duration": 4}], shots, {"title": "Kịch bản B"}, {"s_2": 1, "s_4": 2})
        finally:
            ai._ask = real
        marks = [[i for i, b in enumerate(c) if "cache_control" in b] for c in sent]
        self.assertEqual([len(m) for m in marks], [1, 1])           # đúng một điểm đánh dấu mỗi lần gọi
        prefixes = [json.dumps(c[:m[0] + 1], ensure_ascii=False) for c, m in zip(sent, marks)]
        self.assertEqual(prefixes[0], prefixes[1])                  # phần kho giống hệt nhau => được nhớ lại
        self.assertNotIn("đã dùng", prefixes[0])                    # số lần dùng đổi theo từng video nên phải đứng sau
        after = json.dumps(sent[1][marks[1][0] + 1:], ensure_ascii=False)
        self.assertIn("s_4×2", after)

    # ---- viết kịch bản: soát lại song song ----
    def test_scripts_are_reviewed_at_the_same_time_and_keep_their_order(self):
        import time
        src = self.source(12)
        shots = library.collect_shots([src["id"]])
        for k, sh in enumerate(store.sources.get(src["id"])["shots"]):
            sh.update(desc=f"đoạn {k}", sub_checked=True)
        s = store.sources.get(src["id"])
        for sh in s["shots"]:
            sh.update(desc="đoạn", sub_checked=True)
        store.sources.save(s)
        shots = library.collect_shots([src["id"]])
        make = lambda n: {"title": f"Hướng {n}", "product": "Lịch", "summary": "", "hook_type": "", "why_it_works": "",
                          "caption": "", "hashtags": [], "beats": [{"part": "p", "shot_id": shots[(n + i) % 12]["id"],
                          "voice": f"Câu {i} của hướng {n} nói đủ dài để đọc nha anh chị.", "text": "", "text_pos": "top",
                          "duration": 4} for i in range(4)]}
        ai.suggest_scripts = lambda *a, **k: {"scripts": [make(n) for n in range(3)]}
        calls = []

        def slow_review(script, items, shots_, seconds, target=(30, 40), salvage=False):
            calls.append(time.time())
            time.sleep(0.4)
            return {"verdict": "ok", "note": "", "beats": [{"from": i, "shot_id": it["shot_id"], "part": "p",
                    "voice": it["voice"], "text": "", "text_pos": "top", "duration": 4, "changed": ""}
                    for i, it in enumerate(items)]}
        ai.review_plan = slow_review
        real_labels, real_ready = library.ensure_shot_labels, ai.is_ready
        library.ensure_shot_labels, ai.is_ready = (lambda *a, **k: 0), (lambda: True)
        started = time.time()
        try:
            result = library.suggest_from_sources({"count": 3, "mode": "lenient"})
        finally:
            library.ensure_shot_labels, ai.is_ready = real_labels, real_ready
        took = time.time() - started
        self.assertEqual(result["added"], 3)
        self.assertLess(took, 0.4 * 3)                                # song song, không phải 1,2 giây lần lượt
        titles = [store.scripts.get(i)["title"] for i in result["ids"]]
        self.assertEqual([t.split(" · ")[-1] for t in titles], ["Hướng 0", "Hướng 1", "Hướng 2"])

    # ---- đợt tạo video: lập kế hoạch gối đầu với dựng ----
    def test_planning_the_next_video_overlaps_with_rendering_the_current_one(self):
        import time
        from app import batch as b
        s = self.source(12)
        sh = store.sources.get(s["id"])
        for x in sh["shots"]:
            x.update(desc="đoạn", sub_checked=True)
        store.sources.save(sh)
        for sid in store.scripts.list():
            pass
        scripts = [store.scripts.save({"title": f"K{i}", "code": f"K{i}", "channel": "NS", "beats": [
                   {"voice": "Lời đủ dài để đọc nha anh chị.", "shot": "x", "text": "", "text_pos": "top", "duration": 3}] * 4,
                   "status": "ready"}) for i in range(4)]
        events = []
        real = (b.plan_beats, b.assemble.render_project)

        def slow_plan(script, beats, shots, used, use_ai, adapt, note=lambda m: None, review=True, mode="strict"):
            events.append(("plan+", script["title"], time.time()))
            time.sleep(0.4)
            events.append(("plan-", script["title"], time.time()))
            picks = [{"shot": shots[i], "fit": "tot", "reason": "", "voice": "Lời đủ dài để đọc nha anh chị.", "text": "",
                      "text_pos": "top", "orig_voice": "", "adapted": False, "drop": False} for i in range(3)]
            return {"blocked": "", "warnings": [], "missing": [], "changes": [], "picks": picks,
                    "beats": [{"part": "", "shot": "", "duration": 3}] * 3}

        def slow_render(project, log=print):
            events.append(("render+", project["name"], time.time()))
            time.sleep(0.4)
            events.append(("render-", project["name"], time.time()))
            return {"path": "/x.mp4", "duration": 10.0, "created": time.time()}
        b.plan_beats, b.assemble.render_project = slow_plan, slow_render
        batch_ = store.batches.save({"name": "t", "status": "running", "message": "", "options": {"voice_mode": "one", "music": "none",
                                     "review": False}, "items": [{"script_id": x["id"], "code": x["code"], "title": x["title"],
                                     "channel": "NS", "status": "pending", "message": "", "warnings": [], "quality": "",
                                     "project_id": None, "render": None, "used": [], "missing": []} for x in scripts]})
        started = time.time()
        try:
            b._run(batch_["id"])
        finally:
            b.plan_beats, b.assemble.render_project = real
        took = time.time() - started
        done = store.batches.get(batch_["id"])
        self.assertEqual([i["status"] for i in done["items"]], ["done"] * 4)
        self.assertEqual(done["status"], "done")
        self.assertLess(took, 4 * 0.8 - 0.5)                         # tuần tự là 3,2 giây; gối đầu còn khoảng 2 giây
        plan_starts = {e[1]: e[2] for e in events if e[0] == "plan+"}
        render_ends = {e[1]: e[2] for e in events if e[0] == "render-"}
        self.assertLess(plan_starts["K1"], render_ends["K0"])        # đang dựng video 1 thì đã lập kế hoạch video 2
        order = [e[1] for e in events if e[0] == "render+"]
        self.assertEqual(order, ["K0", "K1", "K2", "K3"])            # vẫn dựng đúng thứ tự đã chọn

    def test_cancelling_leaves_planned_but_unrendered_videos_to_resume(self):
        import time
        from app import batch as b
        s = self.source(12)
        sh = store.sources.get(s["id"])
        for x in sh["shots"]:
            x.update(desc="đoạn", sub_checked=True)
        store.sources.save(sh)
        scripts = [store.scripts.save({"title": f"H{i}", "code": f"H{i}", "channel": "NS", "status": "ready", "beats": [
                   {"voice": "Lời đủ dài để đọc nha anh chị.", "shot": "x", "text": "", "text_pos": "top", "duration": 3}] * 4})
                   for i in range(4)]
        real = (b.plan_beats, b.assemble.render_project)
        batch_ = store.batches.save({"name": "t", "status": "running", "message": "", "options": {"voice_mode": "one", "music": "none",
                                     "review": False}, "items": [{"script_id": x["id"], "code": x["code"], "title": x["title"],
                                     "channel": "NS", "status": "pending", "message": "", "warnings": [], "quality": "",
                                     "project_id": None, "render": None, "used": [], "missing": []} for x in scripts]})

        def plan(script, beats, shots, used, use_ai, adapt, note=lambda m: None, review=True, mode="strict"):
            picks = [{"shot": shots[i], "fit": "tot", "reason": "", "voice": "Lời đủ dài để đọc nha anh chị.", "text": "",
                      "text_pos": "top", "orig_voice": "", "adapted": False, "drop": False} for i in range(3)]
            return {"blocked": "", "warnings": [], "missing": [], "changes": [], "picks": picks,
                    "beats": [{"part": "", "shot": "", "duration": 3}] * 3}

        def render(project, log=print):
            b.cancel(batch_["id"])        # bấm Dừng ngay khi đang dựng video đầu tiên
            time.sleep(0.3)
            return {"path": "/x.mp4", "duration": 10.0, "created": time.time()}
        b.plan_beats, b.assemble.render_project = plan, render
        try:
            b._run(batch_["id"])
        finally:
            b.plan_beats, b.assemble.render_project = real
        final = store.batches.get(batch_["id"])
        statuses = [i["status"] for i in final["items"]]
        self.assertEqual(statuses[0], "done")
        self.assertNotIn("planned", statuses)                        # video đã lập kế hoạch mà chưa dựng quay về "chờ"
        self.assertNotIn("rendering", statuses)
        self.assertEqual(final["status"], "cancelled")


class Connection(unittest.TestCase):
    """"Failed to fetch": app dừng, trình duyệt chạy bản giao diện cũ, tải file nặng đứt giữa chừng, khoá file trên Windows."""

    def client(self, **kw):
        try:
            from starlette.testclient import TestClient
        except Exception:
            self.skipTest("cần httpx để thử máy chủ web: pip install httpx")
        from app.server import app
        return TestClient(app, **kw)

    def wait(self, client, item, seconds=60):
        import time
        for _ in range(seconds * 4):
            job = jobs.get(item["job"])
            if job["status"] != "running":
                break
            time.sleep(0.25)
        return job, next(x for x in client.get("/api/sources").json() if x["id"] == item["id"])

    # ---- trình duyệt không được giữ bản giao diện cũ ----
    def test_page_and_scripts_are_never_served_from_the_browsers_cache(self):
        from app import __version__
        with self.client() as client:
            page = client.get("/")
            self.assertEqual(page.headers["cache-control"], "no-cache")
            self.assertIn(f"/static/app.js?v={__version__}", page.text)   # có bản mới là địa chỉ đổi theo
            self.assertIn(f"/static/style.css?v={__version__}", page.text)
            self.assertEqual(client.get("/static/app.js").headers["cache-control"], "no-cache")
            self.assertEqual(client.get("/api/state").headers["cache-control"], "no-cache")

    def test_ping_answers_with_the_version_and_a_restart_marker(self):
        from app import __version__
        with self.client() as client:
            first = client.get("/api/ping").json()
        self.assertEqual((first["ok"], first["version"]), (True, __version__))
        self.assertTrue(first["boot"])   # đổi mỗi lần app khởi động để trang biết app vừa chạy lại

    def test_cross_site_writes_are_still_blocked_by_the_new_middleware(self):
        with self.client() as client:
            evil = client.post("/api/sources/precheck", json={"name": "a.mov", "size": 1},
                               headers={"origin": "http://evil.example"})
            ok = client.post("/api/sources/precheck", json={"name": "a.mov", "size": 1},
                             headers={"origin": "http://testserver"})
        self.assertEqual(evil.status_code, 403)
        self.assertEqual(ok.status_code, 200)

    def test_an_unexpected_error_comes_back_as_readable_json_not_a_blank_500(self):
        from app.server import app

        @app.get("/api/_boom")
        def boom():
            raise ZeroDivisionError("chia cho 0")
        with self.client(raise_server_exceptions=False) as client:
            res = client.get("/api/_boom")
        self.assertEqual(res.status_code, 500)
        self.assertIn("ZeroDivisionError", res.json()["detail"])
        self.assertIn("nhật ký", res.json()["detail"])

    # ---- tải video nặng ----
    def test_streamed_upload_becomes_a_ready_source(self):
        with self.client() as client, open(sample_movs()["good"], "rb") as f:
            data = f.read()
            res = client.post("/api/sources/stream?name=IMG_1327.MOV", content=data,
                              headers={"content-type": "application/octet-stream"})
            self.assertEqual(res.status_code, 200)
            job, source = self.wait(client, res.json()[0])
        self.assertEqual((job["status"], source["status"]), ("done", "ready"))
        self.assertEqual(source["name"], "IMG_1327.MOV")

    def test_streamed_upload_cannot_write_outside_the_data_folder(self):
        with self.client() as client:
            res = client.post("/api/sources/stream?name=../../evil.mov", content=b"x" * 100)
            sources = client.get("/api/sources").json()
        self.assertEqual(res.status_code, 200)
        self.assertTrue(all(".." not in s["path"] for s in sources))
        self.assertFalse(os.path.exists(os.path.join(ROOT, "evil.mov")))

    def test_streamed_upload_refuses_non_video_and_empty_files_and_leaves_nothing_behind(self):
        with self.client() as client:
            before = len(client.get("/api/sources").json())
            self.assertEqual(client.post("/api/sources/stream?name=anh.jpg", content=b"x" * 50).status_code, 400)
            empty = client.post("/api/sources/stream?name=rong.mov", content=b"")
            self.assertEqual(empty.status_code, 400)
            self.assertIn("rỗng", empty.json()["detail"])
            self.assertEqual(len(client.get("/api/sources").json()), before)   # không có video ma
        leftovers = [n for _, _, files in os.walk(os.path.join(store.DATA_DIR, "sources"))
                     for n in files if n.endswith(".part")]
        self.assertEqual(leftovers, [])

    def test_precheck_reports_a_full_disk_before_anything_is_sent(self):
        import shutil as _sh
        real = _sh.disk_usage
        _sh.disk_usage = lambda p: type("U", (), {"total": 10**12, "used": 10**12 - 10**8, "free": 10**8})()
        try:
            with self.client() as client:
                res = client.post("/api/sources/precheck", json={"name": "IMG_1351.MOV", "size": 800_000_000})
        finally:
            _sh.disk_usage = real
        self.assertEqual(res.status_code, 507)
        self.assertIn("còn trống", res.json()["detail"])
        self.assertIn("IMG_1351.MOV", res.json()["detail"])

    def test_precheck_refuses_a_non_video_with_the_list_of_extensions(self):
        with self.client() as client:
            res = client.post("/api/sources/precheck", json={"name": "ghi_chu.txt", "size": 10})
        self.assertEqual(res.status_code, 400)
        self.assertIn("MOV", res.json()["detail"])

    # ---- Windows: khoá file, file hỏng, app tắt giữa chừng ----
    def test_replacing_a_file_is_retried_when_windows_says_permission_denied(self):
        calls = []
        real = os.replace

        def flaky(a, b):
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError(13, "Access is denied")
            return real(a, b)
        os.replace = flaky
        try:
            item = store.scripts.save({"title": "thử khoá file", "beats": []})
        finally:
            os.replace = real
        self.assertEqual(len(calls), 3)
        self.assertEqual(store.scripts.get(item["id"])["title"], "thử khoá file")

    def test_a_corrupt_record_is_skipped_instead_of_breaking_the_whole_list(self):
        good = store.scripts.save({"title": "bản tốt", "beats": []})
        bad = os.path.join(store.scripts.dir, "hong12345.json")
        with open(bad, "w", encoding="utf-8") as f:
            f.write('{"title": "cụt giữa chừng')
        try:
            titles = [s["title"] for s in store.scripts.list()]
            with self.assertRaises(KeyError):
                store.scripts.get("hong12345")
        finally:
            os.remove(bad)
        self.assertIn("bản tốt", titles)
        self.assertTrue(good)

    def test_reading_while_saving_never_fails(self):
        import threading
        item = store.scripts.save({"title": "đọc ghi cùng lúc", "beats": []})
        errors, stop = [], threading.Event()

        def writer():
            n = 0
            while not stop.is_set():
                n += 1
                try:
                    store.scripts.save({**item, "n": n})
                except Exception as err:
                    errors.append(err)

        t = threading.Thread(target=writer)
        t.start()
        try:
            for _ in range(300):
                store.scripts.list()
                store.scripts.get(item["id"])
        except Exception as err:
            errors.append(err)
        finally:
            stop.set()
            t.join()
        self.assertEqual(errors, [])

    def test_videos_left_processing_by_a_crash_are_picked_up_again_or_reported(self):
        from app import server
        alive = store.sources.save({"name": "con.mov", "status": "processing", "path": sample_movs()["good"]})
        gone = store.sources.save({"name": "mat.mov", "status": "processing", "path": "/khong/co/file.mov"})
        analysing = store.scripts.save({"title": "dở dang", "status": "processing", "beats": []})
        server.recover_interrupted()
        self.assertEqual(store.sources.get(gone["id"])["status"], "error")
        self.assertIn("tải lại", store.sources.get(gone["id"])["error"])
        self.assertEqual(store.scripts.get(analysing["id"])["status"], "error")
        import time
        for _ in range(240):
            if store.sources.get(alive["id"])["status"] != "processing":
                break
            time.sleep(0.25)
        self.assertEqual(store.sources.get(alive["id"])["status"], "ready")   # được xử lý lại, không kẹt mãi

    def test_a_failing_startup_step_does_not_stop_the_app(self):
        from app import server
        server._safely(lambda: 1 / 0, "thử")   # chỉ ghi nhật ký, không ném lỗi ra ngoài

    def test_the_font_list_survives_a_broken_font_file(self):
        real = fonts._read

        def broken(path):
            raise ValueError("file phông hỏng")
        fonts._read = broken
        try:
            fonts.system_fonts(refresh=True)       # không được ném lỗi
        finally:
            fonts._read = real
            fonts.system_fonts(refresh=True)

    # ---- chẩn đoán ----
    def test_errors_are_written_to_the_log_file_and_can_be_read_back(self):
        import logging
        diag.setup_logging()
        logging.getLogger("studio").error("lỗi thử nghiệm 12345")
        for h in logging.getLogger("studio").handlers:
            h.flush()
        self.assertIn("lỗi thử nghiệm 12345", diag.tail_log())
        with self.client() as client:
            self.assertIn("lỗi thử nghiệm 12345", client.get("/api/log").text)

    def test_a_port_just_released_by_a_killed_app_counts_as_free(self):
        # lỗi thật gặp khi thử: tắt app đột ngột rồi bật lại ngay thì cổng còn TIME_WAIT, thử chiếm cổng báo "bận" oan
        import socket
        from app import __main__ as launcher
        server = socket.socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]
        self.assertTrue(launcher.port_in_use("127.0.0.1", port))        # đang có app lắng nghe
        client = socket.create_connection(("127.0.0.1", port))
        conn, _ = server.accept()
        conn.close()                                                     # phía máy chủ đóng trước => TIME_WAIT
        client.close()
        server.close()
        self.assertFalse(launcher.port_in_use("127.0.0.1", port))       # app đã tắt: được phép bật lại

    def test_console_quick_edit_fix_is_a_no_op_away_from_windows(self):
        if os.name != "nt":
            self.assertFalse(diag.disable_quickedit())

    def test_a_onedrive_folder_and_a_nearly_full_disk_are_called_out(self):
        real_dir, real_usage = store.DATA_DIR, diag.shutil.disk_usage
        store.DATA_DIR = r"C:\Users\Lan\OneDrive\Desktop\TikTokVideoStudio\data"
        diag.shutil.disk_usage = lambda p: type("U", (), {"free": 3 * 10**9})()
        try:
            warnings = diag.env_warnings()
        finally:
            store.DATA_DIR, diag.shutil.disk_usage = real_dir, real_usage
        self.assertTrue(any("OneDrive" in w for w in warnings))
        self.assertTrue(any("3.0 GB" in w for w in warnings))

    def test_the_state_endpoint_carries_warnings_and_the_restart_marker(self):
        with self.client() as client:
            state = client.get("/api/state").json()
        self.assertIn("warnings", state)
        self.assertEqual(state["boot"], client.get("/api/ping").json()["boot"])


class ApiErrors(unittest.TestCase):
    """Lỗi của Claude API phải thành một câu tiếng Việt nói rõ phải làm gì."""

    def err(self, message, code=200):
        return type("E", (Exception,), {"status_code": code, "body": {"type": "error", "error": {
            "type": "invalid_request_error", "message": message}}, "message": "..."})()

    def test_running_out_of_credit_says_where_to_top_up(self):
        out = ai.friendly_error(self.err("Your credit balance is too low to access the Anthropic API. "
                                         "Please go to Plans & Billing to upgrade or purchase credits."))
        self.assertIn("hết tiền", out)
        self.assertIn("Plans & Billing", out)
        self.assertNotIn("200", out)      # mã 200 của luồng streaming chỉ làm rối

    def test_other_known_failures_are_translated(self):
        self.assertIn("giới hạn tần suất", ai.friendly_error(self.err("rate_limit_error", 429)))
        self.assertIn("quá tải", ai.friendly_error(self.err("Overloaded", 529)))
        self.assertIn("key", ai.friendly_error(self.err("invalid x-api-key", 401)))

    def test_an_unknown_failure_keeps_the_original_wording_without_the_json(self):
        out = ai.friendly_error(self.err("gateway blew up", 502))
        self.assertIn("gateway blew up", out)
        self.assertNotIn("{", out)

    def test_the_batch_keeps_going_without_ai(self):
        shots = [{"id": f"s_{i}", "source_id": "s", "start": i * 3.0, "end": i * 3.0 + 3, "length": 3.0,
                  "desc": "", "note": "", "thumb": "", "scene_start": 0.0, "scene_end": 30.0, "sub": "",
                  "sub_pos": "none", "marks": "", "sub_ok": True, "talking": False} for i in range(5)]
        beats = [{"voice": f"Lời đọc số {i} đủ dài để đọc nha.", "text": "", "text_pos": "top", "duration": 3}
                 for i in range(4)]
        real = ai.match_clips
        ai.match_clips = lambda *a, **k: (_ for _ in ()).throw(ai.AIError("Tài khoản Anthropic đã hết tiền."))
        try:
            plan = batch.plan_beats({"title": "T"}, beats, shots, {}, True, False, review=False)
        finally:
            ai.match_clips = real
        self.assertEqual(plan["blocked"], "")
        self.assertEqual(len(plan["picks"]), 4)   # vẫn ra video, chỉ là ghép đơn giản
        self.assertTrue(any("hết tiền" in w for w in plan["warnings"]))


class Salvage(unittest.TestCase):
    """Chỉ còn file đã dựng: cắt bỏ dải chữ cũ khỏi khung hình rồi xào lại thành video khác."""

    def test_the_band_with_the_old_text_is_cut_out_of_the_frame(self):
        self.assertIn("crop=iw:", make_videos.crop_filter({"bottom": 0.22}))
        self.assertIn(":0:trunc(ih*0.1600/2)*2", make_videos.crop_filter({"top": 0.16}))
        self.assertEqual(make_videos.crop_filter(None), "")
        self.assertEqual(make_videos.crop_filter({"bottom": 0}), "")

    def test_only_text_at_the_top_or_bottom_can_be_cut_away(self):
        self.assertEqual(library.crop_for({"sub": "LỊCH 2027", "sub_pos": "bottom"}), {"bottom": 0.22})
        self.assertEqual(library.crop_for({"sub": "tên kênh", "sub_pos": "top"}), {"top": 0.16})
        self.assertIsNone(library.crop_for({"sub": "nụ", "sub_pos": "center"}))
        self.assertIsNone(library.crop_for({"sub": "", "sub_pos": "none"}))

    def test_choosing_salvage_crops_even_when_clean_clips_exist(self):
        dirty = {"id": "s_0", "source_id": "s", "start": 0.0, "end": 3.0, "length": 3.0, "desc": "đoạn",
                 "note": "", "thumb": "", "scene_start": 0.0, "scene_end": 12.0, "sub": "LỊCH 2027",
                 "sub_pos": "bottom", "marks": "", "sub_ok": True, "talking": False}
        clean = {**dirty, "id": "s_1", "sub": "", "sub_pos": "none"}
        beats = [{"voice": f"Lời đọc số {i} đủ dài để đọc nha anh chị.", "text": "", "text_pos": "top",
                  "duration": 3} for i in range(4)]
        plan = batch.plan_beats({"title": "T"}, beats, [dirty, clean], {}, False, True, mode="salvage")
        self.assertTrue(plan["salvage"])
        self.assertEqual(plan["blocked"], "")
        crops = [library.clip_from_shot(p["shot"], "", plan["salvage"]).get("crop") for p in plan["picks"]]
        self.assertIn({"bottom": library.CROP["bottom"]}, crops)   # đoạn dính chữ bị cắt
        self.assertIn(None, crops)                                 # đoạn sạch giữ nguyên khung

    def test_a_cut_clip_fills_the_frame_instead_of_showing_blurred_bars(self):
        segs = make_videos.clip_segments("x.mp4", {"duration": 10.0, "width": 1080, "height": 1920,
                                                   "has_audio": False, "hdr": False},
                                         [{"start": 0, "end": 3, "crop": {"bottom": 0.22}}])
        self.assertEqual(segs[0][6], {"bottom": 0.22})


class Review(unittest.TestCase):
    """Trước khi dựng, AI soát lại từng cảnh cho khớp đoạn quay và đủ 30–40 giây."""

    def setUp(self):
        self.shots = [{"id": f"s_{i}", "source_id": "s", "start": i * 4.0, "end": i * 4.0 + 4, "length": 4.0,
                       "desc": f"đoạn {i}", "note": "", "thumb": "", "scene_start": 0.0, "scene_end": 40.0,
                       "sub": "", "sub_pos": "none", "marks": "", "sub_ok": True} for i in range(8)]
        self.beats = [{"part": "", "voice": "Lời gốc rất ngắn.", "text": "", "text_pos": "top",
                       "duration": 3, "shot_id": f"s_{i}"} for i in range(4)]
        self.calls = []
        self.real = ai.review_plan

    def tearDown(self):
        ai.review_plan = self.real

    def reviewer(self, beats_out, verdict="sua", note="đã sửa"):
        def fake(script, items, shots, seconds, target=(30, 40), salvage=False):
            self.calls.append(round(seconds))
            return {"verdict": verdict, "note": note, "beats": beats_out}
        ai.review_plan = fake

    def out(self, n, voice="Câu đã viết lại cho khớp cảnh quay, dài vừa đủ nha anh chị.", start=0):
        return [{"from": i, "shot_id": f"s_{i}", "part": "Mở đầu", "voice": voice, "text": "", "text_pos": "top",
                 "duration": 4, "changed": "viết lại cho khớp cảnh" if i == start else ""} for i in range(n)]

    def test_review_rewrites_beats_and_records_what_changed(self):
        self.reviewer(self.out(8))
        plan = batch.plan_beats({"title": "T"}, self.beats, self.shots, {}, True, True)
        self.assertEqual(len(plan["picks"]), 8)
        self.assertEqual([c["kind"] for c in plan["changes"]], ["review"])
        self.assertTrue(plan["picks"][0]["adapted"])
        self.assertEqual(plan["picks"][0]["orig_voice"], "Lời gốc rất ngắn.")
        self.assertEqual(plan["blocked"], "")

    def test_short_script_is_sent_back_until_it_reaches_thirty_seconds(self):
        short = self.out(4, "Ngắn quá.")
        self.reviewer(short)
        library.review_beats({"title": "T"}, self.beats, self.shots)
        self.assertEqual(len(self.calls), 2)  # lần đầu chưa đủ dài nên soát lại lần nữa

    def test_long_enough_script_is_not_sent_back(self):
        self.reviewer(self.out(8))
        result = library.review_beats({"title": "T"}, self.beats, self.shots)
        self.assertEqual(len(self.calls), 1)
        self.assertGreaterEqual(result["seconds"], 30)

    def test_model_saying_the_footage_does_not_work_blocks_the_video(self):
        self.reviewer([], verdict="khong_dung_duoc", note="Kho quay toàn cảnh khác sản phẩm")
        plan = batch.plan_beats({"title": "T"}, self.beats, self.shots, {}, True, True)
        self.assertIn("Kho quay toàn cảnh khác", plan["blocked"])

    def test_ai_failure_keeps_the_original_plan(self):
        def boom(*a, **k):
            raise ai.AIError("hết hạn mức")
        ai.review_plan = boom
        plan = batch.plan_beats({"title": "T"}, self.beats, self.shots, {}, True, True)
        self.assertEqual(len(plan["picks"]), 4)
        self.assertEqual(plan["blocked"], "")
        self.assertTrue(any("Soát lại" in w for w in plan["warnings"]))

    def test_estimate_follows_the_spoken_words(self):
        self.assertAlmostEqual(assemble.plan_seconds([{"voice": " ".join(["từ"] * 120)}]), 30.5, places=1)


class Looks(unittest.TestCase):
    """Phông chữ lấy từ máy, màu chữ chọn sẵn, nhạc riêng upload lên."""

    def test_bundled_font_is_always_available(self):
        families = [f["family"] for f in fonts.system_fonts(refresh=True)]
        self.assertIn("DejaVu Sans", families)
        self.assertTrue(fonts.files_for("DejaVu Sans"))
        self.assertTrue(fonts.system_fonts()[0]["recommended"])  # phông gợi ý xếp lên đầu

    def test_unknown_font_falls_back_to_the_bundled_one(self):
        self.assertEqual(fonts.files_for("Phông Không Có Trên Máy"), [])
        with tempfile.TemporaryDirectory() as tmp:
            folder, family = assemble.fonts_dir("Phông Không Có Trên Máy", tmp)
            self.assertEqual(family, "DejaVu Sans")
            self.assertEqual(folder, make_videos.FONTS_DIR)

    def test_chosen_font_is_copied_next_to_the_bundled_ones(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder, family = assemble.fonts_dir("DejaVu Sans", tmp)
            self.assertEqual(family, "DejaVu Sans")
            self.assertTrue(any(f.lower().endswith((".ttf", ".otf")) for f in os.listdir(folder)))

    def test_colour_becomes_ass_bgr_and_dark_text_gets_a_light_edge(self):
        self.assertEqual(make_videos.ass_color("#FFD24A"), "4AD2FF")
        self.assertEqual(make_videos.ass_color("rác"), "FFFFFF")
        self.assertFalse(make_videos.is_dark("#FFD24A"))
        self.assertTrue(make_videos.is_dark("#111111"))

    def test_text_colour_and_style_reach_the_subtitle_file(self):
        path = os.path.join(_TMP, "mau.ass")
        make_videos.build_ass({**make_videos.DEFAULTS, "text_color": "#FFD24A", "sub_color": "#111111",
                               "text_style": "outline", "captions": [{"start": 0, "end": 1, "text": "x", "pos": "bottom"}]},
                              1080, 1920, 2.0, path)
        with open(path, encoding="utf-8") as f:
            styles = {line.split(",")[0].split(": ")[1]: line for line in f if line.startswith("Style:")}
        self.assertIn("&H004AD2FF", styles["Caption"])          # màu chữ
        self.assertIn("&H00111111", styles["Sub"])              # màu phụ đề
        self.assertEqual(styles["Caption"].split(",")[15], "1")  # BorderStyle 1 = chữ viền, không nền hộp
        self.assertIn("&H00FFFFFF", styles["Sub"].split(",")[5])  # phụ đề màu tối thì viền sáng

    def test_uploaded_music_is_listed_and_paths_outside_are_refused(self):
        folder = os.path.join(store.DATA_DIR, "music")
        os.makedirs(folder, exist_ok=True)
        open(os.path.join(folder, "abc123_nhac tet.mp3"), "wb").close()
        open(os.path.join(folder, "ghi_chu.txt"), "wb").close()
        items = library.music_list()
        self.assertEqual([i["name"] for i in items], ["nhac tet.mp3"])  # chỉ nhận file nhạc
        self.assertTrue(library.music_path("abc123_nhac tet.mp3"))
        self.assertIsNone(library.music_path("../../settings.json"))
        self.assertIsNone(library.music_path("khong_co.mp3"))


if __name__ == "__main__":
    unittest.main()
