from app.services.browser import USER_AGENT, BrowserService


class FakePage:
    def __init__(self) -> None:
        self.closed = False

    def is_closed(self) -> bool:
        return self.closed


class FakeContext:
    def __init__(self, page: FakePage) -> None:
        self.pages = [page]


async def test_app_browser_restores_saved_edge_user_agent():
    captured = {}

    class Context:
        def set_default_timeout(self, value):
            pass

        def set_default_navigation_timeout(self, value):
            pass

    class Chromium:
        async def launch_persistent_context(self, **kwargs):
            captured.update(kwargs)
            return Context()

    class Playwright:
        chromium = Chromium()

    browser = BrowserService()
    browser._playwright = Playwright()
    await browser._open_context("taobao_profile", True)
    assert captured["user_agent"] == USER_AGENT
    assert captured["headless"] is True


async def test_resident_session_reuses_headed_context_and_page(monkeypatch):
    browser = BrowserService()
    page = FakePage()
    context = FakeContext(page)
    calls = []

    async def open_context(profile_dir: str, headless: bool):
        calls.append((profile_dir, headless))
        return context

    monkeypatch.setattr(browser, "_open_context", open_context)

    async with browser.resident_session("jd_profile") as first:
        assert first is page
    async with browser.resident_session("jd_profile") as second:
        assert second is page

    assert calls == [("jd_profile", False), ("jd_profile", False)]


async def test_resident_session_replaces_closed_tab(monkeypatch):
    browser = BrowserService()
    old_page = FakePage()
    new_page = FakePage()
    context = FakeContext(old_page)

    async def open_context(profile_dir: str, headless: bool):
        return context

    monkeypatch.setattr(browser, "_open_context", open_context)
    async with browser.resident_session("jd_profile"):
        pass
    old_page.closed = True

    async def create_page():
        context.pages.append(new_page)
        return new_page

    context.new_page = create_page
    async with browser.resident_session("jd_profile") as page:
        assert page is new_page
