from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import json

from PIL import Image
from scripts.update_value_chain_logo_cache import decode_image, logo_background, logo_canvas_color, logo_candidate_score, main, normalize_domain


class CompanyLogoTests(unittest.TestCase):
    def png(self, color=(12, 80, 150, 255), size=(32, 32)):
        output = BytesIO()
        Image.new("RGBA", size, color).save(output, "PNG")
        return output.getvalue()

    def test_domain_removes_path_and_www(self):
        self.assertEqual(normalize_domain("https://www.samsung.com/sec/"), "samsung.com")
        self.assertEqual(normalize_domain("www.ips.co.kr"), "ips.co.kr")
        self.assertEqual(normalize_domain(""), "")

    def test_valid_png(self):
        self.assertEqual(decode_image("image/png", self.png()).size, (32, 32))

    def test_prefers_large_wordmark_to_tiny_icon(self):
        small = logo_candidate_score({"type": "icon", "theme": "light"}, {"width": 57, "height": 57})
        large = logo_candidate_score({"type": "logo", "theme": "dark"}, {"width": 800, "height": 200})
        self.assertGreater(large, small)

    def test_keeps_retina_resolution_without_upscaling(self):
        self.assertEqual(decode_image("image/png", self.png(size=(1200, 600))).size, (768, 384))
        self.assertEqual(decode_image("image/png", self.png(size=(57, 57))).size, (57, 57))

    def test_rejects_html_even_with_successful_http(self):
        with self.assertRaises(ValueError):
            decode_image("text/html", b"<html>" + b"x" * 500)

    def test_rejects_fake_image_content(self):
        with self.assertRaises(OSError):
            decode_image("image/png", b"<html>" + b"x" * 500)

    def test_rejects_tiny_image(self):
        with self.assertRaises(ValueError):
            decode_image("image/png", self.png(size=(1, 1)))

    def test_rejects_fully_transparent_image(self):
        with self.assertRaises(ValueError):
            decode_image("image/png", self.png(color=(0, 0, 0, 0)))

    def test_solid_logo_background_matches_canvas(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "logo.png"
            Image.new("RGBA", (32, 32), (0, 0, 0, 255)).save(path)
            self.assertEqual(logo_canvas_color(path), "#000000")

    def test_white_transparent_logo_uses_dark_plate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "logo.png"
            image = Image.new("RGBA", (32, 32))
            image.paste((255, 255, 255, 255), (8, 8, 24, 24))
            image.save(path)
            self.assertEqual(logo_background(path), "dark")

    def test_missing_key_skips_without_network(self):
        with patch.dict("os.environ", {}, clear=True), patch("sys.argv", ["logos"]), patch("requests.get") as get:
            main()
            get.assert_not_called()

    def test_rate_limit_preserves_cached_logo(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "companies.json").write_text(json.dumps([{"id": "test", "name": "Test", "domain": "example.com"}]))
            original = {"provider": "Brandfetch", "companies": {"test": {"src": "/company-logos/test.png", "domain": "example.com"}}}
            (root / "logos.json").write_text(json.dumps(original))
            (root / "test.png").write_bytes(self.png())
            with patch("scripts.update_value_chain_logo_cache.DATA", root), patch("scripts.update_value_chain_logo_cache.ASSETS", root), patch.dict("os.environ", {"BRANDFETCH_API_KEY": "test"}), patch("sys.argv", ["logos", "--refresh"]), patch("requests.get") as get:
                get.return_value.status_code = 429
                main()
            self.assertEqual(json.loads((root / "logos.json").read_text()), original)
            self.assertEqual((root / "test.png").read_bytes(), self.png())


if __name__ == "__main__":
    unittest.main()
