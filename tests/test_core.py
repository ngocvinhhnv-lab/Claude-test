"""Kiểm thử nhanh các phần dễ hỏng của app (không cần ffmpeg, mạng hay API key).

Chạy:  python -m unittest discover -s tests -v
"""

import importlib.util
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
from app import ai, assemble, batch, docs, library, store  # noqa: E402


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
        out = assemble.fit_clip({"start": 0.0, "end": 12.0}, self.source, 8.0)
        self.assertEqual((out["start"], out["end"]), (0.0, 8.0))
        self.assertNotIn("speed", out)

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
        return batch.plan_beats(self.script, self.beats, self.shots, {}, True, adapt)

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


if __name__ == "__main__":
    unittest.main()
