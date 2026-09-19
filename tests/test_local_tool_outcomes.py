"""已迁移本地 Tool producer 的 PR2 确定性覆盖。"""

import asyncio
import sys
import types
from enum import IntEnum
from pathlib import Path

from backend.modules.tools.execution import (
    ErrorCategory,
    ExecutionState,
    RetrySafety,
    SideEffectState,
)
from backend.modules.tools.file_search import FileSearchTool
from backend.modules.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from backend.modules.tools.memory_tool import MemoryReadTool, MemorySearchTool, MemoryTool, MemoryWriteTool
from backend.modules.tools.registry import ToolRegistry
from backend.modules.tools.screenshot import ScreenshotTool
from backend.modules.tools.shell import ExecTool
from backend.modules.tools.web import WebFetchTool
from backend.modules.wiki.tool import WikiTool


def run(coro):
    return asyncio.run(coro)


def outcome_for(tool, arguments):
    registry = ToolRegistry()
    registry.register(tool)
    return run(registry.execute_outcome(tool.name, arguments))


def install_fake_scrapling(monkeypatch, basic_fetch, stealth_fetch):
    scrapling = types.ModuleType("scrapling")
    scrapling.__path__ = []
    fetchers = types.ModuleType("scrapling.fetchers")

    class AsyncFetcher:
        @classmethod
        async def get(cls, url, **kwargs):
            return await basic_fetch(url, **kwargs)

    class StealthyFetcher:
        @classmethod
        async def async_fetch(cls, url, **kwargs):
            return await stealth_fetch(url, **kwargs)

    fetchers.AsyncFetcher = AsyncFetcher
    fetchers.StealthyFetcher = StealthyFetcher
    monkeypatch.setitem(sys.modules, "scrapling", scrapling)
    monkeypatch.setitem(sys.modules, "scrapling.fetchers", fetchers)


def test_read_batch_is_authoritative_failure_when_one_file_fails(tmp_path: Path):
    (tmp_path / "ok.txt").write_text("hello\n", encoding="utf-8")
    outcome = outcome_for(ReadFileTool(tmp_path, restrict_to_workspace=False), {"paths": [str(tmp_path / "ok.txt"), str(tmp_path / "missing.txt")]})

    assert outcome.state is ExecutionState.FAILED
    assert outcome.error_category is ErrorCategory.VALIDATION
    assert outcome.retry_safety is RetrySafety.SAFE
    assert outcome.side_effect_state is SideEffectState.NOT_APPLICABLE
    assert "hello" in outcome.display_text
    assert "missing.txt" in outcome.display_text


def test_filesystem_successes_are_structured_and_keep_display_text(tmp_path: Path):
    write = WriteFileTool(tmp_path, restrict_to_workspace=False)
    note = tmp_path / "note.txt"
    write_outcome = outcome_for(write, {"path": str(note), "content": "one"})
    assert write_outcome.state is ExecutionState.SUCCEEDED
    assert write_outcome.display_text == f"Wrote 3 chars to {note}"
    assert write_outcome.retry_safety is RetrySafety.UNSAFE
    assert write_outcome.side_effect_state is SideEffectState.COMMITTED
    assert run(write.execute(path=str(note), content="two")) == f"Wrote 3 chars to {note}"

    edit_outcome = outcome_for(EditFileTool(tmp_path, restrict_to_workspace=False), {"path": str(note), "old_text": "two", "new_text": "three"})
    assert edit_outcome.state is ExecutionState.SUCCEEDED
    assert edit_outcome.side_effect_state is SideEffectState.COMMITTED
    assert outcome_for(ListDirTool(tmp_path, restrict_to_workspace=False), {"path": str(tmp_path)}).state is ExecutionState.SUCCEEDED


def test_file_mutation_pre_and_post_boundary_failures_are_distinguished(tmp_path: Path):
    write = WriteFileTool(tmp_path, restrict_to_workspace=False)
    pre_write = outcome_for(write, {"path": "", "content": "x"})
    assert (pre_write.state, pre_write.side_effect_state) == (ExecutionState.FAILED, SideEffectState.NOT_ATTEMPTED)

    class Parent:
        def mkdir(self, **kwargs):
            return None

    class FailingPath:
        parent = Parent()

        def exists(self):
            return False

        def write_text(self, content, **kwargs):
            raise OSError("write boundary lost")

    write.validator.validate_path = lambda value: FailingPath()
    post_write = outcome_for(write, {"path": "target", "content": "x"})
    assert (post_write.state, post_write.side_effect_state) == (ExecutionState.UNKNOWN_OUTCOME, SideEffectState.UNKNOWN)

    class ExistingParent:
        def mkdir(self, **kwargs):
            raise AssertionError("append preparation must fail before mutation")

    class ExistingFile:
        parent = ExistingParent()

        def exists(self):
            return True

        def read_text(self, **kwargs):
            raise PermissionError("append source cannot be read")

    append = WriteFileTool(tmp_path, restrict_to_workspace=False)
    append.validator.validate_path = lambda value: ExistingFile()
    append_preparation = outcome_for(append, {"path": "target", "content": "x", "mode": "append"})
    assert (append_preparation.state, append_preparation.error_category, append_preparation.side_effect_state) == (
        ExecutionState.FAILED,
        ErrorCategory.PERMISSION,
        SideEffectState.NOT_ATTEMPTED,
    )

    editable = tmp_path / "editable.txt"
    editable.write_text("old", encoding="utf-8")
    edit = EditFileTool(tmp_path, restrict_to_workspace=False)
    pre_edit = outcome_for(edit, {"path": str(editable)})
    assert (pre_edit.state, pre_edit.side_effect_state) == (ExecutionState.FAILED, SideEffectState.NOT_ATTEMPTED)

    original_write_text = Path.write_text

    def fail_only_for_edit(path, text, **kwargs):
        if path == editable:
            raise OSError("edit boundary lost")
        return original_write_text(path, text, **kwargs)

    from pytest import MonkeyPatch
    patch = MonkeyPatch()
    patch.setattr(Path, "write_text", fail_only_for_edit)
    try:
        post_edit = outcome_for(edit, {"path": str(editable), "old_text": "old", "new_text": "new"})
    finally:
        patch.undo()
    assert (post_edit.state, post_edit.side_effect_state) == (ExecutionState.UNKNOWN_OUTCOME, SideEffectState.UNKNOWN)


def test_read_only_file_search_treats_no_matches_as_success(tmp_path: Path):
    outcome = outcome_for(FileSearchTool(tmp_path, restrict_to_workspace=False), {"path": str(tmp_path), "pattern": "*.missing"})
    assert outcome.state is ExecutionState.SUCCEEDED
    assert outcome.retry_safety is RetrySafety.SAFE
    assert outcome.side_effect_state is SideEffectState.NOT_APPLICABLE
    missing = outcome_for(FileSearchTool(tmp_path, restrict_to_workspace=False), {"path": str(tmp_path / "missing")})
    assert (missing.state, missing.error_category) == (ExecutionState.FAILED, ErrorCategory.VALIDATION)


def test_file_search_root_permission_is_not_false_success(tmp_path: Path):
    class DeniedRoot:
        def exists(self):
            return True

        def is_dir(self):
            return True

        def iterdir(self):
            raise PermissionError("root traversal denied")

    tool = FileSearchTool(tmp_path, restrict_to_workspace=False)
    tool.validator.validate_path = lambda value: DeniedRoot()
    outcome = outcome_for(tool, {"path": "authoritative-root"})
    assert (outcome.state, outcome.error_category) == (ExecutionState.FAILED, ErrorCategory.PERMISSION)


class FakeMemory:
    def __init__(self):
        self.entries = []

    def append_entry(self, *, source, content):
        self.entries.append((source, content))
        return len(self.entries)

    def get_line_count(self):
        return len(self.entries)

    def get_stats(self):
        return {"total": len(self.entries)}

    def search(self, keywords, **kwargs):
        return "search-result"

    def get_recent(self, count):
        return "recent"

    def read_lines(self, start, end):
        return "lines"


def test_memory_tools_are_action_aware_and_legacy_subclasses_are_migrated():
    memory = FakeMemory()
    write = outcome_for(MemoryTool(memory), {"action": "write", "content": "remember"})
    search = outcome_for(MemoryTool(memory), {"action": "search", "keywords": "remember"})
    read = outcome_for(MemoryTool(memory), {"action": "read"})
    invalid = outcome_for(MemoryTool(memory), {"action": "write"})
    assert (write.retry_safety, write.side_effect_state) == (RetrySafety.UNSAFE, SideEffectState.COMMITTED)
    assert (search.retry_safety, search.side_effect_state) == (RetrySafety.SAFE, SideEffectState.NOT_APPLICABLE)
    assert (read.retry_safety, read.side_effect_state) == (RetrySafety.SAFE, SideEffectState.NOT_APPLICABLE)
    assert invalid.error_category is ErrorCategory.VALIDATION
    assert outcome_for(MemoryWriteTool(memory), {"content": "legacy"}).state is ExecutionState.SUCCEEDED
    assert outcome_for(MemorySearchTool(memory), {"keywords": "legacy"}).state is ExecutionState.SUCCEEDED
    assert outcome_for(MemoryReadTool(memory), {}).state is ExecutionState.SUCCEEDED


def test_memory_write_failure_after_boundary_is_unknown_outcome():
    class FailingMemory(FakeMemory):
        def append_entry(self, *, source, content):
            raise OSError("memory persistence uncertain")

    outcome = outcome_for(MemoryTool(FailingMemory()), {"action": "write", "content": "remember"})
    assert (outcome.state, outcome.error_category, outcome.side_effect_state) == (
        ExecutionState.UNKNOWN_OUTCOME,
        ErrorCategory.EXECUTION,
        SideEffectState.UNKNOWN,
    )


def test_web_fetch_is_safe_without_output_and_unsafe_with_persistence(tmp_path: Path, monkeypatch):
    tool = WebFetchTool()

    async def fake_fetch(url, max_chars, output_format):
        return {"text": "body", "html": "<p>body</p>", "length": 4, "mode": "fake"}

    monkeypatch.setattr(tool, "_fetch_with_httpx", fake_fetch)
    no_output = outcome_for(tool, {"url": "https://example.test"})
    assert (no_output.retry_safety, no_output.side_effect_state) == (RetrySafety.SAFE, SideEffectState.NOT_APPLICABLE)

    import backend.modules.tools.web as web_module
    target = tmp_path / "saved.txt"
    monkeypatch.setattr(web_module, "resolve_path", lambda value: target)
    persisted = outcome_for(tool, {"url": "https://example.test", "output_path": "saved.txt"})
    assert persisted.state is ExecutionState.SUCCEEDED
    assert (persisted.retry_safety, persisted.side_effect_state) == (RetrySafety.UNSAFE, SideEffectState.COMMITTED)
    assert target.read_text(encoding="utf-8") == "body"
    invalid = outcome_for(tool, {"url": "not-a-url"})
    assert invalid.error_category is ErrorCategory.VALIDATION

    async def offline(url, max_chars, output_format):
        raise ConnectionError("offline")

    monkeypatch.setattr(tool, "_fetch_with_httpx", offline)
    dependency = outcome_for(tool, {"url": "https://example.test"})
    assert (dependency.state, dependency.error_category, dependency.retry_safety) == (ExecutionState.FAILED, ErrorCategory.DEPENDENCY, RetrySafety.SAFE)

    async def timed_out(url, max_chars, output_format):
        raise TimeoutError("request deadline")

    monkeypatch.setattr(tool, "_fetch_with_httpx", timed_out)
    timeout = outcome_for(tool, {"url": "https://example.test"})
    assert (timeout.state, timeout.error_category, timeout.retry_safety) == (ExecutionState.FAILED, ErrorCategory.TIMEOUT, RetrySafety.SAFE)

    async def scrapling_timed_out(url, mode):
        raise TimeoutError("scrapling request deadline exceeded")

    monkeypatch.setattr(web_module, "_fetch_with_scrapling", scrapling_timed_out)
    tool.scrapling_available = True
    scrapling_timeout = outcome_for(tool, {"url": "https://example.test", "mode": "basic"})
    assert (
        scrapling_timeout.state,
        scrapling_timeout.error_category,
        scrapling_timeout.retry_safety,
        scrapling_timeout.side_effect_state,
    ) == (
        ExecutionState.FAILED,
        ErrorCategory.TIMEOUT,
        RetrySafety.SAFE,
        SideEffectState.NOT_APPLICABLE,
    )
    tool.scrapling_available = False

    class Parent:
        def mkdir(self, **kwargs):
            return None

    class FailingTarget:
        parent = Parent()

        def write_text(self, content, **kwargs):
            raise OSError("output write lost")

        def __str__(self):
            return "failing-output"

    monkeypatch.setattr(tool, "_fetch_with_httpx", fake_fetch)
    monkeypatch.setattr(web_module, "resolve_path", lambda value: FailingTarget())
    post_write = outcome_for(tool, {"url": "https://example.test", "output_path": "saved.txt"})
    assert (post_write.state, post_write.side_effect_state) == (ExecutionState.UNKNOWN_OUTCOME, SideEffectState.UNKNOWN)


def test_web_fetch_scrapling_disables_hidden_client_retries(monkeypatch):
    calls = []

    class Response:
        html_content = "<p>body</p>"
        status = 200
        url = "https://example.test"

    async def basic_fetch(url, **kwargs):
        calls.append(("basic", kwargs))
        return Response()

    async def stealth_fetch(url, **kwargs):
        calls.append(("stealth", kwargs))
        return Response()

    install_fake_scrapling(monkeypatch, basic_fetch, stealth_fetch)
    tool = WebFetchTool()
    tool.scrapling_available = True
    assert outcome_for(tool, {"url": "https://example.test", "mode": "basic"}).state is ExecutionState.SUCCEEDED
    assert outcome_for(tool, {"url": "https://example.test", "mode": "stealth"}).state is ExecutionState.SUCCEEDED
    assert [mode for mode, _ in calls] == ["basic", "stealth"]
    assert all(kwargs["retries"] == 0 for _, kwargs in calls)


def test_web_fetch_normalizes_static_and_browser_scrapling_timeouts(monkeypatch):
    class CurlECode(IntEnum):
        OPERATION_TIMEDOUT = 28

    class CurlError(Exception):
        def __init__(self, message, code):
            super().__init__(message)
            self.code = code

    class PatchrightTimeoutError(Exception):
        pass

    curl_cffi = types.ModuleType("curl_cffi")
    curl_cffi.__path__ = []
    curl_const = types.ModuleType("curl_cffi.const")
    curl_const.CurlECode = CurlECode
    curl_module = types.ModuleType("curl_cffi.curl")
    curl_module.CurlError = CurlError
    patchright = types.ModuleType("patchright")
    patchright.__path__ = []
    patchright_api = types.ModuleType("patchright.async_api")
    patchright_api.TimeoutError = PatchrightTimeoutError
    monkeypatch.setitem(sys.modules, "curl_cffi", curl_cffi)
    monkeypatch.setitem(sys.modules, "curl_cffi.const", curl_const)
    monkeypatch.setitem(sys.modules, "curl_cffi.curl", curl_module)
    monkeypatch.setitem(sys.modules, "patchright", patchright)
    monkeypatch.setitem(sys.modules, "patchright.async_api", patchright_api)

    async def basic_timeout(url, **kwargs):
        raise CurlError("static deadline exceeded", CurlECode.OPERATION_TIMEDOUT)

    async def browser_timeout(url, **kwargs):
        raise PatchrightTimeoutError("browser deadline exceeded")

    install_fake_scrapling(monkeypatch, basic_timeout, browser_timeout)
    tool = WebFetchTool()
    tool.scrapling_available = True
    basic = outcome_for(tool, {"url": "https://example.test", "mode": "basic"})
    browser = outcome_for(tool, {"url": "https://example.test", "mode": "stealth"})
    for outcome in (basic, browser):
        assert (
            outcome.state,
            outcome.error_category,
            outcome.retry_safety,
            outcome.side_effect_state,
        ) == (
            ExecutionState.FAILED,
            ErrorCategory.TIMEOUT,
            RetrySafety.SAFE,
            SideEffectState.NOT_APPLICABLE,
        )


def test_screenshot_persistence_uses_explicit_committed_outcome(tmp_path: Path, monkeypatch):
    import backend.modules.tools.screenshot as screenshot_module

    class Capture:
        rgb = b"pixels"
        size = (1, 1)
        width = 1
        height = 1

    class Session:
        monitors = [{"width": 1, "height": 1}]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def grab(self, monitor):
            return Capture()

    mss_module = types.ModuleType("mss")
    mss_module.__path__ = []
    mss_module.mss = Session
    mss_tools = types.ModuleType("mss.tools")
    mss_tools.to_png = lambda rgb, size, output: Path(output).write_bytes(b"png")
    mss_module.tools = mss_tools
    monkeypatch.setitem(sys.modules, "mss", mss_module)
    monkeypatch.setitem(sys.modules, "mss.tools", mss_tools)
    target = tmp_path / "shot.png"
    monkeypatch.setattr(screenshot_module, "resolve_path", lambda value: target)

    outcome = outcome_for(ScreenshotTool(tmp_path), {"mode": "desktop", "output_path": "shot.png"})
    assert outcome.state is ExecutionState.SUCCEEDED
    assert outcome.side_effect_state is SideEffectState.COMMITTED
    assert target.read_bytes() == b"png"

    mss_tools.to_png = lambda rgb, size, output: (_ for _ in ()).throw(OSError("persistence lost"))
    uncertain = outcome_for(ScreenshotTool(tmp_path), {"mode": "desktop", "output_path": "shot.png"})
    assert (uncertain.state, uncertain.side_effect_state) == (ExecutionState.UNKNOWN_OUTCOME, SideEffectState.UNKNOWN)


def test_screenshot_validation_dependency_and_webpage_timeout(tmp_path: Path, monkeypatch):
    import backend.modules.tools.screenshot as screenshot_module

    validation = outcome_for(ScreenshotTool(tmp_path), {"mode": "invalid"})
    assert (validation.state, validation.error_category, validation.side_effect_state) == (
        ExecutionState.FAILED,
        ErrorCategory.VALIDATION,
        SideEffectState.NOT_ATTEMPTED,
    )
    monkeypatch.setitem(sys.modules, "mss", None)
    dependency = outcome_for(ScreenshotTool(tmp_path), {"mode": "desktop"})
    assert (dependency.state, dependency.error_category) == (ExecutionState.FAILED, ErrorCategory.DEPENDENCY)

    class FakePlaywrightTimeoutError(Exception):
        pass

    class Page:
        async def goto(self, *args, **kwargs):
            raise FakePlaywrightTimeoutError()

    class Context:
        async def new_page(self):
            return Page()

    class Browser:
        async def new_context(self, **kwargs):
            return Context()

    class Chromium:
        async def launch(self, **kwargs):
            return Browser()

    class Playwright:
        chromium = Chromium()

    class PlaywrightContext:
        async def __aenter__(self):
            return Playwright()

        async def __aexit__(self, *args):
            return None

    playwright = types.ModuleType("playwright")
    playwright.__path__ = []
    playwright_api = types.ModuleType("playwright.async_api")
    playwright_api.TimeoutError = FakePlaywrightTimeoutError
    playwright_api.async_playwright = lambda: PlaywrightContext()
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.async_api", playwright_api)
    timeout = outcome_for(ScreenshotTool(tmp_path), {"mode": "webpage", "url": "https://example.test", "wait_time": 0})
    assert (timeout.state, timeout.error_category, timeout.side_effect_state) == (
        ExecutionState.FAILED,
        ErrorCategory.TIMEOUT,
        SideEffectState.NOT_ATTEMPTED,
    )


def test_shell_has_no_hidden_retry_and_nonzero_is_not_success(tmp_path: Path, monkeypatch):
    tool = ExecTool(tmp_path)
    calls = 0

    class Process:
        returncode = None

    async def fake_spawn(*args, **kwargs):
        nonlocal calls
        calls += 1
        return Process()

    async def timeout(coro, *args, **kwargs):
        coro.close()
        raise asyncio.TimeoutError()

    import backend.modules.tools.shell as shell_module
    monkeypatch.setattr(shell_module.asyncio, "create_subprocess_shell", fake_spawn)
    monkeypatch.setattr(shell_module, "run_with_monitoring", timeout)
    outcome = outcome_for(tool, {"command": "echo test"})
    assert calls == 1
    assert outcome.state is ExecutionState.UNKNOWN_OUTCOME
    assert outcome.error_category is ErrorCategory.TIMEOUT
    assert outcome.retry_safety is RetrySafety.UNSAFE
    guarded = outcome_for(tool, {"command": "rm -rf forbidden"})
    assert guarded.state is ExecutionState.FAILED
    assert guarded.side_effect_state is SideEffectState.NOT_ATTEMPTED


def test_shell_success_and_nonzero_have_explicit_outcomes(tmp_path: Path):
    tool = ExecTool(tmp_path)
    success = outcome_for(tool, {"command": "printf canonical"})
    nonzero = outcome_for(tool, {"command": "exit 7"})
    assert (success.state, success.side_effect_state) == (ExecutionState.SUCCEEDED, SideEffectState.COMMITTED)
    assert success.display_text == "canonical"
    assert (nonzero.state, nonzero.side_effect_state) == (ExecutionState.UNKNOWN_OUTCOME, SideEffectState.UNKNOWN)


def test_shell_cancellation_and_post_spawn_exception_are_uncertain(tmp_path: Path, monkeypatch):
    import backend.modules.tools.shell as shell_module

    class Process:
        returncode = None

    async def fake_spawn(*args, **kwargs):
        return Process()

    async def cancelled(coro, *args, **kwargs):
        coro.close()
        raise asyncio.CancelledError()

    monkeypatch.setattr(shell_module.asyncio, "create_subprocess_shell", fake_spawn)
    monkeypatch.setattr(shell_module, "run_with_monitoring", cancelled)
    cancellation = outcome_for(ExecTool(tmp_path), {"command": "echo test"})
    assert (cancellation.state, cancellation.error_category, cancellation.side_effect_state) == (
        ExecutionState.UNKNOWN_OUTCOME,
        ErrorCategory.CANCELLATION,
        SideEffectState.UNKNOWN,
    )

    async def failed(coro, *args, **kwargs):
        coro.close()
        raise RuntimeError("collector failed")

    monkeypatch.setattr(shell_module, "run_with_monitoring", failed)
    exception = outcome_for(ExecTool(tmp_path), {"command": "echo test"})
    assert (exception.state, exception.error_category, exception.side_effect_state) == (
        ExecutionState.UNKNOWN_OUTCOME,
        ErrorCategory.EXECUTION,
        SideEffectState.UNKNOWN,
    )


def test_wiki_read_and_mutation_actions_have_explicit_outcomes(tmp_path: Path):
    tool = WikiTool(tmp_path)
    created = outcome_for(tool, {"action": "create", "title": "Entry", "content": "body"})
    assert (created.state, created.retry_safety, created.side_effect_state) == (ExecutionState.SUCCEEDED, RetrySafety.UNSAFE, SideEffectState.COMMITTED)
    read = outcome_for(tool, {"action": "get", "slug": "entry"})
    assert (read.state, read.retry_safety, read.side_effect_state) == (ExecutionState.SUCCEEDED, RetrySafety.SAFE, SideEffectState.NOT_APPLICABLE)
    updated = outcome_for(tool, {"action": "update", "slug": "entry", "content": "new"})
    deleted = outcome_for(tool, {"action": "delete", "slug": "entry"})
    synced = outcome_for(tool, {"action": "sync"})
    assert updated.state is deleted.state is synced.state is ExecutionState.SUCCEEDED
    missing = outcome_for(tool, {"action": "get", "slug": "entry"})
    assert (missing.state, missing.error_category, missing.retry_safety) == (ExecutionState.FAILED, ErrorCategory.VALIDATION, RetrySafety.SAFE)


def test_wiki_post_mutation_exception_preserves_uncertainty(tmp_path: Path, monkeypatch):
    tool = WikiTool(tmp_path)
    monkeypatch.setattr(tool._service, "add_document", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("index unavailable")))
    outcome = outcome_for(tool, {"action": "create", "title": "Entry", "content": "body"})
    assert (outcome.state, outcome.side_effect_state, outcome.retry_safety) == (ExecutionState.UNKNOWN_OUTCOME, SideEffectState.UNKNOWN, RetrySafety.UNSAFE)
