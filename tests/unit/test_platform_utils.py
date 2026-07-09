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


def test_get_app_data_dir_crea_carpeta(tmp_path, monkeypatch):
    monkeypatch.setattr(platform_utils.platform, "system", lambda: "Windows")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    app_dir = platform_utils.get_app_data_dir("VideoForgeTest")
    assert app_dir.exists()
    assert app_dir == tmp_path / "VideoForgeTest"
