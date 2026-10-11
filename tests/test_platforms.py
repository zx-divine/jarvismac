from pathlib import Path
from types import SimpleNamespace
import ctypes
import pytest
from jarvis.platforms import MacAdapter, WindowsAdapter
from jarvis.security import SecretVault
from jarvis.config import Settings
from jarvis.tools import Registry
from jarvis.keychain import MacKeychain, NOT_FOUND

def test_mac_launch_fixed_bundle_and_project_arguments(tmp_path):
    calls = []
    adapter = MacAdapter(run=lambda argv, **kw: calls.append((argv, kw)) or SimpleNamespace(returncode=0))
    adapter.open_app("calculator")
    assert calls[0][0] == ["/usr/bin/open", "-b", "com.apple.calculator"]
    folder = str(tmp_path / "project with ; characters")
    adapter.open_project(folder, "vscode")
    assert calls[-1][0][-2:] == ["--", folder]
    assert not calls[-1][1]["shell"]
    with pytest.raises(ValueError):
        adapter.open_app("Terminal")

def test_mac_volume_and_media_are_allowlisted():
    calls = []
    adapter = MacAdapter(run=lambda argv, **kw: calls.append(argv) or SimpleNamespace(returncode=0))
    adapter.volume("up", 2)
    assert "(12)" in calls[-1][-1]
    adapter.media("next")
    assert 'application "Music"' in calls[-1][-1] and "next track" in calls[-1][-1]
    for action, steps in (("execute", 1), ("up", True), ("up", 100)):
        with pytest.raises(ValueError):
            adapter.volume(action, steps)

def test_mac_denied_os_permission_does_not_claim_success():
    adapter = MacAdapter(run=lambda *a, **kw: SimpleNamespace(returncode=1))
    with pytest.raises(RuntimeError, match="permission"):
        adapter.open_app("settings")

def test_mac_power_delay_and_abort_only_own_child():
    calls = []
    class Child:
        stopped = False
        def poll(self):
            return 0 if self.stopped else None
        def terminate(self):
            self.stopped = True
        def wait(self, timeout):
            return 0
    child = Child()
    adapter = MacAdapter(popen=lambda argv, **kw: calls.append(argv) or child)
    adapter.power("restart")
    assert calls[0][2] == "delay 60"
    with pytest.raises(RuntimeError):
        adapter.power("shutdown")
    adapter.close()
    assert child.stopped and adapter.pending_power is None
    with pytest.raises(ValueError):
        adapter.power("sudo")

async def test_mac_actions_still_require_registry_consent(tmp_path):
    calls = []
    adapter = MacAdapter(run=lambda *a, **kw: calls.append(a) or SimpleNamespace(returncode=0))
    registry = Registry(Settings(), tmp_path, platform_adapter=adapter)
    async def deny(*args):
        return False
    result = await registry.execute("open_app", {"app": "calculator"}, deny)
    assert not result["ok"] and not calls

def test_windows_adapter_preserves_windows_dispatch():
    calls = []
    owner = SimpleNamespace(_windows_open_app=lambda app: calls.append(app) or "Windows")
    assert WindowsAdapter(owner).open_app("calculator") == "Windows"
    assert calls == ["calculator"]

def test_mac_vault_endpoint_isolation_no_disk_secret(tmp_path):
    class FakeKeychain:
        data = {}
        def get(self, account):
            return self.data.get(account, "")
        def set(self, account, secret):
            self.data[account] = secret
        def delete(self, account=None):
            if account is None:
                self.data.clear()
            else:
                self.data.pop(account, None)
    vault = SecretVault(tmp_path, keychain=FakeKeychain(), platform_name="darwin")
    vault.set("chat:gemini", "https://example.test", "dummy-not-a-real-key")
    assert vault.get("chat:gemini", "https://example.test") == "dummy-not-a-real-key"
    assert vault.get("chat:gemini", "https://other.test") == ""
    assert not list(tmp_path.iterdir())
    vault.clear()
    assert not vault.get("chat:gemini", "https://example.test")

def test_native_secitem_get_notfound_and_data_release():
    backend = MacKeychain.__new__(MacKeychain)
    backend.query = lambda *args, **kw: 123
    released = []
    data = ctypes.create_string_buffer(b"dummy")
    backend.cf = SimpleNamespace(CFRelease=lambda value: released.append(value), CFDataGetBytePtr=lambda result: ctypes.addressof(data), CFDataGetLength=lambda result: 5)
    backend.sec = SimpleNamespace(SecItemCopyMatching=lambda *args: NOT_FOUND)
    assert backend.get("account") == ""
    assert released == [123]
    def found(query, result):
        result._obj.value = ctypes.addressof(data)
        return 0
    backend.sec.SecItemCopyMatching = found
    assert backend.get("account") == "dummy"
    assert len(released) == 3

def test_keychain_rejects_denied_access_without_plaintext():
    with pytest.raises(RuntimeError, match="OSStatus -25293"):
        MacKeychain.check(-25293)

def test_macos_data_location(monkeypatch, tmp_path):
    import jarvis.config as config
    monkeypatch.delenv("JARVIS_DATA_DIR", raising=False)
    monkeypatch.setattr(config.sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert config.data_dir() == tmp_path / "Library/Application Support/ASH-JARVIS"

def test_model_resource_path_source(monkeypatch, tmp_path):
    import jarvis.config as config
    source = tmp_path / "_internal/jarvis/config.py"
    model = tmp_path / "_internal/models/vosk-model-small-en-us-0.15"
    model.mkdir(parents=True)
    monkeypatch.setattr(config, "__file__", str(source))
    assert config.default_voice_model() == str(model)

def test_no_windows_api_on_mac_adapter_path(monkeypatch, tmp_path):
    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kw: pytest.fail("Windows DLL on Mac"), raising=False)
    calls = []
    adapter = MacAdapter(run=lambda argv, **kw: calls.append(argv) or SimpleNamespace(returncode=0))
    adapter.open_app("explorer")
    assert calls[0][-1] == "com.apple.finder"
