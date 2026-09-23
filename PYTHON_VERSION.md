# Python 版本说明

本项目已从 Node.js 转换为 Python 实现，提供更好的跨平台兼容性和易用性。

## 主要变化

### 核心文件
- `localize.js` → `localize.py` (核心汉化逻辑)
- `汉化.bat` → `汉化.py` (Windows 一键汉化脚本)
- `还原.bat` → `还原.py` (Windows 一键还原脚本)

### 工具脚本
- `tools/syntax-check.js` → `tools/syntax-check.py` (语法校验)
- `tools/extract.js` → `tools/extract.py` (字符串提取)
- `tools/filter.js` → `tools/filter.py` (候选词条过滤)
- `tools/clean-dict.js` → `tools/clean-dict.py` (词典清理)
- `tools/boundary-test.js` → `tools/boundary-test.py` (边界测试)

### 保持不变
- `dict.json` - 翻译词典格式不变
- `backups/` - 备份目录结构不变
- 工作原理和逻辑完全相同

## 系统要求

- Python 3.6 或更高版本
- 无需额外依赖包（使用 Python 标准库）
- 如需语法校验功能，需要安装 Node.js（用于 `node --check`）

## 使用方法

### 快速开始
```bash
# 汉化（推荐，英文文件名避免编码问题）
python localize_cn.py

# 还原（推荐，英文文件名避免编码问题）
python localize_restore.py

# 或者使用中文文件名（需要UTF-8环境）
python 汉化.py
python 还原.py

# 命令行操作
python localize.py apply
python localize.py restore
python localize.py status
python localize.py dry
```

### Windows bat文件
- `汉化.bat` 和 `还原.bat` 调用英文文件名的Python脚本
- bat文件内容：`python "%~dp0localize_cn.py"` 和 `python "%~dp0localize_restore.py"`
- 使用英文文件名完全避免Windows编码问题
- 功能完全相同，只是文件名不同

### 高级用法
```bash
# 指定安装目录
python localize.py apply "D:\你的安装路径\Command Code"

# 使用环境变量
set CC_APP_DIR=D:\你的安装路径\Command Code
python localize.py apply
```

## 优势

1. **跨平台兼容性更好**：Python 在各平台上的行为更一致
2. **无需 Node.js 环境**：除了语法校验外，其他功能不依赖 Node.js
3. **更易维护**：Python 语法更清晰，更易于理解和修改
4. **更好的错误处理**：Python 的异常处理机制更完善
5. **标准库丰富**：利用 Python 标准库实现各种功能

## 兼容性说明

- 原有的 Node.js 版本仍然保留在项目中
- `dict.json` 格式完全兼容，可以继续使用
- 备份文件格式完全兼容
- 功能和逻辑与原版本完全相同

## 故障排除

如果遇到问题：

1. 确认 Python 版本：`python --version` (需要 3.6+)
2. 检查文件编码：确保所有 Python 文件使用 UTF-8 编码
3. 如需语法校验，确认 Node.js 已安装：`node --version`
4. Windows 用户可以直接双击 `.py` 文件运行

## 贡献

欢迎贡献改进建议和 bug 修复！
