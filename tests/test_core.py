import asyncio
import os
import pytest
from jarvis.config import Settings, validate_endpoint
from jarvis.security import SecretVault, FilePolicy, scrub
from jarvis.storage import Store
from jarvis.session import Session, State, control_phrase
from jarvis.engine import Engine, bounded_context
from jarvis.providers import Reply

async def yes(*args):
    return True

async def no(*args):
    return False

def test_storage_roundtrip(tmp_path, root):
    store = Store(tmp_path / "data.sqlite")
    settings = Settings(model="selected-model", approved_folders=[str(root)], remember_history=True)
    store.save_settings(settings)
    assert Store(store.path).settings() == settings
    store.save_memory("ASH prefers concise replies")
    cid = store.new_conversation()
    store.append(cid, "user", "नमस्ते Jarvis")
    store.append(cid, "assistant", "Hello ASH")
    assert store.messages(cid)[0]["content"] == "नमस्ते Jarvis"
    assert store.conversations()[0][1] == "नमस्ते Jarvis"
    store.delete_conversation(cid)
    assert not store.messages(cid)
    store.clear()
    assert not store.memories() and store.settings() == Settings()

def test_commands_and_retention(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    store.save_command("Metrics", "system_info", {})
    cid = store.new_conversation()
    store.append(cid, "user", "old")
    with store.connection() as db:
        db.execute("UPDATE messages SET created=1")
    store.prune(30)
    assert not store.conversations()
    assert store.commands()[0][1] == "Metrics"
    store.delete_command(store.commands()[0][0])
    assert not store.commands()

@pytest.mark.parametrize("url", ["http://api.example.com", "https://user:secret@example.com", "https://example.com?key=secret", "file:///tmp/key"])
def test_invalid_endpoints(url):
    with pytest.raises(ValueError):
        validate_endpoint(url)

def test_file_boundary(root, tmp_path):
    policy = FilePolicy([str(root)], root / "private")
    valid = root / "code.py"
    valid.write_text("print('ASH')")
    assert policy.check(str(valid)) == valid
    for value in (tmp_path / "other.txt", root / ".." / "other.txt", root / ".env", root / "private" / "db.sqlite", root / ".ssh" / "id_rsa", root / ".npmrc", root / ".git" / "config"):
        with pytest.raises((PermissionError, FileNotFoundError)):
            policy.check(str(value), False)
    with pytest.raises(PermissionError):
        policy.check("relative.txt", False)

@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI")
def test_dpapi_encrypts_and_binds_endpoint(tmp_path):
    vault = SecretVault(tmp_path)
    secret = "test-only-not-a-real-key-12345"
    vault.set("chat:gemini", "https://google.example", secret)
    assert vault.get("chat:gemini", "https://google.example") == secret
    assert vault.get("chat:gemini", "https://other.example") == ""
    assert secret.encode() not in next(vault.directory.glob("*.bin")).read_bytes()
    vault.clear()
    assert vault.get("chat:gemini", "https://google.example") == ""

def test_redaction():
    assert "sk-12345678901234567890" not in scrub("key sk-12345678901234567890")
    assert "hunter2" not in scrub("password=hunter2")

async def test_denial_and_no_overwrite(registry, root):
    target = root / "hello.txt"
    args = {"path": str(target), "content": "hello ASH"}
    assert not (await registry.execute("create_text_file", args, no))["ok"]
    assert not target.exists()
    assert (await registry.execute("create_text_file", args, yes))["ok"]
    assert not (await registry.execute("create_text_file", args, yes))["ok"]
    assert target.read_text() == "hello ASH"

async def test_read_search_safe_path(registry, root, tmp_path):
    file = root / "sample.py"
    file.write_text("# untrusted\nprint('ASH')")
    result = await registry.execute("read_file", {"path": str(file)}, yes)
    assert "untrusted_file_content" in result["result"]
    result = await registry.execute("search_files", {"directory": str(root), "query": "sample"}, yes)
    assert result["result"]["files"] == [str(file)]
    assert not (await registry.execute("create_folder", {"path": str(tmp_path / "outside")}, yes))["ok"]

async def test_argument_validation(registry):
    assert not (await registry.execute("shell", {"command": "anything"}, yes))["ok"]
    assert not (await registry.execute("open_app", {"app": "vscode", "command": "bad"}, yes))["ok"]
    assert not (await registry.execute("volume", {"action": "up", "steps": True}, yes))["ok"]
    assert not (await registry.execute("open_app", {"app": "powershell"}, yes))["ok"]

async def test_disabled_tool(registry):
    registry.settings.disabled_tools = ["system_info"]
    assert not (await registry.execute("system_info", {}, yes))["ok"]
    registry.settings.developer_mode = False
    assert "dev_command" not in [t["function"]["name"] for t in registry.schemas()]

async def test_sleep_during_approval_blocks_write(registry, root):
    session = Session()
    session.wake()
    token = session.generation
    entered, release = asyncio.Event(), asyncio.Event()
    async def approval(tool, args):
        entered.set()
        await release.wait()
        return True
    file = root / "must-not-exist.txt"
    task = asyncio.create_task(registry.execute("create_text_file", {"path": str(file), "content": "bad"}, approval, lambda: session.require(token)))
    await entered.wait()
    session.sleep()
    session.wake()
    release.set()
    result = await task
    assert not result["ok"] and not file.exists()

async def test_real_system_metrics(registry):
    result = await registry.execute("system_info", {}, no)
    assert result["ok"] and 0 <= result["result"]["ram_percent"] <= 100
    assert "local_time" in (await registry.execute("current_time", {}, no))["result"]

@pytest.mark.parametrize("text", ["Wake up, Jarvis.", "Hey Jarvis, wake up", "Jarvis, activate", "Jarvis, online", "Hey Jarvis"])
def test_wake_phrases(text):
    assert control_phrase(text) == "wake"

@pytest.mark.parametrize("text", ["Jarvis, go to sleep", "Jarvis, sleep", "Jarvis, standby", "Jarvis, go offline", "Go to sleep, Jarvis"])
def test_sleep_phrases(text):
    assert control_phrase(text) == "sleep"

def test_session_repeat_wake_hard_mute():
    session = Session()
    assert session.state == State.SLEEPING and not session.valid(0)
    assert session.wake()
    token = session.generation
    assert not session.wake() and session.generation == token
    session.transition(token, State.THINKING)
    session.sleep()
    assert not session.valid(token)
    session.mute(True)
    assert not session.wake(from_voice=True)
    session.mute(False)
    assert session.wake(from_voice=True) and not session.valid(token)
    assert control_phrase("Explain how to wake up Jarvis") is None

class Vault:
    def get(self, *args):
        return "fake-test-key"

async def test_late_response_never_runs_tools(tmp_path, registry):
    started, release = asyncio.Event(), asyncio.Event()
    class SlowProvider:
        def __init__(self, *args):
            pass
        async def complete(self, messages, tools, callback):
            started.set()
            await release.wait()
            return Reply(calls=[{"id": "call1", "type": "function", "function": {"name": "system_info", "arguments": "{}"}}])
    session = Session()
    session.wake()
    token = session.generation
    audits = []
    engine = Engine(Settings(), Vault(), Store(tmp_path / "db"), registry, SlowProvider)
    task = asyncio.create_task(engine.chat([{"role": "user", "content": "metrics"}], yes, lambda x: None, lambda x: None, lambda *x: audits.append(x), lambda: session.require(token)))
    await started.wait()
    session.sleep()
    release.set()
    with pytest.raises(PermissionError):
        await task
    assert not audits

async def test_sleep_prevents_api(tmp_path, registry):
    calls = []
    class Provider:
        def __init__(self, *args):
            calls.append("constructed")
    session = Session()
    engine = Engine(Settings(), Vault(), Store(tmp_path / "db"), registry, Provider)
    with pytest.raises(PermissionError):
        await engine.chat([], None, None, None, None, lambda: session.require(0))
    assert not calls

def test_context_bounded():
    result = bounded_context([{"role": "user", "content": "old" * 100}, {"role": "assistant", "content": "old"}, {"role": "user", "content": "new"}], 10)
    assert result == [{"role": "user", "content": "new"}]
