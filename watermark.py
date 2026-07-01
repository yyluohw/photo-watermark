from enum import Enum
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


class WatermarkType(Enum):
    DATE = "DATE"
    LOCATION = "LOCATION"
    PREGNANCY = "PREGNANCY"
    AGE = "AGE"


WATERMARK_TYPE_DISPLAY = {
    WatermarkType.DATE: "日期",
    WatermarkType.LOCATION: "位置",
    WatermarkType.PREGNANCY: "怀孕",
    WatermarkType.AGE: "年龄",
}

DEFAULT_WATERMARK_ORDER = [
    WatermarkType.DATE,
    WatermarkType.LOCATION,
    WatermarkType.PREGNANCY,
    WatermarkType.AGE,
]


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


def _convert_to_degrees(value):
    try:
        d = value[0][0] / value[0][1]
        m = value[1][0] / value[1][1]
        s = value[2][0] / value[2][1]
        return d + m / 60 + s / 3600
    except Exception:
        return None


def get_exif_location(image_path):
    try:
        image = Image.open(image_path)
        exif = image._getexif()
        if not exif:
            return None
        gps_tag = next((tag_id for tag_id, tag_name in ExifTags.TAGS.items() if tag_name == 'GPSInfo'), None)
        if gps_tag is None or gps_tag not in exif:
            return None

        gps_info = exif[gps_tag]
        gps = {}
        for key, value in gps_info.items():
            name = ExifTags.GPSTAGS.get(key, key)
            gps[name] = value

        lat = _convert_to_degrees(gps.get('GPSLatitude'))
        lon = _convert_to_degrees(gps.get('GPSLongitude'))
        lat_ref = gps.get('GPSLatitudeRef')
        lon_ref = gps.get('GPSLongitudeRef')
        if lat is None or lon is None or not lat_ref or not lon_ref:
            return None
        if lat_ref.upper() == 'S':
            lat = -lat
        if lon_ref.upper() == 'W':
            lon = -lon
        return lat, lon
    except Exception:
        return None


def format_location_text(image_path, default_value):
    gps = get_exif_location(image_path)
    if gps:
        lat, lon = gps
        lat_dir = 'N' if lat >= 0 else 'S'
        lon_dir = 'E' if lon >= 0 else 'W'
        return f"{abs(lat):.5f}°{lat_dir} {abs(lon):.5f}°{lon_dir}"
    return default_value.strip() if default_value and default_value.strip() else None


def parse_date_input(date_text):
    if not date_text:
        return None
    for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"]:
        try:
            return datetime.strptime(date_text.strip(), fmt)
        except Exception:
            continue
    return None


def calc_pregnancy_text(photo_date, due_date_text):
    due_date = parse_date_input(due_date_text)
    if not due_date:
        return None
    days_before_due = (due_date - photo_date).days
    days_pregnant = 280 - days_before_due
    if days_pregnant < 0 or days_pregnant > 280:
        return None
    weeks = days_pregnant // 7
    days = days_pregnant % 7
    return f"孕{weeks}周+{days}天"


def calc_age_text(photo_date, birth_date_text):
    birth_date = parse_date_input(birth_date_text)
    if not birth_date or photo_date < birth_date:
        return None
    year_diff = photo_date.year - birth_date.year
    month_diff = photo_date.month - birth_date.month
    day_diff = photo_date.day - birth_date.day
    if day_diff < 0:
        month_diff -= 1
    total_months = year_diff * 12 + month_diff
    if total_months < 0:
        return None
    if total_months >= 12:
        years = total_months // 12
        months = total_months % 12
        return f"{years}岁{months}月" if months else f"{years}岁"
    return f"{total_months}月"


def build_watermark_lines(image_path, config):
    photo_date = get_date_taken(image_path)
    if not photo_date:
        photo_date = datetime.fromtimestamp(os.path.getmtime(image_path))

    lines = []
    for wt in config.get('watermark_types', ['DATE']):
        if wt == 'LOCATION':
            loc_text = format_location_text(image_path, config.get('default_location', ''))
            if loc_text:
                lines.append(loc_text)
        elif wt == 'DATE':
            date_str = photo_date.strftime(config.get('date_format', '%Y-%m-%d %H:%M'))
            lines.append(date_str)
        elif wt == 'PREGNANCY':
            preg = calc_pregnancy_text(photo_date, config.get('due_date', ''))
            if preg:
                lines.append(preg)
        elif wt == 'AGE':
            age = calc_age_text(photo_date, config.get('birth_date', ''))
            if age:
                lines.append(age)
    return lines


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


def apply_italic_shear(layer, shear=0.15):
    """简单斜体仿真：对生成的文字图层应用仿射剪切。"""
    try:
        width, height = layer.size
        offset = max(2, int(abs(shear) * height * 1.2))
        transformed = layer.transform(
            (width + offset, height),
            Image.AFFINE,
            (1, shear, 0, 0, 1, 0),
            resample=Image.BICUBIC,
            fillcolor=(0, 0, 0, 0),
        )
        canvas = Image.new('RGBA', (width + offset, height), (0, 0, 0, 0))
        canvas.paste(transformed, (0, 0), transformed)
        return canvas
    except Exception:
        return layer


def build_text_layer(text, font, color, alpha, outline=False, italic=False, padding=8, align='left'):
    spacing = max(4, int((font.getmetrics()[0] + font.getmetrics()[1]) * 0.3))
    temp = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
    temp_draw = ImageDraw.Draw(temp)
    try:
        bbox = temp_draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing, align=align)
    except AttributeError:
        lines = text.split('\n')
        widths = []
        heights = []
        for line in lines:
            if line:
                line_bbox = temp_draw.textbbox((0, 0), line, font=font)
                widths.append(line_bbox[2] - line_bbox[0])
                heights.append(line_bbox[3] - line_bbox[1])
            else:
                widths.append(0)
                heights.append(font.getmetrics()[0] + font.getmetrics()[1])
        text_width = max(widths) if widths else 0
        text_height = sum(heights) + spacing * (len(lines) - 1)
        bbox = (0, 0, text_width, text_height)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    italic_extra = int(abs(0.15) * text_height) if italic else 0

    layer_w = int(round(text_width + italic_extra + padding * 2))
    layer_h = int(round(text_height + padding * 2))
    text_layer = Image.new('RGBA', (layer_w, layer_h), (0, 0, 0, 0))
    text_draw = ImageDraw.Draw(text_layer)

    draw_x = padding - min(0, bbox[0])
    draw_y = padding - min(0, bbox[1])
    if outline:
        outline_color = (0, 0, 0, alpha)
        text_draw.multiline_text((draw_x, draw_y), text, font=font, fill=outline_color, spacing=spacing, align=align)

    text_draw.multiline_text((draw_x, draw_y), text, fill=(color[0], color[1], color[2], alpha), font=font, spacing=spacing, align=align)

    if italic:
        try:
            text_layer = apply_italic_shear(text_layer)
        except Exception:
            pass

    return text_layer


def add_watermark(input_path, output_path, config=None):
    config = config or {}
    options = {
        'position': config.get('position', 'bottom-right'),
        'date_format': config.get('date_format', '%Y-%m-%d %H:%M'),
        'quality': config.get('quality', 95),
        'opacity': config.get('opacity', 85),
        'font_scale': config.get('font_scale', 3.5),
        'outline': config.get('outline', False),
        'italic': config.get('italic', False),
        'save_mode': config.get('save_mode', 'keep'),
        'color': config.get('color', (255, 255, 255)),
        'font_path': config.get('font_path', None),
        'watermark_types': config.get('watermark_types', ['DATE']),
        'default_location': config.get('default_location', ''),
        'due_date': config.get('due_date', ''),
        'birth_date': config.get('birth_date', ''),
    }
    original_img = Image.open(input_path)
    img = ImageOps.exif_transpose(original_img)
    width, height = img.size

    lines = build_watermark_lines(input_path, options)
    if not lines:
        date_taken = get_date_taken(input_path)
        if date_taken:
            lines = [date_taken.strftime(options['date_format'])]
        else:
            mtime = os.path.getmtime(input_path)
            lines = [datetime.fromtimestamp(mtime).strftime(options['date_format'])]

    font_size = max(10, int(height * (options['font_scale'] / 100)))
    font = load_font(font_size, options['font_path'], italic=options['italic'])
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    r, g, b = options['color']
    alpha = int(255 * (options['opacity'] / 100))
    padding = max(6, int(font_size * 0.25))

    if options['position'] in ['右下', '右上']:
        align = 'right'
    elif options['position'] == '底部居中':
        align = 'center'
    else:
        align = 'left'

    text_layer = build_text_layer(
        "\n".join(lines),
        font,
        (r, g, b),
        alpha,
        outline=options['outline'],
        italic=options['italic'],
        padding=padding,
        align=align,
    )
    layer_w, layer_h = text_layer.size
    margin = max(4, int(font_size * 0.6))

    pos = options['position']
    if pos == '右下':
        x = width - layer_w - margin
        y = height - layer_h - margin
    elif pos == '左下':
        x = margin
        y = height - layer_h - margin
    elif pos == '右上':
        x = width - layer_w - margin
        y = margin
    elif pos == '左上':
        x = margin
        y = margin
    elif pos == '底部居中':
        x = (width - layer_w) // 2
        y = height - layer_h - margin
    else:
        x = (width - layer_w) // 2
        y = (height - layer_h) // 2

    x = max(margin, min(x, width - layer_w - margin))
    y = max(margin, min(y, height - layer_h - margin))

    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    overlay.paste(text_layer, (x, y), text_layer)
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