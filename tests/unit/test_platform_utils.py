from src.utils import platform_utils


def test_no_window_kwargs_en_windows(monkeypatch):
    monkeypatch.setattr(platform_utils.platform, "system", lambda: "Windows")
    kwargs = platform_utils.no_window_kwargs()
    assert "creationflags" in kwargs


def test_no_window_kwargs_fuera_de_windows(monkeypatch):
    monkeypatch.setattr(platform_utils.platform, "system", lambda: "Darwin")
    assert platform_utils.no_window_kwargs() == {}

    monkeypatch.setattr(platform_utils.platform, "system", lambda: "Linux")
    assert platform_utils.no_window_kwargs() == {}


def test_is_frozen_por_defecto_false():
    # En pytest (no empaquetado con PyInstaller) sys.frozen no deberia existir.
    assert platform_utils.is_frozen() is False


def test_get_app_data_dir_crea_carpeta_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(platform_utils.platform, "system", lambda: "Windows")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    app_dir = platform_utils.get_app_data_dir("VideoForgeTest")
    assert app_dir.exists()
    assert app_dir == tmp_path / "VideoForgeTest"


def test_get_app_data_dir_crea_carpeta_mac(monkeypatch):
    # En Mac no hay APPDATA -- debe caer a ~/Library/Application Support, no romper.
    monkeypatch.setattr(platform_utils.platform, "system", lambda: "Darwin")
    app_dir = platform_utils.get_app_data_dir("VideoForgeTest")
    assert app_dir == platform_utils.Path.home() / "Library" / "Application Support" / "VideoForgeTest"


def test_open_folder_usa_explorer_en_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(platform_utils.platform, "system", lambda: "Windows")
    calls = []
    monkeypatch.setattr(platform_utils.subprocess, "Popen", lambda cmd, **kw: calls.append(cmd))
    platform_utils.open_folder(str(tmp_path))
    assert calls[0][0] == "explorer"


def test_open_folder_usa_open_en_mac(tmp_path, monkeypatch):
    monkeypatch.setattr(platform_utils.platform, "system", lambda: "Darwin")
    calls = []
    monkeypatch.setattr(platform_utils.subprocess, "Popen", lambda cmd, **kw: calls.append(cmd))
    platform_utils.open_folder(str(tmp_path))
    assert calls[0] == ["open", str(tmp_path)]


def test_open_folder_usa_xdg_open_en_linux(tmp_path, monkeypatch):
    monkeypatch.setattr(platform_utils.platform, "system", lambda: "Linux")
    calls = []
    monkeypatch.setattr(platform_utils.subprocess, "Popen", lambda cmd, **kw: calls.append(cmd))
    platform_utils.open_folder(str(tmp_path))
    assert calls[0] == ["xdg-open", str(tmp_path)]
