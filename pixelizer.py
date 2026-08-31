"""
图片像素化工具（纯逻辑模块）
==============================

## 文件功能
把普通图片（特效帧/渲染图/照片）批量转换为像素风 PNG。
管线与 xswj 项目 vfx-tornado / vfx-truck-pass 定稿方式一致：

  1. （可选）色键抠除：纯色背景 → 透明（必须在降采样之前，否则污染调色板）
  2. （可选）自动裁切：按内容 bbox 裁掉空白，整批共享或每帧独立，缩放后居中
  3. 盒滤波降采样（BOX）到目标宽高 → 天然像素网格
  4. 颜色收敛：固定调色板最近色映射，或自动量化生成调色板（批处理共享，防动画闪烁）
  5. 抖动（可选）：Floyd-Steinberg / 有序抖动，输出像素仍精确落在调色板内
  6. alpha 处理：硬阈值（锐利边缘）或保留半透明
  7. 边缘清理（边界像素取不透明邻居主色）→ 去掉混合色描边
  8. 输出 report.json（颜色数/调色板合规/边界色/透明占比/所用参数）

## 架构定位
零 GUI 依赖的纯逻辑模块，供 pixelizer_panel.py（PySide6）调用；
同时支持 CLI 直接运行。

## 用法
python pixelizer.py --input <图片或目录> --out <输出目录> [参数]

尺寸：
  --size N                 正方形快捷方式（默认 0 = 保持原图尺寸）
  --width N --height N     宽高独立（0 = 原图尺寸；可非正方形，如 96 60）
  --pixel-size N           像素块大小 1~64（默认 1 = 每个输出像素一个色块，最精细；
                           N = 每个色块覆盖原图 N×N 像素同色，网格=原图尺寸/N，
                           在该网格上完成像素处理后，整体最近邻缩放到目标尺寸）
  --extra-sizes "128,96"   附加正方形尺寸（仅显式正方形尺寸时生效）

调色板与颜色：
  --palette gray8|sweetie16|<hex,...>   固定调色板（可重复）
  --quantize off|median_cut|octree      自动量化生成调色板（默认 off；批处理共享）
  --quantize-colors N                   自动量化颜色数（默认 16）
  --dither none|floyd|ordered           抖动（默认 none）

透明与边缘：
  --alpha-mode hard|keep                hard=硬阈值（默认），keep=保留半透明
  --alpha-threshold N                   hard 阈值（默认 128）
  --edge-iters N                        边缘清理轮数（默认 2）
  --color-key "0,0,0;255,255,255"       色键抠背景，分号分隔多键（可选）
  --color-key-tol N                     色键容差（默认 50）

裁切与输出：
  --autocrop none|batch|frame           自动裁切（默认 none；batch=整批共享边框防动画跳动）
  --crop-margin N                       裁切边距百分比（默认 6）
  --contact-scale N                     接触表放大倍数（0=不生成，默认 8）

说明：
- 输入为目录时批量处理目录下所有图片（png/jpg/jpeg/bmp/gif/webp）
- GIF 只取第一帧；动画帧请先用「GIF拆分」工具拆成序列
- 输出按 调色板名_尺寸 分子目录，绝不覆盖原图
"""

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# ---- 内置调色板 ----

# Sweetie16（xswj 项目默认游戏调色板）
SWEETIE16_HEX = [
    "1a1c2c", "5d275d", "b13e53", "ef7d57",
    "ffcd75", "a7f070", "38b764", "257179",
    "29366f", "3b5dc9", "41a6f6", "73eff7",
    "f4f4f4", "94b0c2", "566c86", "333c57",
]

# 8 级灰度（黑白素材专用，避免映射 Sweetie16 后变彩色）
GRAY8_HEX = [
    "000000", "242424", "494949", "6d6d6d",
    "929292", "b6b6b6", "dbdbdb", "ffffff",
]

PALETTES = {
    "sweetie16": SWEETIE16_HEX,
    "gray8": GRAY8_HEX,
}

VALID_EXTS = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')


# ---- 调色板工具 ----

def parse_palette(hex_list):
    """十六进制颜色列表 -> int16 RGB 数组 (P,3)。"""
    pal = []
    for h in hex_list:
        h = h.strip().lstrip("#")
        pal.append((int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)))
    return np.array(pal, dtype=np.int16)


def to_palette(a, pal):
    """把每个 RGB 像素映射到调色板最近色（无抖动）。"""
    d = ((a.astype(np.int16)[..., None, :] - pal[None, None, :, :]) ** 2).sum(axis=-1)
    return pal[d.argmin(axis=-1)].astype(np.uint8)


def resolve_palette(val):
    """解析 CLI/面板传入的调色板参数。

    返回 (hex_list, label)：
    - 内置名（sweetie16/gray8）→ 对应列表，label 用名字
    - 逗号分隔十六进制 → 自定义列表，label 用 "custom"
    """
    if val in PALETTES:
        return PALETTES[val], val
    if "," in val:
        hexes = [h.strip() for h in val.split(",") if h.strip()]
        for h in hexes:
            h2 = h.lstrip("#")
            if len(h2) != 6 or not all(c in "0123456789abcdefABCDEF" for c in h2):
                raise ValueError(f"非法颜色: {h}")
        return hexes, "custom"
    raise ValueError(f"未知调色板: {val}（可选 {list(PALETTES)} 或逗号分隔十六进制）")


# ---- 抠图 / 裁切 / 边缘处理 ----

def key_color_alpha(rgb, key=(0, 0, 0), tolerance=50):
    """单键色抠除（兼容单键调用）：与键色距离 <= tolerance 的像素置透明。"""
    return multi_key_alpha(rgb, [key], tolerance)


def multi_key_alpha(rgb, keys, tolerance=50):
    """多键色抠除：与任一键色距离 <= tolerance 的像素置透明（alpha=0），其余 255。

    必须在降采样之前调用，否则背景色会污染降采样后的调色板映射。
    """
    alpha = np.full(rgb.shape[:2], 255, np.uint8)
    for key in keys:
        k = np.array(key, dtype=np.int16)
        dist = np.abs(rgb.astype(np.int16) - k).sum(axis=-1)
        alpha = np.where(dist <= tolerance, 0, alpha)
    return alpha


def content_bbox(arr, alpha_threshold=16):
    """内容包围盒：alpha > 阈值的像素范围 (x0,y0,x1,y1)，无内容返回全图。"""
    a = arr[..., 3]
    ys, xs = np.where(a > alpha_threshold)
    if len(ys) == 0:
        return (0, 0, arr.shape[1], arr.shape[0])
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def _expand_box(box, margin_pct, W, H):
    """按百分比外扩裁切框，并 clamp 到画布内。"""
    x0, y0, x1, y1 = box
    mw = (x1 - x0) * margin_pct / 100.0
    mh = (y1 - y0) * margin_pct / 100.0
    return (max(0, int(x0 - mw)), max(0, int(y0 - mh)),
            min(W, int(x1 + mw)), min(H, int(y1 + mh)))


def _fit_center(arr, width, height):
    """保持比例缩放到目标画布内并居中（透明填充），不拉伸变形。"""
    H, W = arr.shape[:2]
    scale = min(width / W, height / H)
    nw, nh = max(1, round(W * scale)), max(1, round(H * scale))
    im = Image.fromarray(arr).resize((nw, nh), Image.BOX)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    canvas.paste(im, ((width - nw) // 2, (height - nh) // 2), im)
    return np.array(canvas)


def _prep_arr(src, color_keys, color_key_tolerance):
    """打开图片并应用色键抠除（若指定），返回 RGBA ndarray。"""
    img = Image.open(src).convert("RGBA")
    arr = np.array(img)
    if color_keys:
        arr[..., 3] = multi_key_alpha(arr[..., :3], color_keys,
                                      color_key_tolerance)
    return arr


def edge_cleanup(rgba, iters=2):
    """边缘清理：把边界像素颜色替换为不透明邻居的主色，去掉混合色描边。"""
    a = np.array(rgba).copy()
    for _ in range(iters):
        alpha = a[..., 3]
        op = alpha > 0
        tr = alpha == 0
        bnd = np.zeros_like(op)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                s = np.roll(tr, dy, axis=0)
                s = np.roll(s, dx, axis=1)
                bnd |= (op & s)
        ys, xs = np.where(bnd)
        for y, x in zip(ys.tolist(), xs.tolist()):
            neigh = []
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy == 0 and dx == 0:
                        continue
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < a.shape[0] and 0 <= xx < a.shape[1] and a[yy, xx, 3] > 0:
                        neigh.append(tuple(a[yy, xx, :3]))
            if neigh:
                vals, cnts = np.unique(np.array(neigh), axis=0, return_counts=True)
                a[y, x, :3] = vals[np.argmax(cnts)]
    return Image.fromarray(a, "RGBA")


# ---- 自动量化调色板 / 抖动 ----

# Bayer 8x8 有序抖动矩阵（0..63）
BAYER8 = np.array([
    [0, 32, 8, 40, 2, 34, 10, 42],
    [48, 16, 56, 24, 50, 18, 58, 26],
    [12, 44, 4, 36, 14, 46, 6, 38],
    [60, 28, 52, 20, 62, 30, 54, 22],
    [3, 35, 11, 43, 1, 33, 9, 41],
    [51, 19, 59, 27, 49, 17, 57, 25],
    [15, 47, 7, 39, 13, 45, 5, 37],
    [63, 31, 55, 23, 61, 29, 53, 21],
], dtype=np.float32)


def _floyd_dither(rgb, pal):
    """Floyd-Steinberg 误差扩散（手动实现）。

    逐像素取最近色，误差按 7/16 3/16 5/16 1/16 扩散到右/左下/下/右下。
    输出像素始终精确等于调色板中的颜色。
    """
    H, W, _ = rgb.shape
    work = rgb.astype(np.int16).copy()
    out = np.empty((H, W, 3), np.int16)
    for y in range(H):
        for x in range(W):
            px = work[y, x]
            d = ((px[None, :] - pal) ** 2).sum(axis=1)
            qc = pal[d.argmin()]
            out[y, x] = qc
            err = px - qc
            if x + 1 < W:
                work[y, x + 1] += (err * 7) // 16
            if y + 1 < H:
                if x > 0:
                    work[y + 1, x - 1] += (err * 3) // 16
                work[y + 1, x] += (err * 5) // 16
                if x + 1 < W:
                    work[y + 1, x + 1] += err // 16
    return np.clip(out, 0, 255).astype(np.uint8)


def _ordered_dither(rgb, pal):
    """Bayer 8x8 有序抖动（手动实现）。

    思路：对每个像素，在「最近色 c0」与「次近色 c1」之间，按 Bayer 阈值
    扰动后重新取最近色——靠近颜色边界的像素会按阈值翻转到 c1，
    输出像素始终精确等于调色板中的颜色。
    """
    H, W, _ = rgb.shape
    rep = (int(np.ceil(H / 8)), int(np.ceil(W / 8)))
    t = (np.tile(BAYER8, rep)[:H, :W] - 31.5) / 64.0  # [-0.5, 0.5)
    f = rgb.astype(np.float32)
    p = pal.astype(np.float32)
    d = ((f[..., None, :] - p[None, None, :, :]) ** 2).sum(axis=-1)  # (H,W,P)
    i0 = d.argmin(axis=-1)
    c0 = p[i0]
    i1 = np.argpartition(d, 2, axis=-1)[..., 1]
    c1 = p[i1]
    f2 = f + t[..., None] * (c1 - c0)
    d3 = ((f2[..., None, :] - p[None, None, :, :]) ** 2).sum(axis=-1)
    return p[d3.argmin(axis=-1)].astype(np.uint8)


def map_to_palette(rgb, pal, dither="none"):
    """把 RGB 像素映射到调色板；dither 可选抖动。

    输出像素始终精确等于调色板中的颜色（all_in_palette 恒成立）。
    dither: none | floyd | ordered
    """
    if dither == "none":
        return to_palette(rgb, pal)
    if dither == "floyd":
        return _floyd_dither(rgb, pal)
    return _ordered_dither(rgb, pal)


def _sample_rgb(arr, max_pixels=200_000):
    """抽取不透明像素的 RGB 样本（步长采样控制总量），供调色板量化。"""
    h, w = arr.shape[:2]
    step = max(1, int((h * w / max_pixels) ** 0.5))
    rgb = arr[::step, ::step]
    mask = rgb[..., 3] > 128
    return rgb[..., :3][mask]


def build_auto_palette(rgb_samples, colors, method):
    """对像素样本做颜色量化，返回去重后的十六进制颜色列表。

    method: median_cut | octree（Pillow 内置算法，零额外依赖）。
    """
    if len(rgb_samples) == 0:
        raise ValueError("没有可用的像素样本用于量化调色板")
    n = len(rgb_samples)
    # (N,3) 不是合法的图像形状，pad 成正方形再量化
    side = int(np.ceil(np.sqrt(n)))
    buf = np.zeros((side * side, 3), dtype=np.uint8)
    buf[:n] = rgb_samples.astype(np.uint8)
    im = Image.fromarray(buf.reshape(side, side, 3))
    m = (Image.Quantize.MEDIANCUT if method == "median_cut"
         else Image.Quantize.FASTOCTREE)
    q = im.quantize(colors=colors, method=m, dither=Image.Dither.NONE)
    pal = np.array(q.getpalette(), dtype=np.uint8)[:colors * 3].reshape(-1, 3)
    pal = np.unique(pal, axis=0)
    return ["%02x%02x%02x" % tuple(c) for c in pal.tolist()]


# ---- 单图像素化 ----

def pixelize_image(src, out, width, height, palette_hex,
                   alpha_threshold=128, edge_iters=2,
                   color_keys=None, color_key_tolerance=50,
                   dither="none", alpha_mode="hard", crop_box=None,
                   pixel_size=1):
    """单张图片像素化，返回 report 字典。

    参数：
        src: 输入图片路径
        out: 输出 PNG 路径（不覆盖输入）
        width/height: 目标输出尺寸；0 或负数 = 保持原图尺寸
        palette_hex: 十六进制颜色列表
        alpha_threshold: hard 模式下的 alpha 阈值（默认 128）
        edge_iters: 边缘清理轮数（默认 2）
        color_keys: 可选 [(r,g,b), ...] 键色列表，抠除纯色背景（须在降采样前）
        color_key_tolerance: 色键容差（默认 50）
        dither: none | floyd | ordered
        alpha_mode: hard（二值化）| keep（保留半透明）
        crop_box: 可选 (x0,y0,x1,y1)，先裁切再缩放（fit+居中，不拉伸）
        pixel_size: 像素块大小（默认 1 = 最精细，网格=输出尺寸，旧行为）。
                    N(>1) 表示每个色块覆盖原图 N×N 像素（同色）——
                    网格=原图尺寸/N，先在该网格上完成全部像素处理
                    （降采样/调色板/抖动/alpha/边缘清理），
                    最后整体最近邻缩放（NEAREST）到目标输出尺寸。
                    注：网格=输出尺寸/N 时（即 N×输出尺寸=原图尺寸）结果与
                    pixel_size=1 完全一致（数学等价，无信息损失）。
    """
    pal = parse_palette(palette_hex)
    src = Path(src)
    out = Path(out)
    arr = _prep_arr(src, color_keys, color_key_tolerance)
    src_h, src_w = arr.shape[:2]

    # 输出尺寸：0 = 原图尺寸
    if width <= 0:
        width = src_w
    if height <= 0:
        height = src_h
    pixel_size = max(1, int(pixel_size))
    if pixel_size <= 1:
        # 最精细（默认）：每个输出像素一个色块 —— 网格=输出尺寸（旧行为，逐像素映射）
        gw, gh = width, height
    else:
        # 像素块 N：每个色块覆盖原图 N×N 像素（同色）—— 网格基于原图尺寸，
        # 在该网格上完成全部像素处理后，整体最近邻缩放（NEAREST）到目标输出尺寸
        gw = (src_w + pixel_size - 1) // pixel_size
        gh = (src_h + pixel_size - 1) // pixel_size

    if crop_box is not None:
        x0, y0, x1, y1 = crop_box
        arr = arr[y0:y1, x0:x1]
        small = _fit_center(arr, gw, gh)
    else:
        small = np.array(Image.fromarray(arr).resize((gw, gh), Image.BOX))

    # 调色板映射（含抖动）——在网格分辨率上做
    rgb = map_to_palette(small[..., :3], pal, dither)

    # alpha 处理
    if alpha_mode == "hard":
        alpha = np.where(small[..., 3] >= alpha_threshold, 255, 0).astype(np.uint8)
    else:
        alpha = small[..., 3]

    rgba = np.zeros((gh, gw, 4), np.uint8)
    rgba[..., :3] = rgb
    rgba[..., 3] = alpha

    # 边缘清理（网格上），再整体最近邻缩放到输出尺寸
    img2 = edge_cleanup(Image.fromarray(rgba, "RGBA"), iters=edge_iters)
    if gw != width or gh != height:
        img2 = img2.resize((width, height), Image.NEAREST)

    out.parent.mkdir(parents=True, exist_ok=True)
    img2.save(out)

    # 报告
    a = np.array(img2.convert("RGBA"))
    op = a[..., 3] > 0
    cols = np.unique(a[op][:, :3], axis=0).astype(np.int16)
    in_pal = bool(all(any((c == p).all() for p in pal) for c in cols))
    tr = a[..., 3] == 0
    bnd = np.zeros_like(op)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            s2 = np.roll(tr, dy, axis=0)
            s2 = np.roll(s2, dx, axis=1)
            bnd |= (op & s2)
    boundary_colors = int(len(np.unique(a[bnd][:, :3], axis=0))) if bnd.any() else 0
    opaque_pct = round(100 * int(op.sum()) / a[..., 3].size, 1)
    report = {
        "input": str(src), "output": str(out),
        "size": [width, height], "grid": [gw, gh], "pixel_size": pixel_size,
        "colors": int(len(cols)), "all_in_palette": in_pal,
        "boundary_colors": boundary_colors, "opaque_pct": opaque_pct,
    }
    return report


# ---- 批量预处理（共享调色板 / 裁切框）----

def build_shared_palette(files, quantize, quantize_colors,
                         color_keys, color_key_tolerance):
    """批处理共享调色板：采样全部帧的不透明像素做量化（防动画逐帧闪烁）。

    返回 (palette_hex, label)；quantize=off 时返回 (None, None)。
    """
    if quantize == "off":
        return None, None
    samples = []
    for f in files:
        arr = _prep_arr(f, color_keys, color_key_tolerance)
        s = _sample_rgb(arr)
        if len(s):
            samples.append(s)
    if not samples:
        raise ValueError("没有可用的像素样本用于量化调色板")
    palette_hex = build_auto_palette(np.concatenate(samples),
                                     quantize_colors, quantize)
    return palette_hex, f"{quantize}{quantize_colors}"


def compute_crop_boxes(files, autocrop, crop_margin,
                       color_keys, color_key_tolerance):
    """计算每帧裁切框。

    autocrop=batch：全部帧 bbox 求并集（动画帧间大小不跳动）；
    autocrop=frame：每帧独立 bbox。
    返回 {file: box}；autocrop=none 返回 None。
    """
    if autocrop == "none":
        return None
    boxes = {}
    union = None
    for f in files:
        arr = _prep_arr(f, color_keys, color_key_tolerance)
        box = content_bbox(arr)
        if autocrop == "batch":
            union = (box if union is None else
                     (min(union[0], box[0]), min(union[1], box[1]),
                      max(union[2], box[2]), max(union[3], box[3])))
        else:
            boxes[f] = _expand_box(box, crop_margin,
                                   arr.shape[1], arr.shape[0])
    if autocrop == "batch":
        first = _prep_arr(files[0], color_keys, color_key_tolerance)
        H, W = first.shape[:2]
        u = _expand_box(union, crop_margin, W, H)
        boxes = {f: u for f in files}
    return boxes


# ---- 批量处理 ----

def _natural_key(name):
    """自然排序键：Shield-2 < Shield-10（数字按数值比较）。"""
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", name)]


def collect_images(input_path, exclude=None):
    """收集待处理图片；输入为目录则递归收集（可排除输出目录），为文件则单张。

    exclude: 可选输出目录路径——当输出目录在输入目录内部时，
    跳过它避免重复处理自己上次生成的像素图；同时跳过任何名为
    pixelized 的目录（本工具的默认输出名，防止把上次输出当输入）。
    """
    p = Path(input_path)
    if p.is_file():
        return [p]
    if p.is_dir():
        ex = None
        if exclude:
            ex = str(Path(exclude).resolve())
        files = []
        for f in p.rglob("*"):
            if f.suffix.lower() not in VALID_EXTS:
                continue
            if ex and str(f.resolve()).startswith(ex):
                continue
            if any(part == "pixelized" for part in f.parts[:-1]):
                continue
            files.append(f)
        return sorted(files, key=lambda f: _natural_key(f.name))
    raise FileNotFoundError(f"输入不存在: {input_path}")


def process_directory(input_dir, out_dir, width, height, palette_hex, palette_label,
                      alpha_threshold=128, edge_iters=2,
                      color_keys=None, color_key_tolerance=50,
                      dither="none", alpha_mode="hard",
                      autocrop="none", crop_margin=6,
                      quantize="off", quantize_colors=16,
                      contact_scale=0, extra_sizes=(), pixel_size=1):
    """批量像素化一个目录，输出到 out_dir/<label>_<尺寸标签>/，写 report.json。

    width/height 为 0 表示保持原图尺寸（尺寸标签用 orig）；
    返回汇总文本行列表（供 CLI/面板日志使用）。
    """
    files = collect_images(input_dir, exclude=out_dir)
    if not files:
        return [f"没有找到图片文件: {input_dir}"]

    # 共享调色板（自动量化）
    if quantize != "off":
        palette_hex, palette_label = build_shared_palette(
            files, quantize, quantize_colors, color_keys, color_key_tolerance)

    # 裁切框
    crop_boxes = compute_crop_boxes(files, autocrop, crop_margin,
                                    color_keys, color_key_tolerance)

    # 附加尺寸（仅显式正方形时生效）
    sizes = [(width, height)]
    if extra_sizes and width > 0 and height > 0 and width == height:
        sizes += [(s, s) for s in extra_sizes]

    lines = []
    for (w, h) in sizes:
        tag = f"{w}x{h}" if (w > 0 and h > 0) else "orig"
        if pixel_size > 1:
            tag += f"_p{pixel_size}"
        sub = Path(out_dir) / f"{palette_label}_{tag}"
        sub.mkdir(parents=True, exist_ok=True)
        reports = []
        for f in files:
            out_p = sub / (f.stem + ".png")
            try:
                rep = pixelize_image(f, out_p, w, h, palette_hex,
                                     alpha_threshold, edge_iters,
                                     color_keys, color_key_tolerance,
                                     dither, alpha_mode,
                                     None if crop_boxes is None else crop_boxes[f],
                                     pixel_size)
            except Exception as e:
                rep = {"input": str(f), "output": "", "error": str(e)}
            reports.append(rep)

        ok = [r for r in reports if "error" not in r]
        params = {
            "size": [w, h], "pixel_size": pixel_size, "palette": palette_label,
            "palette_hex": palette_hex,
            "alpha_threshold": alpha_threshold, "edge_iters": edge_iters,
            "color_keys": color_keys, "color_key_tolerance": color_key_tolerance,
            "dither": dither, "alpha_mode": alpha_mode,
            "autocrop": autocrop, "crop_margin": crop_margin,
            "quantize": quantize, "quantize_colors": quantize_colors,
        }
        report_path = sub / "report.json"
        report_path.write_text(json.dumps(
            {"params": params, "files": reports},
            ensure_ascii=False, indent=2), encoding="utf-8")

        summary = {
            "subdir": str(sub), "files": len(reports), "ok": len(ok),
            "avg_colors": round(sum(r["colors"] for r in ok) / len(ok), 1) if ok else 0,
            "avg_opaque_pct": round(sum(r["opaque_pct"] for r in ok) / len(ok), 1) if ok else 0,
            "all_in_palette": all(r["all_in_palette"] for r in ok) if ok else False,
        }
        lines.append(f"{palette_label}_{tag}: {summary['files']} 张，成功 {summary['ok']}，"
                     f"平均颜色 {summary['avg_colors']}，平均透明占比 {100 - summary['avg_opaque_pct']}%，"
                     f"全部在调色板内={summary['all_in_palette']}")

        if contact_scale > 0 and ok:
            cs = build_contact_sheet(sub, scale=contact_scale)
            if cs:
                lines.append(f"  接触表: {cs}")

    return lines


def build_contact_sheet(png_dir, cols=4, scale=8, out_name="_contact_sheet.png"):
    """把目录内所有 PNG 按自然序拼成一张放大接触表（最近邻放大，像素不变形）。"""
    png_dir = Path(png_dir)
    files = sorted([p for p in png_dir.glob("*.png") if p.name != out_name],
                   key=lambda p: _natural_key(p.name))
    if not files:
        return None
    w0, h0 = Image.open(files[0]).size
    rows = (len(files) + cols - 1) // cols
    cell_w, cell_h = w0 * scale, h0 * scale
    canvas = Image.new("RGBA", (cols * cell_w, rows * cell_h), (0, 0, 0, 0))
    for i, p in enumerate(files):
        im = Image.open(p).convert("RGBA").resize((cell_w, cell_h), Image.NEAREST)
        canvas.paste(im, ((i % cols) * cell_w, (i // cols) * cell_h), im)
    out_p = png_dir / out_name
    canvas.save(out_p)
    return out_p


# ---- CLI ----

def _parse_color_keys(text):
    """解析色键：分号分隔多键，如 "0,0,0;255,255,255"。"""
    keys = []
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        p = [int(v) for v in part.split(",")]
        if len(p) != 3 or any(not 0 <= v <= 255 for v in p):
            raise ValueError(f"色键格式无效: {part}（需为 r,g,b，如 0,0,0）")
        keys.append(tuple(p))
    return keys


def main():
    ap = argparse.ArgumentParser(description="图片像素化批量转换（盒滤波 + 调色板 + 边缘清理）")
    ap.add_argument("--input", required=True, help="输入图片或目录")
    ap.add_argument("--out", required=True, help="输出目录（按 调色板名_宽x高 分子目录）")
    ap.add_argument("--size", type=int, default=0, help="正方形目标尺寸（0=保持原图尺寸，默认；等价 --width N --height N）")
    ap.add_argument("--width", type=int, default=0, help="目标宽度（0=原图尺寸；独立设置可非正方形输出）")
    ap.add_argument("--height", type=int, default=0, help="目标高度（0=原图尺寸）")
    ap.add_argument("--pixel-size", type=int, default=1,
                    help="像素块大小 1~64（默认 1=每个输出像素一个色块，最精细；"
                         "N=每个色块覆盖原图 N×N 像素同色，网格=原图尺寸/N，"
                         "在该网格上完成像素处理后整体最近邻缩放到目标尺寸）")
    ap.add_argument("--extra-sizes", default="", help="附加正方形尺寸，逗号分隔，如 128,96（仅 width==height 时生效）")
    ap.add_argument("--palette", action="append", default=["sweetie16"],
                    help="调色板（可重复）：sweetie16 / gray8 / 逗号分隔十六进制")
    ap.add_argument("--quantize", choices=["off", "median_cut", "octree"], default="off",
                    help="自动量化生成调色板（默认 off；批处理共享，防动画闪烁）")
    ap.add_argument("--quantize-colors", type=int, default=16, help="自动量化颜色数（默认 16）")
    ap.add_argument("--dither", choices=["none", "floyd", "ordered"], default="none",
                    help="抖动：none / floyd(Floyd-Steinberg) / ordered(有序 Bayer)（默认 none）")
    ap.add_argument("--alpha-mode", choices=["hard", "keep"], default="hard",
                    help="alpha 处理：hard=硬阈值（默认）/ keep=保留半透明")
    ap.add_argument("--alpha-threshold", type=int, default=128, help="alpha 硬阈值（默认 128）")
    ap.add_argument("--edge-iters", type=int, default=2, help="边缘清理轮数（默认 2）")
    ap.add_argument("--color-key", default="", help="色键抠除背景，分号分隔多键，如 0,0,0;255,255,255（可选）")
    ap.add_argument("--color-key-tol", type=int, default=50, help="色键容差（默认 50）")
    ap.add_argument("--autocrop", choices=["none", "batch", "frame"], default="none",
                    help="自动裁切内容 bbox：none / batch(整批共享) / frame(每帧独立)（默认 none）")
    ap.add_argument("--crop-margin", type=int, default=6, help="裁切边距百分比（默认 6）")
    ap.add_argument("--contact-scale", type=int, default=8,
                    help="生成接触表放大倍数（0=不生成，默认 8）")
    args = ap.parse_args()

    extra = [int(s) for s in args.extra_sizes.split(",") if s.strip()]
    if any(s <= 0 for s in extra):
        print("--extra-sizes 需为正整数", file=sys.stderr)
        return 1

    width = args.width or args.size
    height = args.height or args.size
    if width < 0 or height < 0:
        print("尺寸不能为负数", file=sys.stderr)
        return 1
    if not 1 <= args.pixel_size <= 64:
        print("--pixel-size 需在 1~64 之间", file=sys.stderr)
        return 1

    color_keys = None
    if args.color_key:
        try:
            color_keys = _parse_color_keys(args.color_key)
        except ValueError as e:
            print(f"错误: {e}", file=sys.stderr)
            return 1

    try:
        if args.quantize != "off":
            # 自动量化：整批共享调色板（防动画闪烁），忽略 --palette
            palette_hex, label = build_shared_palette(
                collect_images(args.input), args.quantize,
                args.quantize_colors, color_keys, args.color_key_tol)
            lines = process_directory(
                args.input, args.out, width, height,
                palette_hex, label,
                alpha_threshold=args.alpha_threshold,
                edge_iters=args.edge_iters,
                color_keys=color_keys,
                color_key_tolerance=args.color_key_tol,
                dither=args.dither, alpha_mode=args.alpha_mode,
                autocrop=args.autocrop, crop_margin=args.crop_margin,
                quantize="off", contact_scale=args.contact_scale,
                extra_sizes=extra, pixel_size=args.pixel_size)
            print("\n".join(lines))
        else:
            for val in args.palette:
                palette_hex, label = resolve_palette(val)
                lines = process_directory(
                    args.input, args.out, width, height,
                    palette_hex, label,
                    alpha_threshold=args.alpha_threshold,
                    edge_iters=args.edge_iters,
                    color_keys=color_keys,
                    color_key_tolerance=args.color_key_tol,
                    dither=args.dither, alpha_mode=args.alpha_mode,
                    autocrop=args.autocrop, crop_margin=args.crop_margin,
                    quantize="off", contact_scale=args.contact_scale,
                    extra_sizes=extra, pixel_size=args.pixel_size)
                print("\n".join(lines))
    except (ValueError, FileNotFoundError) as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
