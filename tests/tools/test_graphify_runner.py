from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

from openjarvis.tools import graphify_runner


def test_graphify_site_packages_supports_windows_uv_layout(tmp_path: Path) -> None:
    site_packages = tmp_path / "graphifyy" / "Lib" / "site-packages"
    site_packages.mkdir(parents=True)

    assert graphify_runner._graphify_site_packages(tmp_path) == [site_packages]


def test_ensure_graphify_importable_uses_uv_tool_environment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    site_packages = tmp_path / "graphifyy" / "Lib" / "site-packages"
    package = site_packages / "graphify"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")

    monkeypatch.setattr(graphify_runner, "_uv_tool_dir", lambda: tmp_path)
    assert graphify_runner.ensure_graphify_importable() is True
    assert str(site_packages) in sys.path


def test_main_delegates_to_graphify_entrypoint(monkeypatch) -> None:
    package = ModuleType("graphify")
    package.__path__ = []  # type: ignore[attr-defined]
    entrypoint = ModuleType("graphify.__main__")
    seen: dict[str, list[str]] = {}

    def fake_main() -> int:
        seen["argv"] = sys.argv[:]
        return 0

    entrypoint.main = fake_main  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "graphify", package)
    monkeypatch.setitem(sys.modules, "graphify.__main__", entrypoint)
    monkeypatch.setattr(
        graphify_runner,
        "ensure_graphify_importable",
        lambda: True,
    )

    original = sys.argv[:]
    assert graphify_runner.main(["--version"]) == 0
    assert seen["argv"] == ["graphify", "--version"]
    assert sys.argv == original


def test_graphify_skill_uses_portable_runner() -> None:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

    root = Path(__file__).parents[2]
    skill_path = root / "src" / "openjarvis" / "skills" / "data"
    skill_path = skill_path / "graphify-code-intelligence.toml"
    data = tomllib.loads(skill_path.read_text(encoding="utf-8"))
    first_step = data["skill"]["steps"][0]
    assert "openjarvis.tools.graphify_runner" in first_step["arguments_template"]
