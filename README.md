# UnlockOverwatchRank

一个以屏幕捕捉、画面识别和系统级键鼠事件为基础的桌面自动化原型设计。项目采用有限状态机管理主菜单、模式选择、英雄选择、对局、结算和安全退出等界面状态，并将运行计数持久化；在确认 50 场胜利后停止新一轮操作。

本项目不读取或修改游戏内存、不注入进程、不修改网络数据，也不包含反检测或规避账号安全机制。在线游戏自动化可能违反服务条款并影响其他玩家，因此开发与验证应仅在获得明确授权的模拟界面、训练场或自定义环境中进行。遇到未知画面、验证、更新、掉线或失焦时，设计要求立即释放输入并停止，交由人工处理。

完整架构、状态机、测试策略、里程碑和安全边界见：

- [实现方案](docs/implementation-plan.md)

## 开发环境

项目使用 Conda 环境 `ow` 和 Python 3.11。依赖清单位于 [requirements.txt](requirements.txt)，包括屏幕捕捉、OpenCV 图像处理、OCR 封装、系统级键鼠控制、YAML 配置与测试工具。

```bash
conda create -n ow python=3.11 -y
conda activate ow
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

或无需激活环境，直接执行：

```bash
conda run -n ow python -m pip install -r requirements.txt
```

`pytesseract` 是 OCR 的 Python 封装，实际运行 OCR 功能还需要在操作系统中单独安装并配置 Tesseract 可执行程序。Windows 上的 `pywin32` 会依据平台标记自动安装；macOS 运行系统级输入控制前还需要在“隐私与安全性 → 辅助功能”中授予终端或 IDE 权限。

## Python 工程

代码位于 `src/ow_automation`，按边界拆分为：

- `models.py` / `state_machine.py`：可离线测试的状态、置信度确认、超时和 50 胜安全退出。
- `capture.py`：基于桌面区域的 `mss` 捕捉适配器，以及用于回放测试的静态帧源。
- `vision.py`：OpenCV 多尺度模板匹配、OCR 关键词分类和场景合并；只分析图像，不发送输入。
- `input_control.py`：受限点击/移动动作、急停、焦点检查和全路径按键释放。
- `config.py` / `storage.py`：YAML 安全参数和原子 JSON 会话存档。
- `runtime.py`：将捕捉、识别、状态机、存档和动作计划编排在一起。

复制并修改示例配置：

```bash
cp config.example.yaml config.yaml
PYTHONPATH=src python -m pytest -q
```

目前默认提供离线可测试的核心库和假后端。Windows 集成时，需要实现窗口焦点检查、模板资产和授权测试环境；未知界面、验证/更新弹窗、失焦或 OCR 不可用时，运行时必须停止并交由人工处理。
