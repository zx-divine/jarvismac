"""Allowlisted capabilities. Every side effect and file-content transfer is approved."""
import asyncio
import ctypes
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import time
import webbrowser
from datetime import datetime
from urllib.parse import urlsplit, quote_plus
import psutil
from .security import FilePolicy, TEXT_EXTENSIONS, scrub

def system_info():
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(Path.home().anchor or "/")
    battery = psutil.sensors_battery()
    return {"cpu_percent": psutil.cpu_percent(), "ram_percent": memory.percent,
            "ram_available_gb": round(memory.available / 2**30, 2), "disk_percent": disk.percent,
            "battery_percent": battery.percent if battery else None,
            "plugged_in": battery.power_plugged if battery else None}

def windows_executable(name):
    if os.name != "nt":
        raise RuntimeError("This command requires Windows.")
    # OS directory from the OS API rather than user-writable PATH.
    buffer = ctypes.create_unicode_buffer(32768)
    if name == "explorer.exe":
        ctypes.windll.kernel32.GetWindowsDirectoryW(buffer, len(buffer))
    else:
        ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
    path = Path(buffer.value) / name
    if not path.is_file():
        raise FileNotFoundError(f"Windows component {name} is unavailable.")
    return str(path)

def vscode():
    for root in (Path(os.environ.get("LOCALAPPDATA", "")) / "Programs", Path(os.environ.get("ProgramFiles", "C:/Program Files"))):
        candidate = root / "Microsoft VS Code" / "Code.exe"
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError("VS Code is not installed in a standard location. Install it or open the folder in Explorer.")

@dataclass
class Tool:
    name: str
    description: str
    properties: dict
    handler: object
    sensitive: bool = True
    developer: bool = False

    def schema(self):
        return {"type": "function", "function": {"name": self.name, "description": self.description,
            "parameters": {"type": "object", "properties": self.properties, "required": list(self.properties), "additionalProperties": False}}}

    def validate(self, args):
        if not isinstance(args, dict) or set(args) != set(self.properties):
            raise ValueError("Tool arguments must match its schema exactly.")
        for name, spec in self.properties.items():
            value = args[name]
            expected = {"string": str, "integer": int, "boolean": bool}[spec["type"]]
            if type(value) is not expected:
                raise ValueError(f"{name} must be a {spec['type']}.")
            if isinstance(value, str) and (len(value) > spec.get("maxLength", 2000) or "\x00" in value):
                raise ValueError(f"{name} is too long or contains invalid characters.")
            if "enum" in spec and value not in spec["enum"]:
                raise ValueError(f"{name} is not an allowed choice.")

def string(description, **extra):
    return {"type": "string", "description": description, **extra}

class Registry:
    def __init__(self, settings, private_dir):
        self.settings, self.private_dir = settings, Path(private_dir)
        self.policy = FilePolicy(settings.approved_folders, private_dir)
        self.tools = {}
        self.register(Tool("system_info", "Report actual CPU, RAM, disk and battery usage.", {}, lambda: system_info(), False))
        self.register(Tool("current_time", "Report actual current local time, date and timezone from Windows.", {}, lambda: {"local_time": datetime.now().astimezone().isoformat(), "timezone": time.tzname}, False))
        self.register(Tool("open_app", "Open an allowlisted Windows application.", {"app": string("Application", enum=["vscode", "chrome", "edge", "explorer", "settings", "notepad", "calculator"])}, self.open_app))
        self.register(Tool("open_website", "Open an HTTPS website in the default browser.", {"url": string("HTTPS URL")}, self.open_website))
        self.register(Tool("web_search", "Open a web search in the browser; does not fetch results or claim to have read them.", {"query": string("Search terms", maxLength=500)}, lambda query: self.open_website("https://www.bing.com/search?q=" + quote_plus(query))))
        self.register(Tool("search_files", "Find filenames inside one approved directory; does not read contents.", {"directory": string("Absolute approved directory"), "query": string("Filename substring", maxLength=100)}, self.search_files))
        self.register(Tool("read_file", "Read one selected text/source file. Contents will be sent to the configured AI provider after approval.", {"path": string("Absolute approved text file")}, self.read_file))
        self.register(Tool("create_folder", "Create a new folder inside an approved directory.", {"path": string("Absolute new folder")}, self.create_folder))
        self.register(Tool("create_text_file", "Create a new UTF-8 text/source file. Never overwrites existing files.", {"path": string("Absolute new text/source file"), "content": string("File content", maxLength=40000)}, self.create_text_file))
        self.register(Tool("open_project", "Open an approved project folder in VS Code or Explorer.", {"path": string("Absolute approved project directory"), "editor": string("Editor", enum=["vscode", "explorer"])}, self.open_project))
        self.register(Tool("volume", "Adjust Windows master volume using media keys (steps or mute toggle).", {"action": string("Volume action", enum=["up", "down", "mute"]), "steps": {"type": "integer", "description": "1–10 steps"}}, self.volume))
        self.register(Tool("media", "Send Windows media playback controls.", {"action": string("Playback action", enum=["play_pause", "next", "previous", "stop"])}, self.media))
        self.register(Tool("screenshot", "Capture the screen to an approved PNG path after explicit approval. Image is saved locally, not sent to AI.", {"path": string("Absolute new .png path")}, self.screenshot))
        self.register(Tool("power", "Shut down or restart Windows after confirmation, with a 60-second abort window.", {"action": string("Power action", enum=["shutdown", "restart", "abort"])}, self.power))
        self.register(Tool("dev_command", "Run one approved development command in an approved project. Project code can execute; output may be sent to AI.", {"directory": string("Absolute project directory"), "command": string("Allowlisted command", enum=["git_status", "git_diff", "pytest", "npm_test"])}, self.dev_command, True, True))

    def register(self, tool):
        if tool.name in self.tools:
            raise ValueError("Duplicate tool name")
        self.tools[tool.name] = tool

    def available(self):
        return [t for t in self.tools.values() if t.name not in self.settings.disabled_tools and (not t.developer or self.settings.developer_mode)]

    def schemas(self):
        return [t.schema() for t in self.available()]

    async def execute(self, name, args, approve, gate=None):
        try:
            if gate:
                gate()
            tool = next((t for t in self.available() if t.name == name), None)
            if not tool:
                raise PermissionError("Tool is unavailable or disabled in Settings.")
            tool.validate(args)
            # Validate paths before prompting and again in each handler after approval.
            for key in ("path", "directory"):
                if key in args:
                    self.policy.check(args[key], exists=name not in {"create_folder", "create_text_file", "screenshot"})
            if tool.sensitive and not await approve(tool, args):
                return {"ok": False, "error": "ASH denied this action. Do not retry without a new request."}
            if gate:
                gate()
            if asyncio.iscoroutinefunction(tool.handler):
                result = await tool.handler(**args)
            else:
                def invoke():
                    if gate:
                        gate()
                    return tool.handler(**args)
                result = await asyncio.to_thread(invoke)
            if gate:
                gate()
            return {"ok": True, "result": result}
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return {"ok": False, "error": scrub(str(exc))[:1000]}

    def open_app(self, app):
        if os.name != "nt":
            raise RuntimeError("Application launch requires Windows.")
        if app == "settings":
            os.startfile("ms-settings:")
        elif app in {"chrome", "edge"}:
            relative = "Google/Chrome/Application/chrome.exe" if app == "chrome" else "Microsoft/Edge/Application/msedge.exe"
            roots = [Path(os.environ.get(key, "C:/__missing__")) for key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
            path = next((root / relative for root in roots if (root / relative).is_file()), None)
            if not path:
                raise FileNotFoundError(f"{app} is not installed in a standard location.")
            subprocess.Popen([str(path)], shell=False)
        else:
            path = vscode() if app == "vscode" else windows_executable({"explorer": "explorer.exe", "notepad": "notepad.exe", "calculator": "calc.exe"}[app])
            # Explorer lives in the Windows directory, not System32, on Windows 10.
            subprocess.Popen([path], shell=False)
        return "Launch request sent to Windows (application readiness is not verified)."

    def open_website(self, url):
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            raise ValueError("Only HTTPS URLs without credentials are permitted.")
        if not webbrowser.open(url):
            raise RuntimeError("Windows could not open the default browser.")
        return "URL passed to the browser; page content has not been read."

    def search_files(self, directory, query):
        root = self.policy.check(directory)
        if not root.is_dir() or not query.strip():
            raise ValueError("Choose a directory and a nonempty filename query.")
        found, visited, deadline = [], 0, time.monotonic() + 8
        skip = {".git", ".venv", "node_modules", "__pycache__"}
        for folder, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = [d for d in dirs if d not in skip and self._allowed(Path(folder) / d)]
            for name in files:
                visited += 1
                if query.casefold() in name.casefold() and self._allowed(Path(folder) / name):
                    found.append(str(Path(folder) / name))
                if len(found) >= 100 or visited >= 20000 or time.monotonic() > deadline:
                    return {"files": found, "truncated": True}
        return {"files": found, "truncated": False}

    def _allowed(self, path):
        try:
            self.policy.check(str(path))
            return True
        except (OSError, ValueError):
            return False

    def read_file(self, path):
        file = self.policy.check(path)
        if file.suffix.lower() not in TEXT_EXTENSIONS or not file.is_file():
            raise ValueError("Only supported text/source files can be read.")
        with file.open("rb") as stream:
            content = stream.read(40001)
        if len(content) > 40000 or b"\x00" in content:
            raise ValueError("Choose a UTF-8 text file smaller than 40 KB.")
        return {"untrusted_file_content": scrub(content.decode("utf-8")), "path": str(file)}

    def create_folder(self, path):
        folder = self.policy.check(path, False)
        folder.mkdir(parents=False, exist_ok=False)
        return str(folder)

    def create_text_file(self, path, content):
        file = self.policy.check(path, False)
        if file.suffix.lower() not in TEXT_EXTENSIONS:
            raise ValueError("Only text/source extensions may be created; executable scripts and shortcuts are blocked.")
        with file.open("x", encoding="utf-8") as stream:
            stream.write(content)
        return str(file)

    def open_project(self, path, editor):
        folder = self.policy.check(path)
        if not folder.is_dir():
            raise ValueError("Select a project directory.")
        executable = vscode() if editor == "vscode" else windows_executable("explorer.exe")
        subprocess.Popen([executable, str(folder)], shell=False)
        return "Project launch request sent to Windows."

    @staticmethod
    def _key(code, steps=1):
        if os.name != "nt":
            raise RuntimeError("Media controls require Windows.")
        for _ in range(steps):
            ctypes.windll.user32.keybd_event(code, 0, 0, 0)
            ctypes.windll.user32.keybd_event(code, 0, 2, 0)
        return "Media key sent to Windows."

    def volume(self, action, steps):
        if not 1 <= steps <= 10:
            raise ValueError("Volume steps must be between 1 and 10.")
        return self._key({"up": 0xAF, "down": 0xAE, "mute": 0xAD}[action], 1 if action == "mute" else steps)

    def media(self, action):
        return self._key({"play_pause": 0xB3, "next": 0xB0, "previous": 0xB1, "stop": 0xB2}[action])

    def screenshot(self, path):
        from PIL import ImageGrab
        file = self.policy.check(path, False)
        if file.suffix.lower() != ".png":
            raise ValueError("Screenshot destination must be a new PNG file.")
        # Exclusive creation avoids overwriting personal files.
        with file.open("xb") as stream:
            ImageGrab.grab(all_screens=True).save(stream, format="PNG")
        return {"saved_locally": str(file), "uploaded": False}

    def power(self, action):
        args = ["/a"] if action == "abort" else ["/s" if action == "shutdown" else "/r", "/t", "60"]
        subprocess.run([windows_executable("shutdown.exe"), *args], check=True, timeout=10, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return "Power request sent to Windows. Use Abort shutdown within 60 seconds to cancel." if action != "abort" else "Pending shutdown/restart cancelled."

    async def dev_command(self, directory, command):
        import shutil
        import sys
        folder = self.policy.check(directory)
        if not folder.is_dir():
            raise ValueError("Choose a project directory.")
        # Fixed argv, no user/model command interpolation, no shell=True.
        if command.startswith("git_"):
            executable = shutil.which("git.exe")
            argv = [executable, "--no-pager", "-c", "core.fsmonitor=false", "-c", "core.pager=cat", "-c", "diff.external=", "status", "--short"] if command == "git_status" else [executable, "--no-pager", "-c", "core.fsmonitor=false", "-c", "diff.external=", "diff", "--no-ext-diff", "--no-textconv"]
        elif command == "pytest":
            if getattr(sys, "frozen", False):
                raise RuntimeError("The packaged app cannot act as a Python interpreter. Run pytest from the source virtual environment or your terminal.")
            argv = [sys.executable, "-m", "pytest", "-q"]
        else:
            node = shutil.which("node.exe")
            npm = Path(node).parent / "node_modules/npm/bin/npm-cli.js" if node else Path("/__missing__")
            argv = [node, str(npm), "test", "--", "--watch=false"]
            if not npm.is_file():
                raise FileNotFoundError("Install Node.js with npm to run npm test.")
        if not argv[0]:
            raise FileNotFoundError("Required development executable is not installed or on PATH.")
        env = dict(os.environ)
        for key in list(env):
            if any(word in key.upper() for word in ("API_KEY", "TOKEN", "SECRET", "PASSWORD")):
                env.pop(key)
        process = await asyncio.create_subprocess_exec(*argv, cwd=str(folder), env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        chunks = bytearray()
        async def collect():
            while chunk := await process.stdout.read(4096):
                chunks.extend(chunk)
                if len(chunks) > 64000:
                    raise RuntimeError("Command output exceeded 64 KB; process stopped.")
            await process.wait()
        try:
            await asyncio.wait_for(collect(), 60)
        finally:
            if process.returncode is None:
                if os.name == "nt":
                    killer = await asyncio.create_subprocess_exec(windows_executable("taskkill.exe"), "/PID", str(process.pid), "/T", "/F", stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
                    await killer.wait()
                else:
                    process.kill()
                await process.wait()
        return {"exit_code": process.returncode, "output": scrub(chunks.decode("utf-8", errors="replace"))}
