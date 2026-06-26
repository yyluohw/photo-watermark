# 照片日期水印工具

本项目包含一个可批量为照片添加拍摄日期水印的工具，支持命令式处理和图形化界面。主要功能如下：

## 主要功能

- 从照片 EXIF 信息中提取拍摄时间，若没有 EXIF 则使用文件修改时间作为日期水印。
- 批量处理指定文件夹中的图片，包含子目录内的图片。
- 支持常见图片格式：`.jpg`, `.jpeg`, `.png`, `.bmp`, `.tiff`, `.webp`。
- 可选支持 HEIC/HEIF 格式（需安装 `pillow_heif`）。
- 自动计算水印文字大小和位置，保持在图片边缘可读性高。
- 支持输出质量控制、透明度、描边和字体样式等可配置选项（GUI 版本）。

## 文件说明

- `watermark.py`
  - 核心批量处理逻辑。
  - `get_date_taken(image_path)`：从 EXIF 中获取拍摄日期。
  - `load_font(font_size, custom_path=None, italic=False)`：加载本地字体，优先使用系统字体，并支持斜体。
  - `add_watermark(input_path, output_path, position="bottom-right")`：为单张图片添加日期水印。
  - `batch_process(input_folder, output_folder)`：遍历输入文件夹，处理所有支持格式的图片并保存到输出文件夹。

- `watermark_gui.py`
  - 基于 Tkinter 的图形界面程序。
  - 支持选择输入/输出文件夹。
  - 可设置水印位置、日期格式、字体大小、透明度、颜色、描边、斜体和保存模式等。
  - 支持图片预览和进度提示。

## 使用方式

1. 安装依赖：

```bash
pip install pillow
```

如果需要处理 HEIC/HEIF 图片，还请安装：

```bash
pip install pillow_heif
```

2. 运行 Python 文件：

- 运行图形界面：

```bash
python watermark_gui.py
```

- 运行脚本批量处理（直接执行 `watermark.py`，或在其他脚本中导入）：

```bash
python watermark.py
```

运行 `python watermark.py` 时，程序会打开 GUI 让你选择输入/输出文件夹；如果你希望不使用 GUI，请在另一个 Python 脚本中导入并调用 `batch_process`：

```python
from watermark import batch_process
batch_process(r"path\to\photoInput", r"path\to\photoOutput")
```

3. 示例：

```bash
python watermark_gui.py
```

或在 Python 脚本中：

```python
from watermark import batch_process
batch_process(r"e:\photo-watermark\photoInput", r"e:\photo-watermark\photoOutput")
```

## 目录结构

- `photoInput/`：可用于放置待处理照片。
- `photoOutput/`：处理后照片输出目录。

## 注意事项

- 若使用 HEIC/HEIF 图片，请安装 `pillow_heif`。若未安装，程序仍可处理常规格式。
- `watermark.py` 的主入口目前需要通过导入并调用 `batch_process` 使用，`watermark_gui.py` 则直接以 GUI 方式启动。
