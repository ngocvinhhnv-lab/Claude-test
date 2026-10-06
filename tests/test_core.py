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
from app import ai, assemble, batch, docs, fonts, library, store  # noqa: E402


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
