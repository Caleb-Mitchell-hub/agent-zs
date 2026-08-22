import re
import unittest
from pathlib import Path


FRONTEND_PATH = Path(__file__).parents[1] / "app" / "routers" / "frontend.py"


def main_page_html() -> str:
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    match = re.search(
        r'@router\.get\("/", response_class=HTMLResponse\).*?return r"""(.*?)"""',
        source,
        re.DOTALL,
    )
    if not match:
        raise AssertionError("main frontend HTML was not found")
    return match.group(1)


class FrontendChatContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = main_page_html()

    def test_chat_shell_has_fixed_viewport_and_scrollable_message_region(self):
        self.assertRegex(self.html, r"\.main\s*\{[^}]*height:\s*100vh;")
        self.assertRegex(self.html, r"\.main\s*\{[^}]*min-height:\s*0;")
        self.assertRegex(self.html, r"\.chat-box\s*\{[^}]*overflow-y:\s*auto;")
        self.assertIn("scrollChatToBottom", self.html)

    def test_send_reloads_saved_session_once_after_stream_finishes(self):
        self.assertEqual(self.html.count("await openSession(activeSessionId);"), 1)
        self.assertIn("loadSessionList();", self.html)

    def test_conversation_cache_fallback_is_present(self):
        self.assertIn("cacheConversationMessage", self.html)
        self.assertIn("loadCachedConversation", self.html)
        self.assertIn("mergeCachedSessions", self.html)

    def test_collapsed_drawer_uses_topbar_control_without_brand_or_rail(self):
        topbar = re.search(r'<header class="topbar">(.*?)</header>', self.html, re.DOTALL)
        self.assertIsNotNone(topbar)
        self.assertIn('id="drawerRailBtn"', topbar.group(1))
        self.assertNotIn('id="drawerRail"', self.html)
        self.assertNotIn('.drawer-rail', self.html)
        self.assertNotRegex(self.html, r'<div class="brand">')


if __name__ == "__main__":
    unittest.main()
