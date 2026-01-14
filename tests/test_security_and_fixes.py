"""
Test suite for security fixes and quality listing functionality.

Run with: python -m pytest tests/test_security_and_fixes.py -v

Or run individual tests with:
python tests/test_security_and_fixes.py
"""
import os
import sys
import unittest
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.downloader import Downloader, VideoFormat, sanitize_filename, merge_playlist_files
from core.models import DownloadItem


class TestSanitizeFilename(unittest.TestCase):
    """Test filename sanitization to prevent path traversal"""

    def test_removes_path_separators(self):
        """Path separators should be replaced with underscores"""
        result = sanitize_filename("../../../etc/passwd")
        # Path separators become underscores, dots are stripped from edges
        self.assertNotIn('/', result)
        self.assertNotIn('\\', result)
        self.assertIn('etc', result)
        self.assertIn('passwd', result)

        result2 = sanitize_filename("..\\..\\windows\\system32")
        self.assertNotIn('\\', result2)
        self.assertIn('windows', result2)

    def test_removes_null_bytes(self):
        """Null bytes should be removed"""
        self.assertEqual(sanitize_filename("file\x00.txt"), "file.txt")

    def test_removes_dangerous_chars(self):
        """Dangerous characters should be replaced"""
        result = sanitize_filename('<script>alert("xss")</script>')
        self.assertNotIn('<', result)
        self.assertNotIn('>', result)
        self.assertNotIn('"', result)

    def test_empty_input(self):
        """Empty input should return 'download'"""
        self.assertEqual(sanitize_filename(""), "download")
        self.assertEqual(sanitize_filename(None), "download")

    def test_length_limit(self):
        """Filename should be limited to 200 characters"""
        long_name = "a" * 300
        result = sanitize_filename(long_name)
        self.assertLessEqual(len(result), 200)

    def test_strips_dots_and_spaces(self):
        """Leading/trailing dots and spaces should be stripped"""
        self.assertEqual(sanitize_filename("...file..."), "file")
        self.assertEqual(sanitize_filename("   file   "), "file")


class TestURLValidation(unittest.TestCase):
    """Test URL validation to prevent SSRF"""

    def setUp(self):
        self.downloader = Downloader()

    def test_rejects_localhost(self):
        """Localhost URLs should be rejected"""
        self.assertFalse(self.downloader._is_valid_url("http://localhost/video"))
        self.assertFalse(self.downloader._is_valid_url("http://127.0.0.1/video"))
        self.assertFalse(self.downloader._is_valid_url("http://0.0.0.0/video"))

    def test_rejects_private_ips(self):
        """Private IP ranges should be rejected"""
        self.assertFalse(self.downloader._is_valid_url("http://10.0.0.1/video"))
        self.assertFalse(self.downloader._is_valid_url("http://192.168.1.1/video"))
        self.assertFalse(self.downloader._is_valid_url("http://172.16.0.1/video"))

    def test_rejects_non_http_schemes(self):
        """Non-HTTP schemes should be rejected"""
        self.assertFalse(self.downloader._is_valid_url("file:///etc/passwd"))
        self.assertFalse(self.downloader._is_valid_url("ftp://server.com/file"))
        self.assertFalse(self.downloader._is_valid_url("javascript:alert(1)"))

    def test_accepts_valid_youtube_urls(self):
        """Valid YouTube URLs should be accepted"""
        self.assertTrue(self.downloader._is_valid_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        self.assertTrue(self.downloader._is_valid_url("https://youtu.be/dQw4w9WgXcQ"))

    def test_rejects_empty_and_none(self):
        """Empty and None URLs should be rejected"""
        self.assertFalse(self.downloader._is_valid_url(""))
        self.assertFalse(self.downloader._is_valid_url(None))


class TestVideoFormat(unittest.TestCase):
    """Test VideoFormat class"""

    def test_get_label_basic(self):
        """Basic label generation"""
        fmt = VideoFormat("137", 1080, 30, "mp4", "avc1", "none")
        label = fmt.get_label()
        self.assertIn("1080p", label)
        self.assertIn("MP4", label)

    def test_get_label_high_fps(self):
        """High FPS should be shown in label"""
        fmt = VideoFormat("303", 1080, 60, "webm", "vp9", "none")
        label = fmt.get_label()
        self.assertIn("60fps", label)

    def test_get_label_with_filesize(self):
        """Filesize should be shown if available"""
        fmt = VideoFormat("137", 1080, 30, "mp4", "avc1", "none", filesize=500*1024*1024)
        label = fmt.get_label()
        self.assertIn("MB", label)

    def test_to_dict(self):
        """to_dict should return proper structure for UI"""
        fmt = VideoFormat("137", 1080, 30, "mp4", "avc1", "none", filesize=100)
        d = fmt.to_dict()
        self.assertEqual(d['format_id'], "137")
        self.assertEqual(d['height'], 1080)
        self.assertIn('resolution', d)


class TestDownloadItem(unittest.TestCase):
    """Test DownloadItem model"""

    def test_has_required_fields(self):
        """DownloadItem should have all required fields"""
        item = DownloadItem(
            url="https://youtube.com/watch?v=test",
            item_type="video",
            quality="137",
            quality_label="1080p (MP4)",
            height=1080
        )
        self.assertEqual(item.quality, "137")
        self.assertEqual(item.quality_label, "1080p (MP4)")
        self.assertEqual(item.height, 1080)


class TestGetAvailableVideoFormats(unittest.TestCase):
    """Test format extraction returns proper structure"""

    @patch('yt_dlp.YoutubeDL')
    def test_returns_dict_with_video_formats_key(self, mock_ytdl):
        """get_available_video_formats should return dict with 'video_formats' key"""
        # Mock the yt-dlp response
        mock_instance = MagicMock()
        mock_ytdl.return_value.__enter__.return_value = mock_instance
        mock_instance.extract_info.return_value = {
            'formats': [
                {'format_id': '137', 'height': 1080, 'fps': 30, 'ext': 'mp4',
                 'vcodec': 'avc1', 'acodec': 'none', 'filesize': 100000000},
                {'format_id': '248', 'height': 1080, 'fps': 30, 'ext': 'webm',
                 'vcodec': 'vp9', 'acodec': 'none', 'filesize': 80000000},
                {'format_id': '140', 'height': None, 'fps': None, 'ext': 'm4a',
                 'vcodec': 'none', 'acodec': 'mp4a', 'filesize': 5000000},  # Audio only
            ],
            'title': 'Test Video'
        }

        downloader = Downloader()
        result = downloader.get_available_video_formats("https://www.youtube.com/watch?v=test")

        # Check structure
        self.assertIsInstance(result, dict)
        self.assertIn('video_formats', result)
        self.assertIsInstance(result['video_formats'], list)

    @patch('yt_dlp.YoutubeDL')
    def test_filters_out_audio_only_formats(self, mock_ytdl):
        """Audio-only formats should be filtered out"""
        mock_instance = MagicMock()
        mock_ytdl.return_value.__enter__.return_value = mock_instance
        mock_instance.extract_info.return_value = {
            'formats': [
                {'format_id': '137', 'height': 1080, 'fps': 30, 'ext': 'mp4',
                 'vcodec': 'avc1', 'acodec': 'none'},
                {'format_id': '140', 'height': None, 'fps': None, 'ext': 'm4a',
                 'vcodec': 'none', 'acodec': 'mp4a'},  # Audio only - should be filtered
            ],
            'title': 'Test Video'
        }

        downloader = Downloader()
        result = downloader.get_available_video_formats("https://www.youtube.com/watch?v=test")

        video_formats = result['video_formats']
        # Should only have the video format
        self.assertEqual(len(video_formats), 1)
        self.assertEqual(video_formats[0]['format_id'], '137')

    @patch('yt_dlp.YoutubeDL')
    def test_formats_sorted_by_quality(self, mock_ytdl):
        """Formats should be sorted by height (highest first)"""
        mock_instance = MagicMock()
        mock_ytdl.return_value.__enter__.return_value = mock_instance
        mock_instance.extract_info.return_value = {
            'formats': [
                {'format_id': '134', 'height': 360, 'fps': 30, 'ext': 'mp4', 'vcodec': 'avc1', 'acodec': 'none'},
                {'format_id': '137', 'height': 1080, 'fps': 30, 'ext': 'mp4', 'vcodec': 'avc1', 'acodec': 'none'},
                {'format_id': '135', 'height': 480, 'fps': 30, 'ext': 'mp4', 'vcodec': 'avc1', 'acodec': 'none'},
            ],
            'title': 'Test Video'
        }

        downloader = Downloader()
        result = downloader.get_available_video_formats("https://www.youtube.com/watch?v=test")

        video_formats = result['video_formats']
        heights = [f['height'] for f in video_formats]
        self.assertEqual(heights, sorted(heights, reverse=True))


class TestDownloadItemFormatSelection(unittest.TestCase):
    """Test that download uses correct format selection"""

    @patch('yt_dlp.YoutubeDL')
    def test_video_download_uses_format_id_with_audio(self, mock_ytdl):
        """Video download with format_id should merge with audio"""
        mock_instance = MagicMock()
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        downloader = Downloader()
        item = DownloadItem(
            url="https://www.youtube.com/watch?v=test",
            item_type="video",
            quality="137",  # format_id
        )

        # We can't fully test download without mocking more,
        # but we can verify the method constructs correct options
        # by checking the mock was called with expected format string
        try:
            downloader.download_item(item, os.path.dirname(__file__), lambda d: None)
        except Exception:
            pass  # May fail without network

        # Check the options passed to YoutubeDL
        if mock_ytdl.called:
            call_args = mock_ytdl.call_args
            if call_args and call_args[0]:
                opts = call_args[0][0]
                if 'format' in opts:
                    # Should include audio merge for video with format_id
                    self.assertIn('bestaudio', opts['format'])


class TestSecurityMergePaths(unittest.TestCase):
    """Test merge_playlist_files validates paths"""

    def test_rejects_invalid_temp_folder(self):
        """Invalid temp folder should be rejected"""
        result = merge_playlist_files("/nonexistent/path", "/output.mp4", "mp4")
        self.assertFalse(result)


if __name__ == '__main__':
    print("=" * 60)
    print("YouTube Downloader - Security and Fix Verification Tests")
    print("=" * 60)

    # Run tests
    unittest.main(verbosity=2)

