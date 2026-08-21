import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from vision_manager import VisionManager  # noqa: E402


class AtlasVisionTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "atlas": {
                "api_key": "",
                "model": "qwen/qwen3-vl-235b-a22b-thinking",
                "base_url": "https://api.atlascloud.ai/v1/chat/completions",
            }
        }

    @patch("vision_manager.requests.post")
    def test_atlas_uses_environment_key_and_openai_image_payload(self, post):
        response = Mock()
        response.json.return_value = {
            "choices": [{"message": {"content": "A test image"}}]
        }
        post.return_value = response

        with patch.dict(os.environ, {"ATLASCLOUD_API_KEY": "test-key"}):
            result = VisionManager(self.config).analyze(
                prompt="Describe this image",
                images=["https://example.com/image.png"],
                model="atlas",
            )

        self.assertEqual(result["choices"][0]["message"]["content"], "A test image")
        post.assert_called_once()
        url = post.call_args.args[0]
        kwargs = post.call_args.kwargs
        self.assertEqual(url, "https://api.atlascloud.ai/v1/chat/completions")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(kwargs["timeout"], 120)
        self.assertEqual(
            kwargs["json"]["messages"][0]["content"][0],
            {
                "type": "image_url",
                "image_url": {"url": "https://example.com/image.png"},
            },
        )

    @patch("vision_manager.requests.post")
    def test_atlas_rejects_video_input_before_request(self, post):
        with patch.dict(os.environ, {"ATLASCLOUD_API_KEY": "test-key"}):
            with self.assertRaisesRegex(ValueError, "仅支持图片输入"):
                VisionManager(self.config).analyze(
                    prompt="Describe this video",
                    videos=["https://example.com/video.mp4"],
                    model="atlas",
                )

        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
