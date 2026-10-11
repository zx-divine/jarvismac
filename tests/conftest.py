import os
import pytest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app

@pytest.fixture
def root(tmp_path):
    directory = tmp_path / "approved"
    directory.mkdir()
    return directory

@pytest.fixture
def registry(root, tmp_path):
    from jarvis.config import Settings
    from jarvis.tools import Registry
    return Registry(Settings(approved_folders=[str(root)], developer_mode=True), tmp_path / "private")
