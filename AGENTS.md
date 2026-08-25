# Project Rules

## 项目定位

这是基于 Python、Tkinter、MaaFramework 和 MuMu 模拟器 12 的《时尚百货城》Windows 自动化客户端。

## 常用命令

- 安装运行依赖：`.\.venv\Scripts\python.exe -m pip install -r requirements.txt`
- 启动源码客户端：双击 `启动客户端.bat`
- 运行测试：`.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"`
- 一键发布：双击 `发布便携版.bat`，或执行 `.\build_portable.ps1`

## 目录与约定

- `client.py` 负责桌面界面，`runner.py` 负责自动化流程。
- `resource/pipeline/` 保存 MaaFramework 流程，`resource/model/ocr/` 保存 OCR 模型。
- `tests/` 仅保留在本机用于发布验证，不得由 Git 跟踪、推送或复制进用户发布包。
- `VERSION` 是版本号的唯一来源；窗口、文档和发布文件名应与其一致。
- `build/`、`dist/`、`release/`、`.build-deps/` 均为可重新生成的构建产物。
- `build_portable.ps1` 必须保留测试、自检、敏感文件审计和 SHA-256 复核门禁。

## 安全边界

- `runtime/` 包含本机配置、日志和截图，不得提交或复制进发布包。
- `runtime/config/client_config.json` 可能包含明文账号密码，禁止在输出、日志或报告中展示其内容。
- 不要启用 MaaFramework 文件日志或失败截图记录敏感输入。

## 当前状态

- 当前发布版本为 1.0.0。
- 发布前必须通过全部单元测试、便携版自检和发布包内容审计。
- MuMu 与游戏真实画面的端到端验证必须与单元测试、构建自检分别记录。
