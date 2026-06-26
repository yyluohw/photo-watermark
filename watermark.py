from PIL import Image, ImageDraw, ImageFont, ExifTags, ImageOps
import os
from datetime import datetime

# 可选 HEIC 支持
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC_SUPPORT = True
except Exception:
    HEIC_SUPPORT = False

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INPUT_FOLDER = None
OUTPUT_FOLDER = None

SUPPORTED_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp')
if HEIC_SUPPORT:
    SUPPORTED_EXTENSIONS += ('.heic', '.heif')


def get_date_taken(image_path):
    """从 EXIF 中提取拍摄日期"""
    try:
        image = Image.open(image_path)
        exif = image._getexif()
        if exif:
            for tag_id, value in exif.items():
                tag = ExifTags.TAGS.get(tag_id, tag_id)
                if tag == "DateTimeOriginal":
                    return datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
    except Exception as e:
        print(f"读取 EXIF 失败: {e}")
    return None

def load_font(font_size, custom_path=None, italic=False):
    """加载字体，优先尝试斜体变体，失败则回退到常规字体或默认字体"""
    font_paths = []
    if custom_path and os.path.exists(custom_path):
        font_paths.append(custom_path)

    font_paths.extend([
        "/System/Library/Fonts/PingFang.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ])

    def try_load(path):
        try:
            return ImageFont.truetype(path, font_size)
        except Exception:
            return None

    if italic:
        # try italic variants near custom path first
        if custom_path and os.path.exists(custom_path):
            d = os.path.dirname(custom_path)
            try:
                for fname in os.listdir(d):
                    if 'italic' in fname.lower() or 'oblique' in fname.lower():
                        found = try_load(os.path.join(d, fname))
                        if found:
                            return found
            except Exception:
                pass

        # try common italic filename variants
        for path in font_paths:
            base, ext = os.path.splitext(path)
            for cand in (base + ' Italic' + ext, base + '-Italic' + ext, base + 'Italic' + ext):
                if os.path.exists(cand):
                    f = try_load(cand)
                    if f:
                        return f
            d = os.path.dirname(path)
            try:
                for fname in os.listdir(d):
                    if 'italic' in fname.lower() or 'oblique' in fname.lower():
                        found = try_load(os.path.join(d, fname))
                        if found:
                            return found
            except Exception:
                continue

    # fallback to regular fonts
    for path in font_paths:
        f = try_load(path)
        if f:
            return f

    return ImageFont.load_default()


def add_watermark(input_path, output_path, position="bottom-right"):
    original_img = Image.open(input_path)
    img = ImageOps.exif_transpose(original_img)
    width, height = img.size

    date_taken = get_date_taken(input_path)
    if date_taken:
        date_str = date_taken.strftime("%Y-%m-%d %H:%M")
    else:
        mtime = os.path.getmtime(input_path)
        date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")

    font_size = max(12, int(height * 0.025))
    # prefer italic if desired? default CLI uses non-italic
    font = load_font(font_size, custom_path=None, italic=False)

    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0, 0), date_str, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    margin = int(height * 0.02)
    if position == "bottom-right":
        x, y = width - text_width - margin, height - text_height - margin
    elif position == "bottom-left":
        x, y = margin, height - text_height - margin
    elif position == "top-right":
        x, y = width - text_width - margin, margin
    else:
        x, y = margin, margin

    padding = int(font_size * 0.3)
    bg_box = [x - padding, y - padding, x + text_width + padding, y + text_height + padding]
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rectangle(bg_box, fill=(0, 0, 0, 128))
    overlay_draw.text((x, y), date_str, fill=(255, 255, 255, 255), font=font)

    img = Image.alpha_composite(img, overlay)
    final_img = img.convert('RGB')
    exif = original_img.info.get('exif')

    ext = os.path.splitext(output_path)[1].lower()
    if ext in ['.png', '.bmp', '.tiff', '.webp']:
        final_img.save(output_path, exif=exif)
    else:
        final_img.save(output_path, 'JPEG', quality=95, optimize=True, exif=exif)

    print(f"✅ 已处理: {os.path.basename(output_path)}")

def batch_process(input_folder, output_folder):
    if not os.path.exists(input_folder):
        print(f"输入文件夹不存在: {input_folder}")
        return
    if not os.path.exists(output_folder):
        os.makedirs(output_folder, exist_ok=True)

    total = 0
    for root, dirs, files in os.walk(input_folder):
        for f in files:
            if f.lower().endswith(SUPPORTED_EXTENSIONS):
                total += 1

    print(f"发现 {total} 张图片（包含子目录），开始处理...")

    processed = 0
    for root, dirs, files in os.walk(input_folder):
        rel_dir = os.path.relpath(root, input_folder)
        out_dir = output_folder if rel_dir == '.' else os.path.join(output_folder, rel_dir)
        os.makedirs(out_dir, exist_ok=True)
        for f in files:
            if not f.lower().endswith(SUPPORTED_EXTENSIONS):
                continue
            input_path = os.path.join(root, f)
            output_path = os.path.join(out_dir, f)
            try:
                add_watermark(input_path, output_path)
                processed += 1
            except Exception as e:
                print(f"❌ 处理失败 {os.path.join(root, f)}: {e}")

    print(f"全部完成！共处理 {processed} 张照片")


if __name__ == "__main__":
    if not INPUT_FOLDER or not OUTPUT_FOLDER:
        print("请通过 GUI 选择输入/输出文件夹，或在命令行中调用 batch_process(input_folder, output_folder)")
    else:
        batch_process(INPUT_FOLDER, OUTPUT_FOLDER)