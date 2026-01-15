<div align="center">
<p align="center">
  <img src="ButterFetch.ico" alt="ButterFetch Logo" width="128" height="128" />
</p>
# 🧈 ButterFetch

**一款黄油(Galgame)搜索工具**

支持 DLsite / FANZA / VNDB 三平台并行搜索

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)]()
[![Release](https://img.shields.io/github/v/release/apaidedie/ButterFetch?color=orange)](https://github.com/apaidedie/ButterFetch/releases)

[下载](#-下载) • [功能](#-功能特性) • [截图](#-截图) • [使用](#-使用说明) • [构建](#-从源码构建)

</div>

---

## ✨ 功能特性

- 🔍 **三平台并行搜索** - 同时搜索 DLsite、FANZA、VNDB
- 🔗 **VNDB 智能嗅探** - 自动从 VNDB 页面提取 DLsite/FANZA 链接
- 🖼️ **封面预览** - 高清封面图片展示，支持圆角美化
- 🌓 **明暗主题** - 支持浅色/深色主题切换
- 📌 **窗口置顶** - 可固定窗口在最前端
- 📋 **智能粘贴** - Ctrl+V 自动粘贴并搜索
- 📜 **运行日志** - 内置日志查看器，支持过滤和导出
- ⌨️ **快捷键支持** - 键盘快速操作
- 💾 **配置记忆** - 自动保存窗口位置和设置

## 📸 截图

<details>
<summary>点击展开截图</summary>

### 主界面
![主界面](screenshots/main.png)

### 搜索结果
![搜索结果](screenshots/search.png)

### 深色模式
![深色模式](screenshots/dark_mode.png)

</details>

## 📥 下载

### 直接下载

前往 [Releases](https://github.com/apaidedie/ButterFetch/releases) 页面下载最新版本的 `ButterFetch.exe`

### 系统要求

- Windows 10/11 (64-bit)
- 无需安装 Python 环境

## 🎮 使用说明

### 基本操作

1. **搜索** - 输入游戏名称，按 Enter 或点击搜索按钮
2. **切换结果** - 使用下拉框或 ↑↓ 键切换不同结果
3. **分组筛选** - 点击平台按钮筛选特定来源的结果
4. **复制信息** - 点击标题复制，点击 ID 按钮复制游戏 ID
5. **打开链接** - 点击"前往详情页"按钮在浏览器中打开

### 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Enter` | 执行搜索 |
| `Ctrl+V` | 智能粘贴并搜索 |
| `↑` / `↓` | 切换上/下一个结果 |
| `Esc` | 清空搜索框 |

### 功能按钮

| 按钮 | 功能 |
|------|------|
| 📋 | 从剪贴板粘贴并搜索 |
| 📌 | 切换窗口置顶 |
| 🌙/☀️ | 切换明暗主题 |
| 📜 | 查看运行日志 |

## 🔧 从源码构建

### 环境要求

- Python 3.8+
- pip

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行

```bash
python ButterFetch.py
```

### 打包为 EXE

```bash
# 安装 PyInstaller
pip install pyinstaller

# 打包
pyinstaller ButterFetch.spec

# 或使用命令行
pyinstaller --onefile --windowed --icon=ButterFetch.ico --name=ButterFetch ButterFetch.py
```

打包完成后，可执行文件位于 `dist/ButterFetch.exe`

## 📦 依赖

```
ttkbootstrap>=1.10.0
requests>=2.28.0
beautifulsoup4>=4.11.0
Pillow>=9.0.0
urllib3>=1.26.0
```

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 开源协议

本项目采用 [MIT License](LICENSE) 开源协议

## ⚠️ 免责声明

- 本工具仅供学习交流使用
- 请支持正版游戏
- 搜索结果来自第三方网站，与本工具无关

## 💖 致谢

- [ttkbootstrap](https://github.com/israel-dryer/ttkbootstrap) - 现代化 Tkinter 主题
- [VNDB](https://vndb.org/) - 视觉小说数据库
- [DLsite](https://www.dlsite.com/) - 同人作品销售平台
- [FANZA](https://www.dmm.co.jp/) - DMM 游戏平台

---

<div align="center">

**如果觉得好用，请给个 ⭐ Star 支持一下喵~**

Made with 💜 by [apaidedie]

</div>
