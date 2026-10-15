# TripleCam Studio

基于 Python、PyQt5 和海康机器人（Hikrobot）MVS SDK 的三相机采集工具，支持实时预览、曝光设置、ROI 编辑和软件触发采集。目前为 V2.0 beta。

## 运行环境

- Windows，以及已经安装并可正常使用的海康 MVS 驱动和 SDK。
- 与 MVS SDK 兼容、位数一致的 Python 环境。建议沿用本机已验证可用的环境。
- PyQt5，以及三台受支持的相机。

仓库包含 Python SDK 封装，不包含 MVS 安装程序、驱动或原生 DLL。请从厂商官方渠道安装匹配版本，并确认 Python 能加载 `MvCameraControl.dll`。

## 启动

在项目目录下使用 Windows CMD 执行：

```bat
python -m pip install PyQt5
copy config.example.json config.json
python TripleCamStudio.py
```

复制配置后，先编辑 `config.json`，将三台相机的 `serial` 替换为真实序列号，并设置可写的 `save_root`。保存路径须仅包含 ASCII 字符。已有 `config.json` 时不要覆盖它。该文件保存本机参数，已被 Git 忽略。

若 SDK 无法加载，请使用原有正常工作的 MVS Python 环境，或按原始 [README.txt](README.txt) 将项目文件放入 MVS 示例目录运行。

## 操作

1. 点击“一键配置”，连接三台相机并进入预览。
2. 根据需要调整曝光、编辑 ROI。
3. 点击“结束预览 / 准备拍照”，切换到软件触发模式。
4. 点击“一键拍照”，每次采集生成一个独立目录。

## 当前限制

- 相机触发命令顺序执行，不提供硬件同步。
- ROI 为全帧采集后的软件裁剪。
- 目前没有断线自动恢复或 EXE 安装包。
- 实际连接、预览、像素格式转换和采集需在安装 MVS 且连接相机的 Windows 电脑上验证。

原始使用说明见 [README.txt](README.txt)。仓库内厂商 SDK 文件的使用与分发需遵循厂商适用条款。
