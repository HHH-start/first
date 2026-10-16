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

复制配置后，先编辑 `config.json`，将三台相机的 `serial` 替换为真实序列号，并设置三台相机各自可写的 `save_dir`（也可以在界面上选择）。保存路径须仅包含 ASCII 字符。已有 `config.json` 时不要覆盖它。该文件保存本机参数，已被 Git 忽略。

若 SDK 无法加载，请使用原有正常工作的 MVS Python 环境，或按原始 [README.txt](README.txt) 将项目文件放入 MVS 示例目录运行。

## 操作

1. 点击“一键配置”，连接三台相机并进入预览。
2. 根据需要调整曝光、编辑 ROI。
3. 点击“结束预览 / 准备拍照”，切换到软件触发模式。
4. 在界面底部分别选择 Camera 1（left）、Camera 2（mid）、Camera 3（right）的保存目录。目录会保存在本机 `config.json`，下次启动自动恢复，也可以直接输入目录后离开输入框。
5. 点击“一键拍照”，照片直接保存到对应的固定目录，不再生成每批次子目录。

## 照片命名与编号

同一次拍照生成 `pic_1_left.bmp`、`pic_1_mid.bmp`、`pic_1_right.bmp`，分别对应配置中第 1、2、3 台相机（请核对相机序列号与实际左中右位置）。相机显示名称的修改不改变文件名后缀。

每次拍照前扫描三个选定目录中的 `pic_数字_left/mid/right.bmp` 文件，使用最大编号加一；三个目录都没有匹配照片时从 1 开始。例如最大编号为 10 时从 11 开始，为 1 时从 2 开始。重启软件后同样根据已有照片计算，不覆盖旧照片。不扫描子目录或旧版时间戳目录。

部分相机失败时保留成功照片，同批编号一致，下次拍照使用新编号。同一运行期间即使三台全部失败，也会跳过本次编号；重启后仍以目录中的照片为准。更换保存目录后按新目录内容计算编号。

旧版配置无需覆盖：若没有 `save_dir`，界面默认使用旧 `save_root` 下的 `left`、`mid`、`right` 三个目录；选择后自动记忆。开启 `save_metadata` 时，每批记录保存到左相机目录的 `pic_编号_capture.json`，其中包含各相机照片的完整路径。

## 自动检查

```bat
python -m unittest discover -s tests -v
```

存储测试不需要相机或 SDK；安装 PyQt5 后也会运行使用模拟相机的界面与 BMP 保存测试。模拟测试不代替实际硬件验证。

## 当前限制

- 相机触发命令顺序执行，不提供硬件同步。
- ROI 为全帧采集后的软件裁剪。
- 目前没有断线自动恢复或 EXE 安装包。
- 实际连接、预览、像素格式转换和采集需在安装 MVS 且连接相机的 Windows 电脑上验证。

原始使用说明见 [README.txt](README.txt)。仓库内厂商 SDK 文件的使用与分发需遵循厂商适用条款。
