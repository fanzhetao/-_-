"""运行时路径解析。

路径解析集中在这里，避免入口模块各自推导源码目录、PyInstaller 临时目录和
用户运行目录。该模块不创建目录，也不读取任何本地配置。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys


@dataclass(frozen=True)
class ApplicationPaths:
    source_dir: Path
    bundle_dir: Path
    application_dir: Path

    @property
    def version_path(self) -> Path:
        return self.bundle_dir / "VERSION"

    @property
    def resource_dir(self) -> Path:
        return self.bundle_dir / "resource"

    @property
    def runtime_dir(self) -> Path:
        return self.application_dir / "runtime"

    @property
    def ocr_dir(self) -> Path:
        return self.resource_dir / "model" / "ocr"

    @property
    def runtime_option_path(self) -> Path:
        return self.runtime_dir / "config" / "maa_option.json"

    @property
    def client_config_path(self) -> Path:
        return self.runtime_dir / "config" / "client_config.json"


def resolve_paths(module_file: str | Path, runtime_module=sys) -> ApplicationPaths:
    """按源码运行或 PyInstaller frozen 运行模式解析应用目录。"""

    source_dir = Path(module_file).resolve().parent
    bundle_dir = Path(getattr(runtime_module, "_MEIPASS", source_dir))
    application_dir = (
        Path(runtime_module.executable).resolve().parent
        if getattr(runtime_module, "frozen", False)
        else source_dir
    )
    return ApplicationPaths(source_dir, bundle_dir, application_dir)
