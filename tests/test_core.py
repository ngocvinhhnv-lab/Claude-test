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
from app import ai, assemble, batch, library, store  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
