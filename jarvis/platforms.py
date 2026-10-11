"""Platform actions behind the same approved, allowlisted tool registry."""
import ctypes
import subprocess
import sys
from pathlib import Path

class WindowsAdapter:
    def __init__(self, owner):
        self.owner = owner
    def open_app(self, app):
        return self.owner._windows_open_app(app)
    def open_project(self, path, editor):
        return self.owner._windows_open_project(path, editor)
    def volume(self, action, steps):
        return self.owner._windows_volume(action, steps)
    def media(self, action):
        return self.owner._windows_media(action)
    def power(self, action):
        return self.owner._windows_power(action)
    def screenshot(self, path):
        return self.owner._native_screenshot(path)
    def close(self):
        pass

class MacAdapter:
    APPS = {"vscode": "com.microsoft.VSCode", "chrome": "com.google.Chrome", "edge": "com.microsoft.edgemac", "explorer": "com.apple.finder", "settings": "com.apple.systempreferences", "notepad": "com.apple.TextEdit", "calculator": "com.apple.calculator"}

    def __init__(self, run=None, popen=None):
        self.run, self.popen = run or subprocess.run, popen or subprocess.Popen
        self.pending_power = None

    def checked(self, argv):
        result = self.run(argv, shell=False, capture_output=True, timeout=15)
        if result.returncode != 0:
            raise RuntimeError("macOS action failed. Check app installation and System Settings > Privacy & Security > Automation permissions. No OS permission is bypassed.")
        return result

    def open_app(self, app):
        if app not in self.APPS:
            raise ValueError("Application is not allowlisted.")
        self.checked(["/usr/bin/open", "-b", self.APPS[app]])
        return "Launch request sent to macOS; application readiness is not verified."

    def open_project(self, path, editor):
        if editor not in {"explorer", "vscode"}:
            raise ValueError("Editor is not allowlisted.")
        argv = ["/usr/bin/open"]
        if editor == "vscode":
            argv += ["-b", self.APPS["vscode"]]
        self.checked([*argv, "--", path])
        return "Approved folder passed to Finder or VS Code."

    def volume(self, action, steps):
        if type(steps) is not int or not 1 <= steps <= 10:
            raise ValueError("Volume steps must be 1–10.")
        if action == "mute":
            script = "set volume output muted (not (output muted of (get volume settings)))"
        elif action in {"up", "down"}:
            delta = steps * (6 if action == "up" else -6)
            script = f"set v to (output volume of (get volume settings)) + ({delta})\nif v < 0 then set v to 0\nif v > 100 then set v to 100\nset volume output volume v"
        else:
            raise ValueError("Volume action is not allowlisted.")
        self.checked(["/usr/bin/osascript", "-e", script])
        return "Volume request sent to macOS."

    def media(self, action):
        commands = {"play_pause": "playpause", "next": "next track", "previous": "previous track", "stop": "stop"}
        if action not in commands:
            raise ValueError("Media action is not allowlisted.")
        script = 'if application "Music" is running then\n tell application "Music" to ' + commands[action] + '\nelse\n error "Open Music first"\nend if'
        self.checked(["/usr/bin/osascript", "-e", script])
        return "Playback request sent to the running Music application."

    def power(self, action):
        if action == "abort":
            if self.pending_power and self.pending_power.poll() is None:
                self.pending_power.terminate()
                self.pending_power.wait(timeout=5)
                self.pending_power = None
                return "JARVIS's pending Mac power request cancelled."
            return "No pending JARVIS Mac power request. Other applications' requests cannot be cancelled here."
        if action not in {"shutdown", "restart"}:
            raise ValueError("Power action is not allowlisted.")
        if self.pending_power and self.pending_power.poll() is None:
            raise RuntimeError("Abort the existing power request before scheduling another.")
        command = "shut down" if action == "shutdown" else "restart"
        # Fixed AppleScript, a real cancellation window, and normal macOS permissions.
        self.pending_power = self.popen(["/usr/bin/osascript", "-e", "delay 60", "-e", 'tell application "System Events" to ' + command], shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "Power request scheduled with a 60-second JARVIS abort window. macOS may require Automation permission or confirmation; execution is not verified. Closing JARVIS cancels this pending request."

    def screenshot(self, path):
        framework = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        framework.CGPreflightScreenCaptureAccess.argtypes = []
        framework.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
        if not framework.CGPreflightScreenCaptureAccess():
            raise PermissionError("Enable Screen Recording for JARVIS in macOS Privacy & Security, then relaunch. JARVIS does not grant itself permission.")
        file = Path(path)
        if file.suffix.lower() != ".png":
            raise ValueError("Choose a new PNG file.")
        with file.open("xb"):
            pass
        try:
            self.checked(["/usr/sbin/screencapture", "-x", str(file)])
            if file.stat().st_size == 0:
                raise RuntimeError("macOS produced no screenshot.")
        except Exception:
            file.unlink(missing_ok=True)
            raise
        return {"saved_locally": str(file), "uploaded": False}

    def close(self):
        self.power("abort")

def adapter(owner):
    if sys.platform == "darwin":
        return MacAdapter()
    if sys.platform == "win32":
        return WindowsAdapter(owner)
    raise RuntimeError("JARVIS supports Windows and macOS.")
