# ResourceProcessor

用于批量处理 BLP/TGA 贴图的图形界面工具。它会递归扫描指定文件夹，将尺寸超过目标或非 2 的幂的贴图等比缩放到不超过目标的最大 2 的幂，并把结果输出到带时间戳的新目录，同时生成日志。

## 功能
- 批量处理 .blp / .tga
- 超过目标或非 2 的幂时自动缩放
- 保持比例，使用 LANCZOS 重采样
- 输出目录自动创建并记录日志

## 依赖
- Windows
- Python 3.8+（含 Tkinter）
- Pillow（`pip install pillow`）
- `blp.dll` 与脚本同目录

## 使用
1. 运行 `python blp_texture_tool.py`
2. 选择输入文件夹，选择目标尺寸
3. 点击“开始”

输出目录格式：`<输入目录>_输出_YYYYMMDD_HHMMSS`  
日志文件：`处理日志.log`

## 说明
- 未调整的文件会原样拷贝到输出目录。
- BLP 编解码通过 `blp.dll` 完成。

## 致谢
- BLP 编解码库：https://github.com/WarRaft/blp-lib

---

## English
GUI tool for batch processing BLP/TGA textures. It recursively scans a folder, resizes textures that exceed the target size or are not powers of two to the largest power-of-two size not exceeding the target, then outputs results to a timestamped folder and writes a log.

### Features
- Batch process .blp / .tga
- Auto-resize when larger than target or not power-of-two
- Preserve aspect ratio with LANCZOS resampling
- Auto-create output folder and log

### Requirements
- Windows
- Python 3.8+ (Tkinter included)
- Pillow (`pip install pillow`)
- `blp.dll` in the same folder as the script

### Usage
1. Run `python blp_texture_tool.py`
2. Choose the input folder and target size
3. Click "Start"

Output folder format: `<input>_输出_YYYYMMDD_HHMMSS`  
Log file: `处理日志.log`

### Notes
- Files that do not need resizing are copied as-is.
- BLP encode/decode is handled by `blp.dll`.

### Acknowledgements
- BLP library: https://github.com/WarRaft/blp-lib
