import ctypes
import os
import shutil
import sys
import tempfile
from datetime import datetime
from tkinter import Tk, StringVar, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from tkinter.ttk import Button, Frame, Label, OptionMenu

from PIL import Image


# 判断整数是否为二次幂
def _is_pow2(value):
    return value > 0 and (value & (value - 1)) == 0


# 返回不超过 value 的最大二次幂
def _floor_pow2(value):
    if value <= 1:
        return 1
    return 1 << (value.bit_length() - 1)


# BLP DLL 封装与编解码接口
class BlpLib:
    # 加载 BLP DLL 并绑定函数签名
    def __init__(self, dll_path):
        self.dll = ctypes.CDLL(dll_path)

        class BlpImage(ctypes.Structure):
            _fields_ = [
                ("width", ctypes.c_uint32),
                ("height", ctypes.c_uint32),
                ("data", ctypes.POINTER(ctypes.c_uint8)),
                ("data_len", ctypes.c_uint32),
            ]

        self.BlpImage = BlpImage

        self.dll.blp_load_from_file.argtypes = [
            ctypes.c_char_p,
            ctypes.POINTER(BlpImage),
        ]
        self.dll.blp_load_from_file.restype = ctypes.c_int

        self.dll.blp_free_image.argtypes = [ctypes.POINTER(BlpImage)]
        self.dll.blp_free_image.restype = None

        self.dll.blp_encode_file_to_blp.argtypes = [
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_uint32,
        ]
        self.dll.blp_encode_file_to_blp.restype = ctypes.c_int

    # 读取 BLP 图像数据
    def load(self, path):
        image = self.BlpImage()
        result = self.dll.blp_load_from_file(_to_bytes(path), ctypes.byref(image))
        if result != 0:
            raise RuntimeError(f"BLP 读取失败：{result}")
        data = ctypes.string_at(image.data, image.data_len)
        width = int(image.width)
        height = int(image.height)
        self.dll.blp_free_image(ctypes.byref(image))
        return width, height, data

    # 将输入图片编码为 BLP 文件
    def encode(self, input_path, output_path, quality=100, mip_count=1):
        result = self.dll.blp_encode_file_to_blp(
            _to_bytes(input_path),
            _to_bytes(output_path),
            int(quality),
            int(mip_count),
        )
        if result != 0:
            raise RuntimeError(f"BLP 编码失败：{result}")


# 将路径转换为字节串供 DLL 调用
def _to_bytes(path):
    return os.fsencode(path)


# 判断是否需要缩放并返回新尺寸与原因
def _need_resize(width, height, target):
    reasons = []
    scale = min(target / width, target / height, 1.0)
    if width > target:
        reasons.append("宽度超过目标")
    if height > target:
        reasons.append("高度超过目标")

    scaled_width = max(1, int(round(width * scale)))
    scaled_height = max(1, int(round(height * scale)))

    new_width = scaled_width
    new_height = scaled_height

    if not _is_pow2(new_width):
        new_width = _floor_pow2(new_width)
        reasons.append("宽度不是二次幂")
    if not _is_pow2(new_height):
        new_height = _floor_pow2(new_height)
        reasons.append("高度不是二次幂")

    if (new_width, new_height) == (width, height):
        return False, width, height, reasons
    return True, new_width, new_height, reasons


# 获取 LANCZOS 重采样常量，兼容不同 Pillow 版本
def _get_resample():
    resampling = getattr(Image, "Resampling", None)
    if resampling is not None:
        return getattr(resampling, "LANCZOS", getattr(Image, "BICUBIC", 3))
    return getattr(Image, "LANCZOS", getattr(Image, "BICUBIC", 3))


# 按目标尺寸缩放图像，尺寸不变则返回原图
def _resize_img(image, new_width, new_height):
    if image.size == (new_width, new_height):
        return image
    return image.resize((new_width, new_height), _get_resample())


# 处理单个 BLP 文件
def _handle_blp(
    blp_lib,
    src_path,
    dst_path,
    target,
    log,
):
    width, height, data = blp_lib.load(src_path)
    needs_resize, new_width, new_height, reasons = _need_resize(width, height, target)

    if not needs_resize:
        shutil.copy2(src_path, dst_path)
        return False, width, height, width, height, reasons

    image = Image.frombytes("RGBA", (width, height), data, "raw", "RGBA")
    image = _resize_img(image, new_width, new_height)

    temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    temp_path = temp_file.name
    temp_file.close()

    try:
        image.save(temp_path, format="PNG")
        blp_lib.encode(temp_path, dst_path, quality=100, mip_count=1)
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            log(f"警告：删除临时文件失败：{temp_path}")

    return True, width, height, new_width, new_height, reasons


# 处理单个 TGA 文件
def _handle_tga(src_path, dst_path, target, log):
    with Image.open(src_path) as image:
        width, height = image.size
        needs_resize, new_width, new_height, reasons = _need_resize(
            width, height, target
        )

        if not needs_resize:
            shutil.copy2(src_path, dst_path)
            return False, width, height, width, height, reasons

        image = image.convert("RGBA")
        image = _resize_img(image, new_width, new_height)
        image.save(dst_path, format="TGA")

        return True, width, height, new_width, new_height, reasons


# 递归收集文件夹内的 BLP/TGA 文件
def _iter_images(folder):
    for root, _, files in os.walk(folder):
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext in (".blp", ".tga"):
                yield os.path.join(root, name)


# 生成带时间戳的输出目录
def _make_out_dir(input_dir):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{input_dir}_输出_{timestamp}"


# 启动图形界面批处理程序
def run_gui():
    root = Tk()
    root.title("BLP/TGA 批量处理器")
    root.geometry("720x520")

    input_dir_var = StringVar()
    output_dir_var = StringVar(value="（自动）")
    target_var = StringVar(value="512")

    # 写日志到界面和文件
    def write_log(message):
        log_text.insert("end", message + "\n")
        log_text.see("end")
        log_text.update_idletasks()
        if log_file_handle:
            log_file_handle.write(message + "\n")
            log_file_handle.flush()

    # 选择输入目录
    def pick_input():
        folder = filedialog.askdirectory()
        if folder:
            input_dir_var.set(folder)
            output_dir_var.set("（自动）")

    # 执行批处理流程并输出日志
    def run_batch():
        input_dir = input_dir_var.get().strip()
        if not input_dir or not os.path.isdir(input_dir):
            messagebox.showerror("错误", "请选择有效的输入文件夹。")
            return

        dll_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blp.dll")
        if not os.path.isfile(dll_path):
            messagebox.showerror("错误", f"未找到 blp.dll：{dll_path}")
            return

        output_dir = _make_out_dir(input_dir)
        os.makedirs(output_dir, exist_ok=True)
        output_dir_var.set(output_dir)

        log_path = os.path.join(output_dir, "处理日志.log")
        nonlocal log_file_handle
        log_file_handle = open(log_path, "w", encoding="utf-8")

        write_log("--- 开始 ---")
        write_log(f"输入：{input_dir}")
        write_log(f"输出：{output_dir}")
        write_log(f"目标尺寸：{target_var.get()}")

        target = int(target_var.get())
        blp_lib = BlpLib(dll_path)

        total = 0
        changed = 0
        errors = 0

        for src_path in _iter_images(input_dir):
            total += 1
            rel_path = os.path.relpath(src_path, input_dir)
            dst_path = os.path.join(output_dir, rel_path)
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)

            try:
                ext = os.path.splitext(src_path)[1].lower()
                if ext == ".blp":
                    resized, width, height, new_width, new_height, reasons = _handle_blp(
                        blp_lib, src_path, dst_path, target, write_log
                    )
                else:
                    resized, width, height, new_width, new_height, reasons = _handle_tga(
                        src_path, dst_path, target, write_log
                    )

                if resized:
                    changed += 1
                    reason_text = "，".join(reasons) if reasons else "调整"
                    write_log(
                        f"调整：{rel_path} | {width}x{height} -> {new_width}x{new_height} | {reason_text}"
                    )
            except Exception as exc:
                errors += 1
                write_log(f"错误：{rel_path} | {exc}")

            root.update_idletasks()

        write_log("--- 结束 ---")
        write_log(f"总计：{total}")
        write_log(f"已调整：{changed}")
        write_log(f"错误数：{errors}")
        log_file_handle.close()
        log_file_handle = None

        messagebox.showinfo(
            "完成",
            f"处理完成。输出：{output_dir}\n日志：{log_path}",
        )

    frame = Frame(root, padding=10)
    frame.pack(fill="both", expand=True)

    Label(frame, text="输入文件夹").grid(row=0, column=0, sticky="w")
    Label(frame, textvariable=input_dir_var, width=60).grid(row=1, column=0, sticky="w")
    Button(frame, text="浏览", command=pick_input).grid(row=1, column=1, sticky="w")

    Label(frame, text="输出文件夹（自动）").grid(
        row=2, column=0, sticky="w", pady=(10, 0)
    )
    Label(frame, textvariable=output_dir_var, width=60).grid(
        row=3, column=0, sticky="w"
    )

    Label(frame, text="目标尺寸").grid(row=4, column=0, sticky="w", pady=(10, 0))
    OptionMenu(frame, target_var, "512", "32", "64", "128", "256", "512").grid(
        row=5, column=0, sticky="w"
    )

    Button(frame, text="开始", command=run_batch).grid(row=5, column=1, sticky="w")

    Label(frame, text="日志").grid(row=6, column=0, sticky="w", pady=(10, 0))
    log_text = ScrolledText(frame, height=15)
    log_text.grid(row=7, column=0, columnspan=2, sticky="nsew")

    frame.rowconfigure(7, weight=1)
    frame.columnconfigure(0, weight=1)

    log_file_handle = None

    root.mainloop()


if __name__ == "__main__":
    try:
        run_gui()
    except Exception as exc:
        messagebox.showerror("致命错误", str(exc))
        sys.exit(1)
