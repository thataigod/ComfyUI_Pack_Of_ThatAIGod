"""Image Saver Plus node for ComfyUI.

Saves images in PNG, JPEG, WebP, AVIF, or EXR format with:
- Quality / compression control, bit depth, color space, and channel selection
- AVIF CRF control plus still-image or animated output
- Filename template variables: %date:FORMAT%, %year%, %month%, %day%,
  %hour%, %minute%, %second%, %counter%, %batch_num%, %width%, %height%
- Optional .txt sidecar files saved alongside each image
- ComfyUI workflow metadata embedded in PNG, AVIF, and EXR files
- A large-resolution AVIF fallback that avoids SVT-AV1's 8704 px height cap
"""

import importlib
import json
import logging
import os
import re
import struct
import zlib
from datetime import datetime
from fractions import Fraction
from typing import Any

import folder_paths
import numpy as np
import torch
from PIL import Image
from PIL import features as pil_features
from PIL.PngImagePlugin import PngInfo

logger: logging.Logger = logging.getLogger("ThatAIGod")

COMPRESS_MIN: int = 0
COMPRESS_MAX: int = 9
COMPRESS_DEFAULT: int = 4
QUALITY_MIN: int = 1
QUALITY_MAX: int = 100
QUALITY_DEFAULT: int = 95
CRF_MIN: int = 1
CRF_MAX: int = 63
CRF_DEFAULT: int = 18

FILE_FORMATS: tuple[str, ...] = ("png", "jpeg", "webp", "avif", "exr")
BIT_DEPTH_OPTIONS: list[str] = [
    "auto",
    "8-bit",
    "16-bit",
    "8-bit YUV420",
    "10-bit YUV420",
    "16-bit float",
    "32-bit float",
]
COLOR_SPACE_OPTIONS: list[str] = ["sRGB", "HDR", "HDR PQ", "linear", "linear ACEScg"]
CHANNEL_OPTIONS: list[str] = [
    "auto",
    "grayscale (1 channel)",
    "RGB (3 channels)",
    "RGBA (4 channels)",
]
SAVE_MODE_OPTIONS: list[str] = ["still images", "animated"]

# SVT-AV1 (used by the default ComfyUI AVIF path) rejects frames taller than
# 8704 px and wider than 16384 px. Larger images are routed to Pillow/libavif.
AVIF_SVT_MAX_WIDTH: int = 16384
AVIF_SVT_MAX_HEIGHT: int = 8704

_AVIF_COLORSPACES: tuple[str, ...] = ("sRGB", "HDR", "HDR PQ")
_EXR_COLORSPACES: tuple[str, ...] = ("sRGB", "HDR", "linear", "linear ACEScg")

_DATE_PATTERN: re.Pattern[str] = re.compile(r"%date:([^%]+)%")
# Ordered list of (token, strftime_code) pairs mapping Java/.NET-style date tokens
# to Python strftime format codes. Order matters: longer tokens (e.g. "yyyy") must
# be replaced before their substrings (e.g. "yy").
_DATE_FORMAT_MAP: list[tuple[str, str]] = [
    ("yyyy", "%Y"),
    ("yy", "%y"),
    ("MM", "%m"),
    ("dd", "%d"),
    ("HH", "%H"),
    ("mm", "%M"),
    ("ss", "%S"),
]

# Shorthand variable names and their equivalent strftime codes.
# These are expanded before %date:FORMAT% processing so that users can write
# %year% instead of the more verbose %date:yyyy%.
_SHORTHAND_VARS: list[tuple[str, str]] = [
    ("%year%", "%Y"),
    ("%month%", "%m"),
    ("%day%", "%d"),
    ("%hour%", "%H"),
    ("%minute%", "%M"),
    ("%second%", "%S"),
]

# Characters Windows forbids in file and directory names.  Date templates
# like %date:HH:mm% expand to strings containing ':' which would otherwise
# fail the whole batch on Windows.
_WINDOWS_INVALID_CHARS: str = '<>:"|?*'
# Path separators are preserved; every other segment is sanitised.
_SEGMENT_SPLIT_RE: re.Pattern[str] = re.compile(r"([/\\])")

_PNG_SIGNATURE: bytes = b"\x89PNG\r\n\x1a\n"
_PNG16_FORMATS: dict[int, tuple[str, str]] = {
    1: ("gray16le", "gray16be"),
    3: ("rgb48le", "rgb48be"),
    4: ("rgba64le", "rgba64be"),
}
_EXR_FORMATS: dict[int, str] = {
    1: "grayf32le",
    3: "gbrpf32le",
    4: "gbrapf32le",
}

# HLG OETF constants from BT.2100 Table 5.
_HLG_A: float = 0.17883277
_HLG_B: float = 0.28466892
_HLG_C: float = 0.55991072928


def _load_av() -> Any:
    """Import PyAV lazily so the PNG/JPEG/WebP paths work without it.

    Returns:
        The ``av`` module when importable, otherwise ``None``.
    """
    try:
        return importlib.import_module("av")
    except ImportError:
        return None


av: Any = _load_av()


def _sanitize_filename_segment(segment: str) -> str:
    """Replace Windows-invalid characters in one filename template segment.

    Args:
        segment: A single path segment (no separators) of the expanded prefix.

    Returns:
        The segment with ``<>:"|?*`` mapped to ``_`` and any trailing dots or
        spaces removed; never empty (falls back to ``_``).
    """
    cleaned: str = "".join("_" if ch in _WINDOWS_INVALID_CHARS else ch for ch in segment)
    cleaned = cleaned.rstrip(" .")
    return cleaned or "_"


def _sanitize_filename_template(prefix: str) -> str:
    """Sanitise each path segment of an expanded filename prefix.

    Path separators (``/`` and ``\\``) are preserved so subfolder templates
    keep working; only the name segments are cleaned.

    Args:
        prefix: The expanded filename prefix (date/shorthand variables already
            substituted).

    Returns:
        The prefix with Windows-invalid characters replaced per segment.
    """
    parts: list[str] = _SEGMENT_SPLIT_RE.split(prefix)
    return "".join(_sanitize_filename_segment(part) if i % 2 == 0 else part for i, part in enumerate(parts))


def _resolve_date_format(format_str: str) -> str:
    """Apply a Java/.NET-style date format string to the current local datetime.

    Tokens are replaced left-to-right (longer tokens first to avoid substring
    collisions), then ``datetime.strftime`` is called on the result.

    Args:
        format_str: A format string using tokens like ``yyyy``, ``MM``, ``dd``.

    Returns:
        The formatted date string, e.g. ``"2026_05_30"`` for ``"yyyy_MM_dd"``.
    """
    fmt: str = format_str
    for token, code in _DATE_FORMAT_MAP:
        fmt = fmt.replace(token, code)
    return datetime.now().strftime(fmt)


def _find_next_counter(folder: str, filename_template: str) -> int:
    """Scan *folder* for existing files that match *filename_template* and return the next counter.

    The template must contain the literal string ``%counter%`` exactly once.
    Existing files are matched via a regex that accepts a counter of any digit
    count in that position (e.g. ``img_00003_test.png`` or
    ``img_100000_test.png``), so the sequence keeps working past 99 999 files.
    The function returns ``max_found + 1``, or ``1`` if no matching files exist.

    Args:
        folder: Absolute path to the output directory.  If the directory does
            not exist, ``1`` is returned immediately.
        filename_template: The filename stem (no extension) containing
            ``%counter%`` as a placeholder.

    Returns:
        The next available counter value (1-indexed).
    """
    if not os.path.isdir(folder):
        return 1
    prefix_part, suffix_part = filename_template.split("%counter%", 1)
    escaped: str = re.escape(prefix_part) + r"(\d+)" + re.escape(suffix_part) + r"(?:\.[a-zA-Z0-9]+)?$"
    pattern: re.Pattern[str] = re.compile(escaped)
    max_c: int = 0
    for fname in os.listdir(folder):
        m = pattern.match(fname)
        if m:
            max_c = max(max_c, int(m.group(1)))
    return max_c + 1


def _resolve_bit_depth(file_format: str, bit_depth: str, colorspace: str) -> str:
    """Map a shared bit-depth widget value to the concrete depth for a format.

    ``"auto"`` selects PNG 8-bit, AVIF 10-bit for HDR inputs (8-bit otherwise),
    and EXR 16-bit float. Values that do not belong to the format fall back to
    that format's default with a warning.

    Args:
        file_format: One of :data:`FILE_FORMATS`.
        bit_depth: The raw widget value (``"auto"`` or a depth label).
        colorspace: The resolved color space for the image.

    Returns:
        A depth label valid for the target format.
    """
    if file_format == "png":
        if bit_depth == "auto":
            return "8-bit"
        if bit_depth in ("8-bit", "16-bit"):
            return bit_depth
        logger.warning("Bit depth %r is not supported for PNG; using 8-bit", bit_depth)
        return "8-bit"
    if file_format == "avif":
        if bit_depth == "auto":
            return "10-bit YUV420" if colorspace in ("HDR", "HDR PQ") else "8-bit YUV420"
        if bit_depth in ("8-bit YUV420", "10-bit YUV420"):
            return bit_depth
        logger.warning("Bit depth %r is not supported for AVIF; using 8-bit YUV420", bit_depth)
        return "8-bit YUV420"
    if file_format == "exr":
        if bit_depth == "auto":
            return "16-bit float"
        if bit_depth in ("16-bit float", "32-bit float"):
            return bit_depth
        logger.warning("Bit depth %r is not supported for EXR; using 16-bit float", bit_depth)
        return "16-bit float"
    return bit_depth


def _resolve_color_space(file_format: str, colorspace: str) -> str:
    """Constrain a shared color-space widget value to one a format supports.

    Args:
        file_format: One of :data:`FILE_FORMATS`.
        colorspace: The raw widget value.

    Returns:
        A color space valid for the target format.
    """
    if file_format == "avif":
        if colorspace in _AVIF_COLORSPACES:
            return colorspace
        logger.warning("Color space %r is not supported for AVIF; using sRGB", colorspace)
        return "sRGB"
    if file_format == "exr":
        if colorspace in _EXR_COLORSPACES:
            return colorspace
        if colorspace == "HDR PQ":
            logger.warning("EXR has no PQ transfer function; treating HDR PQ input as HLG (HDR)")
            return "HDR"
        logger.warning("Color space %r is not supported for EXR; using sRGB", colorspace)
        return "sRGB"
    return "sRGB"


def _srgb_to_linear(t: torch.Tensor) -> torch.Tensor:
    """Apply the inverse sRGB EOTF to RGB channels, passing alpha through."""
    if t.shape[-1] == 4:
        rgb, alpha = t[..., :3], t[..., 3:]
        return torch.cat([_srgb_to_linear(rgb), alpha], dim=-1)
    low = t / 12.92
    high = ((t.clamp(min=0.0) + 0.055) / 1.055) ** 2.4
    return torch.where(t <= 0.04045, low, high)


def _hlg_to_linear(t: torch.Tensor) -> torch.Tensor:
    """Apply the inverse HLG OETF (BT.2100), passing alpha through."""
    if t.shape[-1] == 4:
        rgb, alpha = t[..., :3], t[..., 3:]
        return torch.cat([_hlg_to_linear(rgb), alpha], dim=-1)
    low = (t**2) / 3.0
    high = (torch.exp((t.clamp(min=0.5) - _HLG_C) / _HLG_A) + _HLG_B) / 12.0
    return torch.where(t <= 0.5, low, high)


def _to_scene_linear(image: torch.Tensor, colorspace: str) -> torch.Tensor:
    """Convert an image in *colorspace* to scene-linear EXR values."""
    if colorspace == "sRGB":
        return _srgb_to_linear(image)
    if colorspace == "HDR":
        return _hlg_to_linear(image)
    if colorspace in ("linear", "linear ACEScg"):
        return image
    raise ValueError(f"Unsupported EXR color space: {colorspace}")


def _encode_via_pyav(
    codec_name: str,
    array: np.ndarray,
    frame_format: str,
    stream_format: str,
    options: dict[str, str] | None = None,
) -> bytes:
    """Encode a single frame with PyAV and return the raw codec payload."""
    if av is None:
        raise RuntimeError("PyAV is required for this format; install the 'av' package bundled with ComfyUI.")
    codec = av.CodecContext.create(codec_name, "w")
    codec.width = array.shape[1]
    codec.height = array.shape[0]
    codec.pix_fmt = stream_format
    codec.time_base = Fraction(1, 1)
    if options:
        codec.options = options
    frame = av.VideoFrame.from_ndarray(array, format=frame_format)
    if frame_format != stream_format:
        frame = frame.reformat(format=stream_format)
    frame.pts = 0
    frame.time_base = codec.time_base
    packets = list(codec.encode(frame)) + list(codec.encode(None))
    return b"".join(bytes(packet) for packet in packets)


def _encode_png16(image: torch.Tensor) -> bytes:
    """Encode an image tensor as a 16-bit PNG through PyAV."""
    if image.ndim == 2:
        image = image.unsqueeze(-1)
    channels: int = image.shape[-1]
    formats = _PNG16_FORMATS.get(channels)
    if formats is None:
        raise ValueError(f"16-bit PNG supports 1, 3, or 4 channels; got {channels}.")
    array = (image * 65535.0).clamp(0, 65535).to(torch.int32).cpu().numpy().astype(np.uint16)
    if channels == 1:
        array = array[..., 0]
    return _encode_via_pyav("png", array, formats[0], formats[1])


def _encode_exr(image: torch.Tensor, bit_depth: str, colorspace: str) -> bytes:
    """Encode an image tensor as an EXR through PyAV."""
    if image.ndim == 2:
        image = image.unsqueeze(-1)
    channels: int = image.shape[-1]
    frame_format = _EXR_FORMATS.get(channels)
    if frame_format is None:
        raise ValueError(f"EXR supports 1, 3, or 4 channels; got {channels}.")
    linear = _to_scene_linear(image, colorspace)
    if bit_depth == "16-bit float":
        linear = linear.to(torch.float16)
    array = linear.cpu().numpy().astype(np.float32)
    options = {"format": "half" if bit_depth == "16-bit float" else "float", "compression": "zip16"}
    return _encode_via_pyav("exr", array, frame_format, frame_format, options)


def _png_text_chunk(keyword: str, text: str) -> bytes:
    """Build one PNG tEXt chunk."""
    payload = keyword.encode("latin-1") + b"\x00" + text.encode("latin-1", errors="replace")
    crc = zlib.crc32(b"tEXt" + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + b"tEXt" + payload + struct.pack(">I", crc)


def _inject_png_metadata(png_bytes: bytes, prompt: dict | None, extra_pnginfo: dict | None) -> bytes:
    """Insert prompt/workflow tEXt chunks right after the PNG IHDR chunk."""
    if not png_bytes.startswith(_PNG_SIGNATURE):
        return png_bytes
    chunks: list[bytes] = []
    if prompt is not None:
        chunks.append(_png_text_chunk("prompt", json.dumps(prompt)))
    if extra_pnginfo:
        for key, value in extra_pnginfo.items():
            chunks.append(_png_text_chunk(key, json.dumps(value)))
    if not chunks:
        return png_bytes
    ihdr_length = struct.unpack(">I", png_bytes[8:12])[0]
    ihdr_end = 8 + 8 + ihdr_length + 4
    return png_bytes[:ihdr_end] + b"".join(chunks) + png_bytes[ihdr_end:]


def _inject_exr_metadata(
    exr_bytes: bytes,
    prompt: dict | None,
    extra_pnginfo: dict | None,
    colorspace: str,
) -> bytes:
    """Embed workflow and chromaticity metadata using ComfyUI's EXR injector.

    The default-node helper is reused when available so our EXR files stay
    byte-compatible with ComfyUI's own Save Image (Advanced) output. When the
    helper is unavailable or rejects the payload, the image is still written.
    """
    try:
        from comfy_extras.nodes_images import inject_exr_metadata
    except ImportError:
        return exr_bytes
    try:
        result: bytes = inject_exr_metadata(exr_bytes, prompt, extra_pnginfo, colorspace)
        return result
    except Exception as e:
        logger.warning("Could not embed EXR metadata: %s", e)
        return exr_bytes


def _inject_avif_metadata(path: str, metadata: dict | None) -> None:
    """Embed workflow metadata using ComfyUI's AVIF box rewriter when available."""
    if not metadata:
        return
    try:
        from comfy_extras.nodes_images import inject_avif_metadata
    except ImportError:
        return
    try:
        inject_avif_metadata(path, metadata)
    except Exception as e:
        logger.warning("Could not embed AVIF metadata in %s: %s", path, e)


def _to_pil(image: torch.Tensor) -> Image.Image:
    """Convert a float image tensor to an 8-bit Pillow image."""
    array = np.clip(255.0 * image.cpu().numpy(), 0, 255).astype(np.uint8)
    if array.ndim == 3 and array.shape[-1] == 1:
        array = array[..., 0]
    return Image.fromarray(array)


def _avif_exif(metadata: dict) -> bytes:
    """Encode ComfyUI metadata as EXIF tags understood by the frontend."""
    exif = Image.Exif()
    if "prompt" in metadata:
        exif[0x0110] = f"prompt:{json.dumps(metadata['prompt'])}"
    next_tag = 0x010F
    for key, value in metadata.items():
        if key == "prompt":
            continue
        exif[next_tag] = f"{key}:{json.dumps(value)}"
        next_tag -= 1
    return bytes(exif.tobytes())


def _save_avif_pillow(
    images: torch.Tensor,
    output_path: str,
    crf: int,
    fps: float,
    animated: bool,
    metadata: dict | None,
) -> None:
    """Save AVIF through Pillow/libavif, which has no SVT-AV1 size limit."""
    if not pil_features.check("avif"):
        raise RuntimeError("Pillow was built without AVIF support; use a Pillow build with libavif.")
    frames = [_to_pil(image) for image in images]
    exif = _avif_exif(metadata) if metadata else None
    quality = max(1, min(100, 100 - crf))
    save_args: dict[str, Any] = {"format": "AVIF", "quality": quality, "speed": 6}
    if exif is not None:
        save_args["exif"] = exif
    if animated:
        save_args.update(
            {
                "save_all": True,
                "append_images": frames[1:],
                "duration": max(1, round(1000.0 / max(fps, 0.01))),
            }
        )
    frames[0].save(output_path, **save_args)


def _avif_color_properties(colorspace: str) -> tuple[Any, Any, int, Any]:
    """Return PyAV color signaling for an AVIF color-space choice."""
    from av.video.reformatter import ColorPrimaries, ColorRange, ColorTrc

    mapping: dict[str, tuple[Any, Any, int]] = {
        "sRGB": (ColorPrimaries.BT709, ColorTrc.IEC61966_2_1, 1),
        "HDR": (ColorPrimaries.BT2020, ColorTrc.ARIB_STD_B67, 9),
        "HDR PQ": (ColorPrimaries.BT2020, ColorTrc.SMPTE2084, 9),
    }
    color_primaries, color_trc, yuv_colorspace = mapping[colorspace]
    return color_primaries, color_trc, yuv_colorspace, ColorRange.MPEG


def _set_avif_color_properties(target: Any, properties: tuple[Any, Any, int, Any]) -> None:
    """Apply color primaries/transfer/range to a frame or codec context."""
    color_primaries, color_trc, yuv_colorspace, color_range = properties
    target.color_primaries = color_primaries
    target.color_trc = color_trc
    target.colorspace = yuv_colorspace
    target.color_range = color_range


def _avif_frame(
    image: torch.Tensor,
    bit_depth: str,
    colorspace: str,
    pixel_format: str,
    properties: tuple[Any, Any, int, Any],
) -> Any:
    """Convert one tensor frame into a PyAV video frame for AVIF encoding."""
    if image.ndim == 2:
        image = image.unsqueeze(-1)
    channels: int = image.shape[-1]
    if channels not in (1, 3):
        raise ValueError(
            "AVIF saving with the PyAV encoder supports 1-channel grayscale and 3-channel RGB; "
            "RGBA is encoded through the Pillow/libavif fallback."
        )
    if bit_depth == "10-bit YUV420":
        array = (image * 65535.0).clamp(0, 65535).to(torch.int32).cpu().numpy().astype(np.uint16)
        frame_format = "gray16le" if channels == 1 else "rgb48le"
    else:
        array = (image * 255.0).clamp(0, 255).to(torch.uint8).cpu().numpy()
        frame_format = "gray" if channels == 1 else "rgb24"
    if channels == 1:
        array = array[..., 0]
    frame = av.VideoFrame.from_ndarray(array, format=frame_format)
    frame = frame.reformat(format=pixel_format, dst_colorspace=properties[2])
    _set_avif_color_properties(frame, properties)
    return frame


def _save_avif_pyav(
    images: torch.Tensor,
    output_path: str,
    bit_depth: str,
    colorspace: str,
    crf: int,
    fps: float,
    loop_count: int | None,
    metadata: dict | None,
) -> None:
    """Save AVIF with PyAV/SVT-AV1, including 10-bit and HDR signaling."""
    properties = _avif_color_properties(colorspace)
    pixel_format = "yuv420p10le" if bit_depth == "10-bit YUV420" else "yuv420p"
    options = {"loop": str(loop_count)} if loop_count is not None else None
    with av.open(output_path, mode="w", format="avif", options=options) as container:
        stream = container.add_stream("libsvtav1", rate=Fraction(round(fps * 1000), 1000))
        stream.width = images.shape[2]
        stream.height = images.shape[1]
        stream.pix_fmt = pixel_format
        stream.options = {"crf": str(crf), "preset": "8"}
        _set_avif_color_properties(stream.codec_context, properties)
        for image in images:
            for packet in stream.encode(_avif_frame(image, bit_depth, colorspace, pixel_format, properties)):
                container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    _inject_avif_metadata(output_path, metadata)


def _save_avif(
    images: torch.Tensor,
    output_path: str,
    bit_depth: str,
    colorspace: str,
    crf: int,
    fps: float,
    loop_count: int,
    animated: bool,
    metadata: dict | None,
) -> None:
    """Save AVIF, falling back to Pillow/libavif beyond SVT-AV1's size limits.

    The default ComfyUI node hardcodes ``libsvtav1`` and fails for images taller
    than 8704 px (e.g. a 48 MP 2:3 image). We attempt PyAV first for full
    bit-depth/HDR support, then transparently re-encode through Pillow's
    libavif/AV1 encoder, which supports much larger frames.

    Args:
        images: A ``(N, H, W, C)`` tensor. Animated mode encodes all N frames
            into one file; still mode is called with a single-frame tensor.
        output_path: Destination ``.avif`` path.
        bit_depth: ``"8-bit YUV420"`` or ``"10-bit YUV420"``.
        colorspace: ``"sRGB"``, ``"HDR"``, or ``"HDR PQ"``.
        crf: AV1 CRF (1-63).
        fps: Frame rate for animated output.
        loop_count: Animation loop count (0 = forever).
        animated: Whether to write a single animated AVIF.
        metadata: Prompt/workflow metadata to embed when supported.
    """
    width, height = int(images.shape[2]), int(images.shape[1])
    if av is not None and width <= AVIF_SVT_MAX_WIDTH and height <= AVIF_SVT_MAX_HEIGHT:
        try:
            _save_avif_pyav(images, output_path, bit_depth, colorspace, crf, fps, loop_count if animated else None, metadata)
            return
        except Exception as e:
            logger.warning("PyAV AVIF encode failed for %dx%d (%s); falling back to Pillow/libavif", width, height, e)
            try:
                os.remove(output_path)
            except OSError:
                pass
    elif av is not None:
        logger.info(
            "Image is %dx%d, beyond SVT-AV1's %dx%d limit; using the Pillow/libavif encoder",
            width,
            height,
            AVIF_SVT_MAX_WIDTH,
            AVIF_SVT_MAX_HEIGHT,
        )
    if bit_depth == "10-bit YUV420" or colorspace != "sRGB":
        logger.warning(
            "Pillow/libavif fallback writes 8-bit SDR AVIF; requested %s / %s signaling is not preserved",
            bit_depth,
            colorspace,
        )
    if animated and loop_count:
        logger.warning("Pillow/libavif fallback cannot set loop_count; using the encoder default")
    _save_avif_pillow(images, output_path, crf, fps, animated, metadata)


def _apply_png_channels(image: torch.Tensor, channels: str) -> torch.Tensor:
    """Apply the PNG ``channels`` conversion to one image tensor."""
    if image.ndim == 2:
        image = image.unsqueeze(-1)
    if channels == "grayscale (1 channel)" and image.shape[-1] in (3, 4):
        image = 0.299 * image[..., :1] + 0.587 * image[..., 1:2] + 0.114 * image[..., 2:3]
    elif channels in ("RGB (3 channels)", "RGBA (4 channels)"):
        if image.shape[-1] == 1:
            image = image.expand(-1, -1, 3)
        if channels == "RGB (3 channels)":
            image = image[..., :3]
        elif image.shape[-1] == 3:
            image = torch.cat((image, torch.ones_like(image[..., :1])), dim=-1)
    return image


def _build_base_file(filename_template: str, batch_number: int, counter: int) -> str:
    """Expand batch and counter placeholders into one file stem."""
    name = filename_template.replace("%batch_num%", str(batch_number))
    if "%counter%" in name:
        return name.replace("%counter%", f"{counter:05}", 1)
    return f"{name}_{counter:05}_"


def _write_sidecar(folder: str, base_file: str, save_text: str | None) -> None:
    """Write the optional ``.txt`` sidecar; failures never abort the batch."""
    if not save_text:
        return
    text_path = os.path.join(folder, f"{base_file}.txt")
    try:
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(save_text)
    except OSError as e:
        logger.error("Failed to write sidecar %s: %s", text_path, e)


def _png_info(prompt: dict | None, extra_pnginfo: dict | None) -> PngInfo | None:
    """Build PNG tEXt metadata for the 8-bit Pillow save path."""
    if prompt is None and not extra_pnginfo:
        return None
    metadata = PngInfo()
    if prompt is not None:
        metadata.add_text("prompt", json.dumps(prompt))
    if extra_pnginfo:
        for key, value in extra_pnginfo.items():
            metadata.add_text(key, json.dumps(value))
    return metadata


class ImageSaverPlus:
    """ComfyUI output node that saves images with rich filename templating.

    Supports PNG (8/16-bit), JPEG, WebP, AVIF (8/10-bit, still or animated),
    and EXR (16/32-bit float). Filename prefixes accept template variables that
    are expanded at save time:

    * ``%date:FORMAT%`` — current date/time in Java/.NET format (e.g. ``%date:yyyy_MM_dd%``)
    * ``%year%``, ``%month%``, ``%day%``, ``%hour%``, ``%minute%``, ``%second%`` — shorthand date parts
    * ``%counter%`` — sequential integer (5 digits, zero-padded) that auto-increments
      based on existing files in the output directory to prevent overwrites
    * ``%batch_num%`` — index of the current image within a batch
    * ``%width%``, ``%height%`` — image dimensions (handled by ComfyUI's folder_paths)

    An optional ``.txt`` sidecar file can be written alongside each saved image.
    """

    DESCRIPTION = (
        "Saves images as PNG, JPEG, WebP, AVIF, or EXR with bit-depth, color-space, "
        "quality/compression control, and optional text sidecar files."
    )

    def __init__(self) -> None:
        # output_dir is the ComfyUI output directory; type labels images for the UI gallery.
        self.output_dir: str = folder_paths.get_output_directory()
        self.type: str = "output"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {  # pragma: no cover
            "required": {
                "images": ("IMAGE", {"tooltip": "The images to save."}),
                "filename_prefix": (
                    "STRING",
                    {
                        "default": "ThatAIGod",
                        "tooltip": (
                            "Prefix for the filename. Supports %width%, %height%, "
                            "%date:FORMAT% (e.g. %date:yyyy_MM_dd%), %year%, %month%, "
                            "%day%, %hour%, %minute%, %second%, "
                            "%counter% (sequential number, place anywhere in the name), "
                            "and %batch_num%."
                        ),
                    },
                ),
                "file_format": (
                    list(FILE_FORMATS),
                    {
                        "default": "png",
                        "tooltip": "Output format. PNG/AVIF/EXR support embedded workflow metadata.",
                    },
                ),
                "quality": (
                    "INT",
                    {
                        "default": QUALITY_DEFAULT,
                        "min": QUALITY_MIN,
                        "max": QUALITY_MAX,
                        "step": 1,
                        "tooltip": "Quality for JPEG/WebP (1-100). Ignored for PNG, AVIF, and EXR.",
                    },
                ),
                "compress_level": (
                    "INT",
                    {
                        "default": COMPRESS_DEFAULT,
                        "min": COMPRESS_MIN,
                        "max": COMPRESS_MAX,
                        "step": 1,
                        "tooltip": "PNG compression level (0-9). 0 = no compression, 9 = max. Ignored for other formats.",
                    },
                ),
                "bit_depth": (
                    BIT_DEPTH_OPTIONS,
                    {
                        "default": "auto",
                        "advanced": True,
                        "tooltip": (
                            "auto: PNG 8-bit, AVIF 10-bit for HDR (8-bit otherwise), EXR 16-bit float. "
                            "PNG accepts 8-bit/16-bit; AVIF accepts 8-bit/10-bit YUV420; "
                            "EXR accepts 16-bit float/32-bit float."
                        ),
                    },
                ),
                "input_color_space": (
                    COLOR_SPACE_OPTIONS,
                    {
                        "default": "sRGB",
                        "advanced": True,
                        "tooltip": (
                            "Color space of the input tensor. Used by AVIF (sRGB/HDR/HDR PQ) and EXR "
                            "(sRGB/HDR/linear/linear ACEScg); ignored by PNG, JPEG, and WebP."
                        ),
                    },
                ),
                "channels": (
                    CHANNEL_OPTIONS,
                    {
                        "default": "auto",
                        "advanced": True,
                        "tooltip": (
                            "PNG only. Auto preserves input channels; grayscale converts RGB to brightness "
                            "and discards alpha; RGB drops alpha; RGBA preserves or adds opaque alpha."
                        ),
                    },
                ),
                "crf": (
                    "INT",
                    {
                        "default": CRF_DEFAULT,
                        "min": CRF_MIN,
                        "max": CRF_MAX,
                        "step": 1,
                        "advanced": True,
                        "tooltip": "AVIF quality (1-63). Lower values produce higher quality and larger files.",
                    },
                ),
                "save_mode": (
                    SAVE_MODE_OPTIONS,
                    {
                        "default": "still images",
                        "tooltip": "AVIF only. 'animated' encodes the input batch into a single looping AVIF.",
                    },
                ),
                "fps": (
                    "FLOAT",
                    {
                        "default": 6.0,
                        "min": 0.01,
                        "max": 1000.0,
                        "step": 0.01,
                        "advanced": True,
                        "tooltip": "Frame rate for animated AVIF output.",
                    },
                ),
                "loop_count": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 1000,
                        "step": 1,
                        "advanced": True,
                        "tooltip": "Loop count for animated AVIF output. 0 loops forever.",
                    },
                ),
            },
            "optional": {
                "save_text": (
                    "STRING",
                    {
                        "forceInput": True,
                        "multiline": True,
                        "tooltip": "Optional text to save as a .txt sidecar file alongside each image.",
                    },
                ),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES: tuple[()] = ()
    FUNCTION: str = "save_images"
    OUTPUT_NODE: bool = True
    CATEGORY: str = "ThatAIGod/Image Utils"

    def save_images(
        self,
        images: torch.Tensor,
        filename_prefix: str = "ThatAIGod",
        file_format: str = "png",
        quality: int = QUALITY_DEFAULT,
        compress_level: int = COMPRESS_DEFAULT,
        bit_depth: str = "auto",
        input_color_space: str = "sRGB",
        channels: str = "auto",
        crf: int = CRF_DEFAULT,
        save_mode: str = "still images",
        fps: float = 6.0,
        loop_count: int = 0,
        save_text: str | None = None,
        prompt: dict[str, Any] | None = None,
        extra_pnginfo: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Save a batch of images to the ComfyUI output directory.

        Template variables in *filename_prefix* are expanded in the following order:

        1. Shorthand date parts (``%year%``, ``%month%``, ``%day%``, ``%hour%``,
           ``%minute%``, ``%second%``) are replaced with the current local time.
        2. ``%date:FORMAT%`` patterns are replaced using :func:`_resolve_date_format`.
        3. ``%width%`` / ``%height%`` and path handling are delegated to
           ``folder_paths.get_save_image_path()``.
        4. ``%batch_num%`` is replaced per-image with the batch index.
        5. ``%counter%`` — if present — is replaced with a zero-padded 5-digit counter
           that is determined by scanning existing files (via :func:`_find_next_counter`)
           to avoid overwriting previous output.

        Args:
            images: A ``(N, H, W, C)`` float32 tensor with values in ``[0, 1]``.
            filename_prefix: Filename stem with optional template variables.
            file_format: ``"png"``, ``"jpeg"``, ``"webp"``, ``"avif"``, or ``"exr"``.
            quality: JPEG/WebP quality (1–100). Ignored for other formats.
            compress_level: PNG zlib compression level (0–9). Ignored for other formats.
            bit_depth: Shared bit-depth widget; normalized per format.
            input_color_space: Shared color-space widget; used by AVIF/EXR.
            channels: PNG channel conversion (``auto``/grayscale/RGB/RGBA).
            crf: AVIF CRF (1–63).
            save_mode: ``"still images"`` or ``"animated"`` (AVIF only).
            fps: Frame rate for animated AVIF.
            loop_count: Loop count for animated AVIF (0 = forever).
            save_text: If provided, written to a ``.txt`` file alongside each image.
            prompt: ComfyUI workflow prompt dict embedded in metadata.
            extra_pnginfo: Additional key/value pairs embedded in metadata.

        Returns:
            A dict ``{"ui": {"images": [...]}}`` consumed by ComfyUI's gallery.
        """
        now = datetime.now()
        # Expand shorthand date variables first so they are not affected by %date:FORMAT%.
        for var, fmt_code in _SHORTHAND_VARS:
            if var in filename_prefix:
                filename_prefix = filename_prefix.replace(var, now.strftime(fmt_code))

        filename_prefix = _DATE_PATTERN.sub(lambda m: _resolve_date_format(m.group(1)), filename_prefix)
        # Date formats like %date:HH:mm% expand to Windows-invalid ':' — clean
        # each segment so the batch cannot fail on filename characters.
        filename_prefix = _sanitize_filename_template(filename_prefix)

        if file_format not in FILE_FORMATS:
            logger.error("Unsupported file format %r; nothing saved", file_format)
            return {"ui": {"images": []}}

        colorspace = _resolve_color_space(file_format, input_color_space)
        resolved_bit_depth = _resolve_bit_depth(file_format, bit_depth, colorspace)
        animated = file_format == "avif" and save_mode == "animated"
        metadata: dict[str, Any] = {}
        if prompt is not None:
            metadata["prompt"] = prompt
        if extra_pnginfo:
            metadata.update(extra_pnginfo)

        full_output_folder: str
        filename: str
        counter: int
        subfolder: str
        full_output_folder, filename, counter, subfolder, filename_prefix = folder_paths.get_save_image_path(
            filename_prefix, self.output_dir, images[0].shape[1], images[0].shape[0]
        )

        if "%counter%" in filename:
            if filename.count("%counter%") > 1:
                logger.warning("Filename template contains %%counter%% more than once; only the first occurrence is replaced")
            counter = _find_next_counter(full_output_folder, filename)

        results: list[dict[str, str]] = []

        if file_format == "avif":
            batches = [(0, images)] if animated else list(enumerate(images))
            for batch_number, batch in batches:
                base_file = _build_base_file(filename, batch_number, counter)
                file = f"{base_file}.avif"
                file_path = os.path.join(full_output_folder, file)
                batch_tensor = images if animated else batch.unsqueeze(0)
                try:
                    _save_avif(
                        batch_tensor,
                        file_path,
                        resolved_bit_depth,
                        colorspace,
                        crf,
                        fps,
                        loop_count,
                        animated,
                        metadata or None,
                    )
                except Exception as e:
                    logger.error("Failed to save %s: %s", file_path, e)
                    continue
                results.append({"filename": file, "subfolder": subfolder, "type": self.type})
                _write_sidecar(full_output_folder, base_file, save_text)
                counter += 1
            return {"ui": {"images": results}}

        for batch_number, image in enumerate(images):
            base_file = _build_base_file(filename, batch_number, counter)
            file = f"{base_file}.{file_format}"
            file_path = os.path.join(full_output_folder, file)

            try:
                if file_format == "png":
                    prepared = _apply_png_channels(image, channels)
                    if resolved_bit_depth == "16-bit":
                        encoded = _encode_png16(prepared)
                        encoded = _inject_png_metadata(encoded, prompt, extra_pnginfo)
                        with open(file_path, "wb") as f:
                            f.write(encoded)
                    else:
                        _to_pil(prepared).save(
                            file_path,
                            pnginfo=_png_info(prompt, extra_pnginfo),
                            compress_level=compress_level,
                        )
                elif file_format == "exr":
                    encoded = _encode_exr(image, resolved_bit_depth, colorspace)
                    encoded = _inject_exr_metadata(encoded, prompt, extra_pnginfo, colorspace)
                    with open(file_path, "wb") as f:
                        f.write(encoded)
                elif file_format == "jpeg":
                    img = _to_pil(image)
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    img.save(file_path, quality=quality)
                else:
                    _to_pil(image).save(file_path, quality=quality)
            except Exception as e:
                # A failed save must not reach the UI gallery as a phantom entry.
                logger.error("Failed to save %s: %s", file_path, e)
                continue

            results.append({"filename": file, "subfolder": subfolder, "type": self.type})
            counter += 1
            _write_sidecar(full_output_folder, base_file, save_text)

        return {"ui": {"images": results}}


NODE_CLASS_MAPPINGS = {
    "ImageSaverPlus": ImageSaverPlus,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ImageSaverPlus": "Image Saver Plus",
}

__all__: list[str] = ["ImageSaverPlus", "NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
