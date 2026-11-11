import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import ig_post  # noqa: E402

F = "https://x.github.io/m/2026-11-11"


class IgPostTest(unittest.TestCase):
    def post(self, data):
        with mock.patch.object(ig_post, "http", return_value=data):
            return ig_post.load_post(F)

    def test_load_post_checks_shape(self):
        kind, urls, cap = self.post({"type": "carousel", "media": ["01.jpg", "02.jpg"], "caption": "c"})
        self.assertEqual((kind, urls, cap), ("carousel", [f"{F}/01.jpg", f"{F}/02.jpg"], "c"))
        for bad in ({"type": "carousel", "media": ["01.jpg"]}, {"type": "image", "media": ["01.png"]},
                    {"type": "reel", "media": ["a.jpg"]}, {"type": "story", "media": ["a.jpg"]},
                    {"type": "image", "media": ["a.jpg"], "caption": "#" * 31}):
            with self.assertRaises(ValueError):
                self.post(bad)

    def test_carousel_publish_order(self):
        calls = []
        def fake(method, url, data=None):
            calls.append((method, url.split("?")[0].rsplit("/", 1)[-1], (data or {}).get("media_type")))
            if "status_code" in url:
                return {"status_code": "FINISHED"}
            if "permalink" in url:
                return {"permalink": "https://instagram.com/p/x"}
            return {"id": f"id{len(calls)}"}
        with mock.patch.object(ig_post, "http", side_effect=fake):
            link = ig_post.publish("H", "IG", "T", "carousel", [f"{F}/1.jpg", f"{F}/2.jpg"], "cap")
        self.assertEqual(link, "https://instagram.com/p/x")
        posts = [c for c in calls if c[0] == "POST"]
        self.assertEqual([p[1] for p in posts], ["media", "media", "media", "media_publish"])
        self.assertEqual(posts[2][2], "CAROUSEL")


if __name__ == "__main__":
    unittest.main()
