"""Small explicit local command vocabulary; all actions still use the registry."""
import re

def local_command(text):
    phrase = " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())
    if phrase.startswith("jarvis "):
        phrase = phrase[7:]
    exact = {
        "system status": ("system_info", {}), "show system status": ("system_info", {}),
        "what time is it": ("current_time", {}), "current time": ("current_time", {}),
        "volume up": ("volume", {"action": "up", "steps": 1}),
        "volume down": ("volume", {"action": "down", "steps": 1}),
        "mute volume": ("volume", {"action": "mute", "steps": 1}),
        "pause music": ("media", {"action": "play_pause"}),
        "abort shutdown": ("power", {"action": "abort"}),
    }
    apps = {"chrome": "chrome", "edge": "edge", "vs code": "vscode", "visual studio code": "vscode", "explorer": "explorer", "finder": "explorer", "settings": "settings", "notepad": "notepad", "textedit": "notepad", "calculator": "calculator"}
    for label, app in apps.items():
        exact["open " + label] = ("open_app", {"app": app})
    return exact.get(phrase)
