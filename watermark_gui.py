import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from PIL import Image, ImageDraw, ImageFont, ExifTags, ImageOps, ImageTk
import os
from datetime import datetime
import threading

# ============ HEIC 支持（可选） ============
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC_SUPPORT = True
except ImportError:
    HEIC_SUPPORT = False

# ============ 核心处理函数 ============

def get_date_taken(image_path):
    try:
        image = Image.open(image_path)
        exif = image._getexif()
        if exif:
            for tag_id, value in exif.items():
                tag = ExifTags.TAGS.get(tag_id, tag_id)
                if tag == "DateTimeOriginal":
                    return datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return None

def add_watermark(input_path, output_path, config):
    original = Image.open(input_path)
    img = ImageOps.exif_transpose(original.copy())
    width, height = img.size

    # 获取日期
    date_taken = get_date_taken(input_path)
    if date_taken:
        date_str = date_taken.strftime(config['date_format'])
    else:
        mtime = os.path.getmtime(input_path)
        date_str = datetime.fromtimestamp(mtime).strftime(config['date_format'])

    # 动态字体大小（使用较小比例）
    font_size = max(10, int(height * (config['font_scale'] / 100)))
    font = load_font(font_size, config.get('font_path'), italic=config.get('italic'))

    # 计算文字尺寸并确保文字宽度不超出图片范围
    text_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    text_draw = ImageDraw.Draw(text_layer)
    bbox = text_draw.textbbox((0, 0), date_str, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # 边距基于字体大小
    margin = max(4, int(font_size * 0.6))
    # 若文字过宽，逐步减小字体直至适配或达到最小字号
    max_text_width = width - 2 * margin
    while text_width > max_text_width and font_size > 10:
        font_size -= 1
        font = load_font(font_size, config.get('font_path'), italic=config.get('italic'))
        text_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
        text_draw = ImageDraw.Draw(text_layer)
        bbox = text_draw.textbbox((0, 0), date_str, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        margin = max(4, int(font_size * 0.6))
    pos = config['position']
    if pos == "右下":
        x, y = width - text_width - margin, height - text_height - margin
    elif pos == "左下":
        x, y = margin, height - text_height - margin
    elif pos == "右上":
        x, y = width - text_width - margin, margin
    elif pos == "左上":
        x, y = margin, margin
    elif pos == "底部居中":
        x, y = (width - text_width) // 2, height - text_height - margin
    else:
        x, y = (width - text_width) // 2, (height - text_height) // 2

    # 限制文本坐标不要超出图片范围
    x = max(margin, min(x, max(margin, width - text_width - margin)))
    y = max(margin, min(y, max(margin, height - text_height - margin)))

    # 水印颜色 & 透明度（整数）
    r, g, b = config['color']
    opacity = int(config['opacity'])
    alpha = int(255 * (opacity / 100))

    # 描边与主文字都画在 text_layer 上
    if config.get('outline'):
        outline_color = (0, 0, 0, alpha)
        for dx, dy in [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]:
            text_draw.text((x+dx, y+dy), date_str, font=font, fill=outline_color)

    text_draw.text((x, y), date_str, fill=(r, g, b, alpha), font=font)

    # 斜体：对 text_layer 做轻微的斜切以模拟斜体效果
    if config.get('italic'):
        try:
            text_layer = apply_italic_shear(text_layer)
        except Exception:
            pass

    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    img = Image.alpha_composite(img, text_layer)

    # 保存时尽量保留原始格式
    ext = os.path.splitext(input_path)[1].lower()
    exif = original.info.get('exif')

    # 保存模式：强制 JPEG 或 保持原格式
    save_mode = config.get('save_mode', 'keep')
    if save_mode == 'jpeg':
        out_img = img.convert('RGB')
        out_img.save(output_path, 'JPEG', quality=int(config['quality']), optimize=True, exif=exif)
    else:
        if ext in ['.jpg', '.jpeg']:
            out_img = img.convert('RGB')
            out_img.save(output_path, 'JPEG', quality=int(config['quality']), optimize=True, exif=exif)
        elif ext == '.png':
            out_img = img if img.mode == 'RGBA' else img.convert('RGBA')
            out_img.save(output_path, 'PNG')
        elif ext == '.webp':
            out_img = img.convert('RGB')
            out_img.save(output_path, 'WEBP', quality=int(config['quality']))
        else:
            try:
                img.convert('RGB').save(output_path)
            except Exception:
                img.save(output_path)

    return True

def load_font(size, custom_path=None, italic=False):
    """加载字体，优先使用真正的斜体字形；若没有可用斜体字体，则退回到轻微仿真效果。"""
    font_paths = []

    if custom_path and os.path.exists(custom_path):
        font_paths.append(custom_path)

    font_paths.extend([
        "/System/Library/Fonts/PingFang.ttc",  # macOS
        "/System/Library/Fonts/STHeiti Light.ttc",
        "C:/Windows/Fonts/msyh.ttc",           # Windows 微软雅黑
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",  # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ])

    def try_load(path, index=None):
        try:
            return ImageFont.truetype(path, size, index=index) if index is not None else ImageFont.truetype(path, size)
        except Exception:
            return None

    def try_candidates(paths):
        for path in paths:
            if italic:
                for idx in (1, 2, 3):
                    f = try_load(path, index=idx)
                    if f:
                        return f
            f = try_load(path)
            if f:
                return f
        return None

    if italic:
        if custom_path and os.path.exists(custom_path):
            d = os.path.dirname(custom_path)
            try:
                for fname in os.listdir(d):
                    if 'italic' in fname.lower() or 'oblique' in fname.lower() or 'slanted' in fname.lower():
                        found = try_candidates([os.path.join(d, fname)])
                        if found:
                            return found
            except Exception:
                pass

        for path in font_paths:
            base, ext = os.path.splitext(path)
            for cand in (base + ' Italic' + ext, base + '-Italic' + ext, base + 'Italic' + ext):
                if os.path.exists(cand):
                    f = try_candidates([cand])
                    if f:
                        return f
            d = os.path.dirname(path)
            try:
                for fname in os.listdir(d):
                    if 'italic' in fname.lower() or 'oblique' in fname.lower() or 'slanted' in fname.lower():
                        found = try_candidates([os.path.join(d, fname)])
                        if found:
                            return found
            except Exception:
                continue

    font = try_candidates(font_paths)
    if font:
        return font

    return ImageFont.load_default()


def apply_italic_shear(layer, shear=0.15):
    """仅在找不到真实斜体字形时使用的轻微仿真效果，不再做反向平移补偿。"""
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
        return canvas.crop((0, 0, width, height))
    except Exception:
        return layer

# ============ GUI 界面 ============

class WatermarkApp:
    def __init__(self, root):
        self.root = root
        self.root.title("📷 照片日期水印工具")
        self.root.geometry("700x640")
        self.root.minsize(640, 480)
        self.root.resizable(True, True)
        
        # 配置变量
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.position_var = tk.StringVar(value="右下")
        self.format_var = tk.StringVar(value="%Y-%m-%d %H:%M")
        self.quality_var = tk.IntVar(value=95)
        self.opacity_var = tk.IntVar(value=85)
        # 字体大小使用离散选项（超小/小/中/大）
        self.scale_var = tk.StringVar(value="中")
        self.outline_var = tk.BooleanVar(value=True)
        self.italic_var = tk.BooleanVar(value=False)
        # 保存模式: 'keep' 或 'jpeg'
        self.save_mode_var = tk.StringVar(value='keep')
        self.color = (255, 255, 255)  # 默认白色
        self.folder_info_var = tk.StringVar(value="已选图片: 0 张")
        self.preview_image_path = None
        self.preview_window = None
        self.preview_label = None
        
        self.create_ui()
        
    def create_ui(self):
        # 输入输出
        frame = ttk.LabelFrame(self.root, text="文件夹选择", padding=10)
        frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(frame, text="输入:").grid(row=0, column=0, sticky='w')
        ttk.Entry(frame, textvariable=self.input_var, width=45).grid(row=0, column=1, padx=5)
        ttk.Button(frame, text="浏览", command=self.browse_input).grid(row=0, column=2)
        
        ttk.Label(frame, text="输出:").grid(row=1, column=0, sticky='w', pady=5)
        ttk.Entry(frame, textvariable=self.output_var, width=45).grid(row=1, column=1, padx=5)
        ttk.Button(frame, text="浏览", command=self.browse_output).grid(row=1, column=2)
        ttk.Label(frame, textvariable=self.folder_info_var).grid(row=2, column=0, columnspan=3, sticky='w', pady=5)
        # 子文件夹列表（供用户选择）
        self.subfolder_listbox = tk.Listbox(frame, height=4)
        self.subfolder_listbox.grid(row=3, column=0, columnspan=2, padx=5, pady=(4,0), sticky='nsew')
        sb_scroll = ttk.Scrollbar(frame, orient='vertical', command=self.subfolder_listbox.yview)
        sb_scroll.grid(row=3, column=2, sticky='nsw', pady=(4,0))
        self.subfolder_listbox.configure(yscrollcommand=sb_scroll.set)
        # Allow the listbox row/column to expand when window is resized
        frame.grid_rowconfigure(3, weight=1)
        frame.grid_columnconfigure(1, weight=1)
        self.subfolder_listbox.bind('<<ListboxSelect>>', self.on_subfolder_select)
        
        # 水印设置
        frame2 = ttk.LabelFrame(self.root, text="水印设置", padding=10)
        frame2.pack(fill='x', padx=10, pady=5)
        
        # 位置
        ttk.Label(frame2, text="位置:").grid(row=0, column=0, sticky='w')
        ttk.Combobox(frame2, textvariable=self.position_var, 
                 values=["左上", "右上", "左下", "右下", "底部居中", "居中"], 
                 width=12, state='readonly').grid(row=0, column=1, sticky='w')
        
        # 颜色
        ttk.Label(frame2, text="颜色:").grid(row=0, column=2, sticky='w', padx=(20,0))
        self.color_btn = tk.Button(frame2, text="  ", bg='#ffffff', width=3, 
                                   command=self.pick_color)
        self.color_btn.grid(row=0, column=3, sticky='w')
        ttk.Checkbutton(frame2, text="文字描边(更清晰)", variable=self.outline_var).grid(row=0, column=4, sticky='w', padx=(10,0))
        ttk.Checkbutton(frame2, text="斜体", variable=self.italic_var).grid(row=0, column=5, sticky='w', padx=(10,0))
        
        # 透明度
        ttk.Label(frame2, text="透明度:").grid(row=1, column=0, sticky='w', pady=5)
        ttk.Scale(frame2, from_=10, to=100, variable=self.opacity_var, 
                  orient='horizontal', length=120, command=self.on_opacity_change).grid(row=1, column=1, sticky='w')
        ttk.Label(frame2, textvariable=self.opacity_var).grid(row=1, column=2, sticky='w')
        
        # 字体大小（使用离散选项：超小/小/中/大）
        ttk.Label(frame2, text="字体大小:").grid(row=2, column=0, sticky='w')
        ttk.Combobox(frame2, textvariable=self.scale_var, values=["超小", "小", "中", "大"], width=8, state='readonly').grid(row=2, column=1, sticky='w')
        
        # 日期格式
        ttk.Label(frame2, text="日期格式:").grid(row=3, column=0, sticky='w', pady=5)
        ttk.Combobox(frame2, textvariable=self.format_var,
                     values=["%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d", 
                             "%m-%d %H:%M", "%Y年%m月%d日"],
                     width=18, state='readonly').grid(row=3, column=1, sticky='w')
        
        # 输出质量
        frame3 = ttk.LabelFrame(self.root, text="输出质量", padding=10)
        frame3.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(frame3, text="输出质量:").grid(row=0, column=0, sticky='w')
        ttk.Scale(frame3, from_=80, to=100, variable=self.quality_var, 
              orient='horizontal', length=200, command=self.on_quality_change).grid(row=0, column=1, sticky='w')
        ttk.Label(frame3, textvariable=self.quality_var).grid(row=0, column=2, sticky='w')
        ttk.Label(frame3, text="(对 JPEG/WEBP 有效，95-98 推荐)").grid(row=0, column=3, sticky='w', padx=5)
        # 保存为原格式 / 强制 JPEG
        ttk.Radiobutton(frame3, text='保持原格式', variable=self.save_mode_var, value='keep').grid(row=1, column=0, sticky='w')
        ttk.Radiobutton(frame3, text='强制保存为 JPEG', variable=self.save_mode_var, value='jpeg').grid(row=1, column=1, sticky='w')
        
        # 进度
        self.progress = ttk.Progressbar(self.root, length=560, mode='determinate')
        self.progress.pack(padx=10, pady=10)
        
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(self.root, textvariable=self.status_var).pack()
        
        # 按钮
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="🚀 开始处理", command=self.start_process, width=20).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="打开输出文件夹", command=self.open_output, width=15).pack(side='left', padx=5)
        # 预览按钮
        ttk.Button(btn_frame, text="选择示例图片用于预览", command=self.pick_preview_image, width=18).pack(side='left', padx=5)
        
        # HEIC 提示
        if not HEIC_SUPPORT:
            ttk.Label(self.root, text="⚠️ 未安装 pillow-heif，iPhone HEIC 照片将跳过", 
                     foreground='orange').pack()

        # 监听设置变化，实时更新预览（如果已经选择了示例图）
        for var in (self.position_var, self.format_var, self.quality_var,
                    self.opacity_var, self.scale_var, self.outline_var,
                    self.italic_var, self.save_mode_var):
            var.trace_add('write', self.on_preview_change)
    
    def browse_input(self):
        path = filedialog.askdirectory()
        if path:
            self.input_var.set(path)
            if not self.output_var.get():
                self.output_var.set(path + "_watermarked")
            self.update_folder_info()
            self.update_folder_list()
            if self.preview_image_path:
                self.render_preview()

    def browse_output(self):
        path = filedialog.askdirectory()
        if path:
            self.output_var.set(path)
            self.update_folder_info()

    def update_folder_info(self):
        path = self.input_var.get()
        supported = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp')
        if HEIC_SUPPORT:
            supported += ('.heic', '.heif')
        count = 0
        if os.path.exists(path):
            try:
                for root, dirs, files in os.walk(path):
                    for f in files:
                        if f.lower().endswith(supported):
                            count += 1
            except Exception:
                count = 0
        self.folder_info_var.set(f"已选图片: {count} 张")

    def update_folder_list(self):
        """列出选中文件夹下的直接子文件夹，便于选择子目录处理"""
        path = self.input_var.get()
        self.subfolder_listbox.delete(0, tk.END)
        if not path or not os.path.exists(path):
            return
        try:
            entries = [d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))]
            entries.sort()
            if len(entries) == 0:
                # 没有子文件夹，则显示当前文件夹名作单行显示
                display_name = os.path.basename(path) or path
                self.subfolder_listbox.insert(tk.END, display_name)
                self.subfolder_listbox.config(height=1)
            else:
                for d in entries:
                    self.subfolder_listbox.insert(tk.END, d)
                # 高度根据条目数量自适应，最大 8 行
                self.subfolder_listbox.config(height=min(8, max(3, len(entries))))
        except Exception:
            pass
        # 每次更新文件夹列表时，尝试更新预览（如果已选择示例图片则重渲染）
        if self.preview_image_path:
            self.render_preview()

    def on_opacity_change(self, value):
        try:
            self.opacity_var.set(int(float(value)))
        except Exception:
            pass

    def on_font_size_change(self, value):
        try:
            self.scale_var.set(int(float(value)))
        except Exception:
            pass

    def on_quality_change(self, value):
        try:
            self.quality_var.set(int(float(value)))
        except Exception:
            pass

    def on_subfolder_select(self, event):
        sel = event.widget.curselection()
        if not sel:
            return
        idx = sel[0]
        name = event.widget.get(idx)
        base = self.input_var.get()
        if base:
            new_path = os.path.join(base, name)
            self.input_var.set(new_path)
            self.update_folder_info()
            self.update_folder_list()
    
    def pick_color(self):
        color = colorchooser.askcolor(title="选择水印颜色", initialcolor=self.color)
        if color[1]:
            self.color = tuple(int(c) for c in color[0])
            self.color_btn.configure(bg=color[1])
            # 更新预览颜色
            if self.preview_image_path:
                self.render_preview()
    
    def open_output(self):
        path = self.output_var.get()
        if os.path.exists(path):
            os.startfile(path) if os.name == 'nt' else os.system(f'open "{path}"')
    
    def start_process(self):
        input_path = self.input_var.get()
        output_path = self.output_var.get()
        
        if not input_path or not os.path.exists(input_path):
            messagebox.showerror("错误", "请选择有效的输入文件夹")
            return
        if not output_path:
            messagebox.showerror("错误", "请选择输出文件夹")
            return
        
        # 字体大小映射：将标签转换为百分比参考值
        size_map = {'超小': 1.5, '小': 2.5, '中': 3.5, '大': 5}
        font_scale_pct = size_map.get(self.scale_var.get(), 3.5)

        config = {
            'position': self.position_var.get(),
            'date_format': self.format_var.get(),
            'quality': self.quality_var.get(),
            'opacity': int(self.opacity_var.get()),
            'font_scale': font_scale_pct,
            'outline': self.outline_var.get(),
            'italic': self.italic_var.get(),
            'save_mode': self.save_mode_var.get(),
            'color': self.color,
            'font_path': None,
        }
        
        thread = threading.Thread(target=self.process, args=(input_path, output_path, config))
        thread.daemon = True
        thread.start()
        # 更新预览（以当前配置渲染示例图）
        if self.preview_image_path:
            self.render_preview()

    def pick_preview_image(self):
        path = filedialog.askopenfilename(filetypes=[('Images', '*.jpg;*.jpeg;*.png;*.webp;*.bmp;*.tiff;*.heic;*.heif')])
        if path:
            self.preview_image_path = path
            self.ensure_preview_window()
            self.render_preview()

    def ensure_preview_window(self):
        if self.preview_window and self.preview_window.winfo_exists():
            return
        self.preview_window = tk.Toplevel(self.root)
        self.preview_window.title("水印实时预览")
        # 默认与主窗口大小一致
        width = self.root.winfo_width() or 700
        height = self.root.winfo_height() or 640
        self.preview_window.geometry(f"{width}x{height}")
        self.preview_window.minsize(360, 240)
        self.preview_window.resizable(True, True)
        self.preview_label = ttk.Label(self.preview_window, anchor='center')
        self.preview_label.pack(fill='both', expand=True)
        self.preview_window.protocol('WM_DELETE_WINDOW', self.on_preview_window_close)
        self.preview_window.bind('<Configure>', self.on_preview_window_resize)
        self.preview_resize_after_id = None

    def on_preview_window_close(self):
        if self.preview_window:
            try:
                self.preview_window.destroy()
            except Exception:
                pass
        self.preview_window = None
        self.preview_label = None
        self.preview_resize_after_id = None

    def on_preview_window_resize(self, event):
        # 仅在实际大小变化时重新渲染预览，避免频繁刷新
        if event.widget is self.preview_window:
            if self.preview_image_path and self.preview_window and self.preview_window.winfo_exists():
                if self.preview_resize_after_id:
                    self.preview_window.after_cancel(self.preview_resize_after_id)
                self.preview_resize_after_id = self.preview_window.after(120, self.render_preview)

    def on_preview_change(self, *args):
        if self.preview_image_path and self.preview_window and self.preview_window.winfo_exists():
            self.render_preview()

    def render_preview(self):
        try:
            sample = Image.open(self.preview_image_path)
            sample = ImageOps.exif_transpose(sample)

            size_map = {'超小': 1.5, '小': 2.5, '中': 3.5, '大': 5}
            font_scale_pct = size_map.get(self.scale_var.get(), 3.5)
            config = {
                'position': self.position_var.get(),
                'date_format': self.format_var.get(),
                'quality': self.quality_var.get(),
                'opacity': int(self.opacity_var.get()),
                'font_scale': font_scale_pct,
                'outline': self.outline_var.get(),
                'italic': self.italic_var.get(),
                'save_mode': self.save_mode_var.get(),
                'color': self.color,
                'font_path': None,
            }

            img = sample.convert('RGBA')
            width, height = img.size

            date_taken = get_date_taken(self.preview_image_path)
            if date_taken:
                date_str = date_taken.strftime(config['date_format'])
            else:
                date_str = datetime.fromtimestamp(os.path.getmtime(self.preview_image_path)).strftime(config['date_format'])

            font_size = max(10, int(height * (config['font_scale'] / 100)))
            font = load_font(font_size, config.get('font_path'), italic=config.get('italic'))

            text_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
            text_draw = ImageDraw.Draw(text_layer)
            bbox = text_draw.textbbox((0, 0), date_str, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            margin = max(4, int(font_size * 0.6))
            max_text_width = width - 2 * margin
            while text_width > max_text_width and font_size > 10:
                font_size -= 1
                font = load_font(font_size, config.get('font_path'), italic=config.get('italic'))
                text_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
                text_draw = ImageDraw.Draw(text_layer)
                bbox = text_draw.textbbox((0, 0), date_str, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                margin = max(4, int(font_size * 0.6))

            pos = config['position']
            if pos == "右下":
                x, y = width - text_width - margin, height - text_height - margin
            elif pos == "左下":
                x, y = margin, height - text_height - margin
            elif pos == "右上":
                x, y = width - text_width - margin, margin
            elif pos == "左上":
                x, y = margin, margin
            elif pos == "底部居中":
                x, y = (width - text_width) // 2, height - text_height - margin
            else:
                x, y = (width - text_width) // 2, (height - text_height) // 2

            x = max(margin, min(x, max(margin, width - text_width - margin)))
            y = max(margin, min(y, max(margin, height - text_height - margin)))

            r, g, b = config['color']
            opacity = int(config['opacity'])
            alpha = int(255 * (opacity / 100))

            if config.get('outline'):
                outline_color = (0, 0, 0, alpha)
                for dx, dy in [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]:
                    text_draw.text((x+dx, y+dy), date_str, font=font, fill=outline_color)

            text_draw.text((x, y), date_str, fill=(r, g, b, alpha), font=font)

            if config.get('italic'):
                try:
                    text_layer = apply_italic_shear(text_layer)
                except Exception:
                    pass

            preview_img = Image.alpha_composite(img, text_layer).convert('RGB')

            # 根据预览窗口大小调整显示，但不放大超出原始图片尺寸
            if self.preview_window and self.preview_window.winfo_exists() and self.preview_label:
                label_w = self.preview_label.winfo_width() or self.preview_window.winfo_width()
                label_h = self.preview_label.winfo_height() or self.preview_window.winfo_height()
                # 减去少量边距，避免显示边界被遮挡
                label_w = max(1, label_w - 10)
                label_h = max(1, label_h - 10)
                scale = min(1.0, label_w / preview_img.width, label_h / preview_img.height)
                if scale < 1.0:
                    new_size = (max(1, int(preview_img.width * scale)), max(1, int(preview_img.height * scale)))
                    preview_img = preview_img.resize(new_size, Image.LANCZOS)

            tkimg = ImageTk.PhotoImage(preview_img)
            self.preview_label.configure(image=tkimg)
            self.preview_label.image = tkimg
        except Exception as e:
            print(f"预览渲染失败: {e}")
    
    def process(self, input_path, output_path, config):
        if not os.path.exists(output_path):
            os.makedirs(output_path, exist_ok=True)

        supported = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp')
        if HEIC_SUPPORT:
            supported += ('.heic', '.heif')

        total = 0
        for root_dir, dirs, files in os.walk(input_path):
            for f in files:
                if f.lower().endswith(supported):
                    total += 1

        if total == 0:
            self.root.after(0, lambda: messagebox.showwarning("提示", "未找到支持的照片"))
            return

        self.root.after(0, lambda: self.status_var.set(f"正在处理 0/{total}..."))

        processed = 0
        for root_dir, dirs, files in os.walk(input_path):
            rel = os.path.relpath(root_dir, input_path)
            out_dir = output_path if rel == '.' else os.path.join(output_path, rel)
            os.makedirs(out_dir, exist_ok=True)
            for f in files:
                if not f.lower().endswith(supported):
                    continue
                in_file = os.path.join(root_dir, f)
                out_file = os.path.join(out_dir, f)
                try:
                    add_watermark(in_file, out_file, config)
                    processed += 1
                    progress = (processed / total) * 100
                    self.root.after(0, lambda p=progress, c=processed, t=total: self.update_progress(p, c, t))
                except Exception as e:
                    print(f"处理失败 {in_file}: {e}")

        self.root.after(0, lambda: self.status_var.set(f"✅ 完成！共处理 {processed} 张"))
        self.root.after(0, lambda: messagebox.showinfo("完成", f"成功处理 {processed} 张照片！"))
    
    def update_progress(self, value, current, total):
        self.progress['value'] = value
        self.status_var.set(f"正在处理 {current}/{total}...")

# ============ 启动 ============

if __name__ == "__main__":
    root = tk.Tk()
    app = WatermarkApp(root)
    root.mainloop()