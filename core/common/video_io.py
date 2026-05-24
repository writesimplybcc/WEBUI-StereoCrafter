"""Video I/O utilities for StereoCrafter.

Provides video reading and frame extraction utilities using decord
for efficient video loading.
"""

import os
import json
import shutil
import threading
import time
import logging
from typing import Optional, Tuple

import subprocess  # Needed for FFmpeg-based preview readers

import numpy as np

# Import torch BEFORE decord to avoid DLL conflicts on Windows
# See: https://github.com/dmlc/decord/issues/174
import torch
from core.common.gpu_utils import CUDA_AVAILABLE
from core.common.encoding_utils import build_encoder_args, get_encoding_config_from_dict

# Import decord after torch
from decord import VideoReader, cpu

logger = logging.getLogger(__name__)


class _NumpyBatch:
    """Minimal wrapper to match Decord's get_batch(...).asnumpy() API."""

    def __init__(self, arr: np.ndarray):
        """Initialize with a numpy array.

        Args:
            arr: Numpy array to wrap
        """
        self._arr = arr

    def asnumpy(self) -> np.ndarray:
        """Return the underlying numpy array.

        Returns:
            The wrapped numpy array
        """
        return self._arr


class VideoIO:
    """Video input/output operations for video processing."""

    @staticmethod
    def read_video_info(video_path: str) -> Tuple[int, int, int, float]:
        """Read video information without loading frames.

        Args:
            video_path: Path to the video file

        Returns:
            Tuple of (total_frames, height, width, fps)
        """
        logger.debug(f"==> Reading video info: {video_path}")
        reader = VideoReader(video_path, ctx=cpu(0))
        total_frames = len(reader)
        first_frame = reader.get_batch([0]).asnumpy()
        height, width = first_frame.shape[1:3]
        fps = float(reader.get_avg_fps())

        logger.debug(f"==> Video info: {total_frames} frames, {width}x{height}, {fps} fps")

        return total_frames, height, width, fps

    @staticmethod
    def read_frame(reader: VideoReader, index: int) -> np.ndarray:
        """Read a single frame from a video reader.

        Args:
            reader: Active VideoReader instance
            index: Frame index to read

        Returns:
            Frame as numpy array [H, W, C]
        """
        return reader.get_batch([index]).asnumpy()[0]

    @staticmethod
    def read_frames_batch(reader: VideoReader, indices: list) -> np.ndarray:
        """Read multiple frames from a video reader.

        Args:
            reader: Active VideoReader instance
            indices: List of frame indices to read

        Returns:
            Frames as numpy array [N, H, W, C]
        """
        return reader.get_batch(indices).asnumpy()


class FFmpegRGBPipeReader:
    """
    Sequential RGB frame reader backed by an FFmpeg pipe (rawvideo).
    Designed for render-time usage where get_batch() is called with
    increasing frame indices (typically contiguous batches).
    """

    def __init__(
        self,
        video_path: str,
        width: int,
        height: int,
        fps: float,
        total_frames: int,
        in_range: str = "tv",
        in_matrix: str = "bt709",
    ):
        self.video_path = video_path
        self.width = int(width)
        self.height = int(height)
        self.fps = float(fps) if fps else 0.0
        self.total_frames = int(total_frames) if total_frames is not None else -1
        self.in_range = in_range
        self.in_matrix = in_matrix
        self._proc = None
        self._next_frame = 0
        self._frame_size = self.width * self.height * 3
        self._force_fallback = False  # set True if strict scale params fail

    def __len__(self):
        return self.total_frames if self.total_frames >= 0 else 0

    def get_avg_fps(self):
        return self.fps

    def _build_cmd(self, start_frame: int = 0):
        # Start from the requested frame index. For render, this is usually 0.
        # Use -ss time seek as a best-effort fast start for non-zero start_frame.
        args = ["ffmpeg", "-v", "error", "-nostdin"]
        if start_frame and self.fps:
            start_time = start_frame / self.fps
            args += ["-ss", f"{start_time:.6f}"]
        args += ["-i", self.video_path, "-an", "-sn", "-dn"]

        vf_strict = (
            f"scale={self.width}:{self.height}:flags=bicubic:"
            f"in_range={self.in_range}:out_range={self.in_range}:"
            f"in_color_matrix={self.in_matrix}:out_color_matrix={self.in_matrix},"
            "format=rgb24"
        )
        vf_fallback = f"scale={self.width}:{self.height}:flags=bicubic,format=rgb24"
        vf = vf_fallback if self._force_fallback else vf_strict
        args += ["-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-vsync", "0", "-"]
        return args

    def _ensure_process(self, start_frame: int):
        if self._proc is not None:
            return
        cmd = self._build_cmd(start_frame=start_frame)
        self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._next_frame = start_frame

    def _restart(self, start_frame: int):
        try:
            if self._proc is not None:
                try:
                    self._proc.kill()
                except Exception:
                    pass
        finally:
            self._proc = None
        self._ensure_process(start_frame=start_frame)

    def get_batch(self, indices):
        if not indices:
            return _NumpyBatch(np.empty((0, self.height, self.width, 3), dtype=np.uint8))

        try:
            # Expect indices to be increasing most of the time; if not, restart.
            min_idx = int(min(indices))
            max_idx = int(max(indices))

            if self._proc is None:
                self._ensure_process(start_frame=min_idx)
            elif min_idx < self._next_frame:
                self._restart(start_frame=min_idx)

            # Discard frames until we reach min_idx
            while self._next_frame < min_idx:
                junk = self._proc.stdout.read(self._frame_size)
                if not junk or len(junk) < self._frame_size:
                    if not self._force_fallback:
                        self._force_fallback = True
                        self._restart(start_frame=min_idx)
                        return self.get_batch(indices)
                    raise EOFError("FFmpegRGBPipeReader reached EOF while skipping frames.")
                self._next_frame += 1

            # Read frames for requested indices
            out = np.empty((len(indices), self.height, self.width, 3), dtype=np.uint8)
            for j, idx in enumerate(indices):
                idx = int(idx)
                if idx < self._next_frame:
                    # non-monotonic request; restart and recurse (rare)
                    self._restart(start_frame=idx)
                    return self.get_batch(indices)

                # Skip gap frames if needed
                while self._next_frame < idx:
                    junk = self._proc.stdout.read(self._frame_size)
                    if not junk or len(junk) < self._frame_size:
                        if not self._force_fallback:
                            self._force_fallback = True
                            self._restart(start_frame=min_idx)
                            return self.get_batch(indices)
                        raise EOFError("FFmpegRGBPipeReader reached EOF while skipping gap frames.")
                    self._next_frame += 1

                raw = self._proc.stdout.read(self._frame_size)
                if not raw or len(raw) < self._frame_size:
                    if not self._force_fallback:
                        self._force_fallback = True
                        self._restart(start_frame=min_idx)
                        return self.get_batch(indices)
                    raise EOFError("FFmpegRGBPipeReader reached EOF while reading a frame.")
                frame = np.frombuffer(raw, dtype=np.uint8).reshape(self.height, self.width, 3)
                out[j] = frame
                self._next_frame += 1

            return _NumpyBatch(out)

        except EOFError as e:
            if not self._force_fallback:
                # Some FFmpeg builds don't support scale=in_range/in_color_matrix.
                # Retry once with a simpler filter chain.
                self._force_fallback = True
                try:
                    self._restart(start_frame=int(min(indices)) if indices else 0)
                except Exception:
                    pass
                return self.get_batch(indices)
            raise


class FFmpegRGBSingleFrameReader:
    """
    Random-access RGB reader for preview usage.
    Each get_batch([idx]) spawns a small FFmpeg decode for that frame.
    Slower than Decord, but matches FFmpeg's YUV->RGB conversion.
    """

    def __init__(
        self,
        video_path: str,
        width: int,
        height: int,
        fps: float,
        total_frames: int,
        in_range: str = "tv",
        in_matrix: str = "bt709",
    ):
        self.video_path = video_path
        self.width = int(width)
        self.height = int(height)
        self.fps = float(fps) if fps else 0.0
        self.total_frames = int(total_frames) if total_frames is not None else -1
        self.in_range = in_range
        self.in_matrix = in_matrix
        self._frame_size = self.width * self.height * 3
        self._force_fallback = False  # set True if strict scale params fail

    def __len__(self):
        return self.total_frames if self.total_frames >= 0 else 0

    def get_avg_fps(self):
        return self.fps

    def get_batch(self, indices):
        if not indices:
            return _NumpyBatch(np.empty((0, self.height, self.width, 3), dtype=np.uint8))

        def _read_exact(proc, nbytes: int) -> bytes:
            buf = b""
            while len(buf) < nbytes:
                chunk = proc.stdout.read(nbytes - len(buf)) if proc.stdout else b""
                if not chunk:
                    break
                buf += chunk
            return buf

        def _decode_one(idx: int, vf: str) -> tuple[bytes, str, int]:
            cmd = [
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-i",
                self.video_path,
                "-an",
                "-sn",
                "-dn",
                "-vf",
                vf,
                "-frames:v",
                "1",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-",
            ]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            raw = b""
            err = ""
            try:
                raw = _read_exact(proc, self._frame_size)
                if proc.stderr:
                    try:
                        err = proc.stderr.read().decode("utf-8", errors="ignore")
                    except Exception:
                        err = ""
            finally:
                try:
                    if proc.stdout:
                        proc.stdout.close()
                except Exception:
                    pass
                try:
                    if proc.stderr:
                        proc.stderr.close()
                except Exception:
                    pass
                try:
                    proc.wait()
                except Exception:
                    pass
            return raw, err, int(proc.returncode or 0)

        frames = np.empty((len(indices), self.height, self.width, 3), dtype=np.uint8)
        for j, idx in enumerate(indices):
            idx = int(idx)

            # Try the strict matrix/range path first; if unsupported by the user's ffmpeg build,
            # fall back to a plain scale->rgb24 path (still FFmpeg-based conversion, just less explicit).
            vf_strict = (
                f"select='eq(n\\,{idx})',"
                f"scale={self.width}:{self.height}:flags=bicubic:"
                f"in_range={self.in_range}:out_range={self.in_range}:"
                f"in_color_matrix={self.in_matrix}:out_color_matrix={self.in_matrix},"
                "format=rgb24"
            )
            vf_fallback = f"select='eq(n\\,{idx})',scale={self.width}:{self.height}:flags=bicubic,format=rgb24"

            raw, err, rc = _decode_one(idx, vf_strict)
            if not raw or len(raw) < self._frame_size:
                raw2, err2, rc2 = _decode_one(idx, vf_fallback)
                if raw2 and len(raw2) >= self._frame_size:
                    raw, err, rc = raw2, err2, rc2
                else:
                    msg = (err2 or err or "").strip()
                    if msg:
                        raise EOFError(f"FFmpegRGBSingleFrameReader failed to decode frame {idx}: {msg}")
                    raise EOFError(f"FFmpegRGBSingleFrameReader failed to decode frame {idx}.")

            frame = np.frombuffer(raw, dtype=np.uint8).reshape(self.height, self.width, 3)
            frames[j] = frame

        return _NumpyBatch(frames)


def read_video_frames(
    video_path: str,
    process_length: int,
    set_pre_res: bool,
    pre_res_width: int,
    pre_res_height: int,
    strict_ffmpeg_decode: bool = False,
    dataset: str = "open",
) -> Tuple[VideoReader, float, int, int, int, int, Optional[dict], int]:
    """Initialize a VideoReader for chunked reading.

    Args:
        video_path: Path to the video file
        process_length: Number of frames to process (-1 for all)
        set_pre_res: Whether to set custom resolution
        pre_res_width: Target width if set_pre_res is True
        pre_res_height: Target height if set_pre_res is True
        dataset: Dataset type (only 'open' supported)

    Returns:
        Tuple of (video_reader, fps, original_height, original_width,
                  actual_processed_height, actual_processed_width,
                  video_stream_info, total_frames_to_process)

    Raises:
        NotImplementedError: If dataset is not 'open'
    """
    # Handle process_length that might be passed as string
    try:
        process_length = int(process_length) if process_length not in (None, "", "N/A") else -1
    except (ValueError, TypeError):
        process_length = -1

    logger.debug(f"read_video_frames: process_length = {process_length} (type: {type(process_length)})")
    if dataset == "open":
        logger.info(f"==> Initializing VideoReader for: {video_path}")
        vid_info_only = VideoReader(video_path, ctx=cpu(0))  # Use separate reader for info
        original_height, original_width = vid_info_only.get_batch([0]).shape[1:3]
        try:
            total_frames_original = int(len(vid_info_only)) if len(vid_info_only) not in (None, "", "N/A") else 0
        except (ValueError, TypeError):
            total_frames_original = 0
        logger.info(
            f"==> Original video shape: {total_frames_original} frames, {original_height}x{original_width} per frame"
        )

        height_for_reader = original_height
        width_for_reader = original_width

        if set_pre_res and pre_res_width > 0 and pre_res_height > 0:
            height_for_reader = pre_res_height
            width_for_reader = pre_res_width
            logger.debug(f"==> Pre-processing resolution set to: {width_for_reader}x{height_for_reader}")
        else:
            logger.debug(f"==> Using original video resolution for reading: {width_for_reader}x{height_for_reader}")

    else:
        raise NotImplementedError(f"Dataset '{dataset}' not supported.")

    # decord automatically resizes if width/height are passed to VideoReader
    video_reader = VideoReader(video_path, ctx=cpu(0), width=width_for_reader, height=height_for_reader)

    # Verify the actual shape after Decord processing, using the first frame
    first_frame_shape = video_reader.get_batch([0]).shape
    actual_processed_height, actual_processed_width = first_frame_shape[1:3]

    fps = float(video_reader.get_avg_fps())  # Use actual FPS from the reader

    # --- Use the single canonical frame count (Phase 1 unification) ---
    total_frames_available = get_canonical_frame_count(video_path)
    if total_frames_available > 0:
        logger.debug(f"[VIDEO_READER] Canonical count = {total_frames_available} for {os.path.basename(video_path)}")
    else:
        # Last-resort direct len (should almost never happen now)
        try:
            raw_len = len(video_reader)
            total_frames_available = raw_len if isinstance(raw_len, int) and raw_len > 0 else 0
        except Exception:
            total_frames_available = 0

    # Always fetch stream info for color metadata / strict FFmpeg path
    video_stream_info = get_video_stream_info(video_path)

    total_frames_to_process = total_frames_available
    if total_frames_available > 0 and process_length != -1 and process_length < total_frames_available:
        total_frames_to_process = process_length

    logger.debug(
        f"==> VideoReader initialized. Final processing dimensions: "
        f"{actual_processed_width}x{actual_processed_height}. "
        f"Total frames for processing: {total_frames_to_process} (robust count preferred)"
    )

    # If strict FFmpeg decode is requested, swap in an FFmpeg-backed reader for frame fetch.
    # This keeps decode/colorspace conversion consistent across preview + renders for problem clips.
    if strict_ffmpeg_decode:
        try:
            in_range = "tv"
            in_matrix = "bt709"
            try:
                cr = str((video_stream_info or {}).get("color_range") or "").lower()
                cs = str((video_stream_info or {}).get("color_space") or "").lower()
                if "full" in cr or cr == "pc":
                    in_range = "pc"
                if "2020" in cs:
                    in_matrix = "bt2020"
                elif "601" in cs:
                    in_matrix = "bt601"
            except Exception:
                pass

            video_reader = FFmpegRGBPipeReader(
                video_path=video_path,
                width=width_for_reader,
                height=height_for_reader,
                fps=float(fps),
                total_frames=total_frames_available,
                in_range=in_range,
                in_matrix=in_matrix,
            )
        except Exception as e:
            logger.warning(
                f"Strict FFmpeg decode requested, but FFmpeg reader init failed; falling back to Decord. ({e})"
            )

    return (
        video_reader,
        fps,
        original_height,
        original_width,
        actual_processed_height,
        actual_processed_width,
        video_stream_info,
        total_frames_to_process,
    )


_FFPROBE_AVAIL: Optional[bool] = None
_INFO_CACHE: dict = {}


def get_video_stream_info(video_path: str) -> Optional[dict]:
    """Get comprehensive video stream information using ffprobe (robust version).

    Includes nb_frames with -count_frames fallback and duration-based guessing.
    This is the canonical implementation used across Splatting, Inpainting, Merging,
    and core render paths to eliminate off-by-one frame count errors.

    Args:
        video_path: Path to the video file

    Returns:
        Dictionary containing stream info (including nb_frames when available)
        or None if unavailable
    """
    global _FFPROBE_AVAIL, _INFO_CACHE
    if not video_path:
        return None
    if video_path in _INFO_CACHE:
        return _INFO_CACHE[video_path]

    if _FFPROBE_AVAIL is None:
        try:
            subprocess.run(["ffprobe", "-version"], check=True, capture_output=True)
            _FFPROBE_AVAIL = True
        except Exception:
            _FFPROBE_AVAIL = False
    if not _FFPROBE_AVAIL:
        return None

    try:
        # Robust query: explicitly request nb_frames + duration for reliable counting
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,profile,pix_fmt,color_range,color_primaries,"
                             "transfer_characteristics,color_space,r_frame_rate,width,height,"
                             "nb_frames,duration,side_data_list",
            "-show_entries", "side_data=mastering_display_metadata,max_content_light_level",
            "-of", "json",
            video_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8", timeout=60)
        raw_stdout = result.stdout
        data = json.loads(raw_stdout)

        stream_info: dict = {}
        if "streams" in data and len(data["streams"]) > 0:
            s = data["streams"][0]

            # Core fields
            for key in ["codec_name", "profile", "pix_fmt", "color_range", "color_primaries",
                        "transfer_characteristics", "color_space", "r_frame_rate",
                        "width", "height", "nb_frames", "duration", "nb_read_frames"]:
                if key in s and s[key] not in (None, "", "N/A", "und", "unknown"):
                    stream_info[key] = s[key]

            # Side data (HDR etc.)
            if s.get("side_data_list"):
                for sd in s["side_data_list"]:
                    if sd.get("side_data_type") == "Mastering display metadata":
                        stream_info["mastering_display_metadata"] = sd.get("mastering_display_metadata")
                    if sd.get("side_data_type") == "Content light level metadata":
                        stream_info["max_content_light_level"] = sd.get("max_content_light_level")

        # If nb_frames missing or zero, force accurate count with -count_frames
        nb_val = stream_info.get("nb_frames")
        if not nb_val or str(nb_val).strip() in ("0", "0.0"):
            logger.info(f"[VIDEO_READER] nb_frames missing/zero for {os.path.basename(video_path)}; running ffprobe -count_frames")
            cmd_count = [
                "ffprobe",
                "-count_frames",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=nb_read_frames",
                "-of", "json",
                video_path,
            ]
            try:
                res_count = subprocess.run(cmd_count, capture_output=True, text=True, check=True,
                                           encoding="utf-8", timeout=120)
                data_count = json.loads(res_count.stdout)
                if "streams" in data_count and len(data_count["streams"]) > 0:
                    s_count = data_count["streams"][0]
                    if "nb_read_frames" in s_count and s_count["nb_read_frames"]:
                        stream_info["nb_frames"] = s_count["nb_read_frames"]
                        stream_info["nb_read_frames"] = s_count["nb_read_frames"]
                        logger.info(f"[VIDEO_READER] -count_frames gave nb_frames={stream_info['nb_frames']} for {os.path.basename(video_path)}")
            except Exception as e:
                logger.warning(f"[VIDEO_READER] -count_frames failed for {video_path}: {e}")

        # Final fallback: derive from duration * r_frame_rate
        if not stream_info.get("nb_frames") or str(stream_info.get("nb_frames", "")).strip() in ("0", "0.0"):
            dur = stream_info.get("duration")
            rate = stream_info.get("r_frame_rate")
            if dur and rate:
                try:
                    duration_f = float(dur)
                    if "/" in rate:
                        num, den = rate.split("/")
                        fps = float(num) / float(den) if float(den) != 0 else 0.0
                    else:
                        fps = float(rate)
                    if duration_f > 0 and fps > 0:
                        guessed = str(round(duration_f * fps))
                        stream_info["nb_frames"] = guessed
                        logger.debug(f"[VIDEO_READER] Guessed nb_frames={guessed} from duration*fps for {os.path.basename(video_path)}")
                except Exception:
                    pass

        # Filter junk values
        cleaned = {}
        for k, v in stream_info.items():
            if v is not None and str(v).strip() not in ("N/A", "und", "unknown", "0", "0.0"):
                cleaned[k] = v

        if cleaned:
            _INFO_CACHE[video_path] = cleaned
            return cleaned

    except Exception as e:
        logger.debug(f"[VIDEO_READER] get_video_stream_info failed for {video_path}: {e}")

    return None


def get_canonical_frame_count(video_path: str, prefer_count_frames: bool = True, timeout: int = 120) -> int:
    """Return the single most reliable frame count for any video or depth map.

    This is the authoritative source of truth for the entire pipeline
    (DepthCrafter → Splatting → Inpainting → Merging) to eliminate
    off-by-one and "last frame dropped" problems.

    Strategy:
    1. Use the robust get_video_stream_info (which already performs
       nb_frames + -count_frames fallback + duration guess).
    2. If that yields a positive count, return it.
    3. Otherwise fall back to opening with Decord and using len().

    The returned number should be used for:
    - Initial planning of total_frames_to_process
    - Enforcing exact frame count in all processing loops
    - Post-write verification

    Args:
        video_path: Path to the video/depth file
        prefer_count_frames: (kept for future; current robust logic already prefers it)
        timeout: Seconds for expensive -count_frames operation

    Returns:
        Positive integer frame count, or 0 on failure
    """
    if not video_path or not os.path.exists(video_path):
        return 0

    # 1. Try robust metadata first (the main improvement)
    try:
        info = get_video_stream_info(video_path)
        if info:
            for key in ("nb_frames", "nb_read_frames"):
                val = info.get(key)
                if val:
                    try:
                        n = int(float(val))
                        if n > 0:
                            logger.debug(
                                f"[CANONICAL_COUNT] Using {key}={n} from robust ffprobe "
                                f"for {os.path.basename(video_path)}"
                            )
                            return n
                    except (ValueError, TypeError):
                        pass
    except Exception as e:
        logger.debug(f"[CANONICAL_COUNT] Robust info failed for {video_path}: {e}")

    # 2. Decord fallback (reliable for actual decodable frames)
    try:
        vr = VideoReader(video_path, ctx=cpu(0))
        n = len(vr)
        del vr
        if n > 0:
            logger.debug(
                f"[CANONICAL_COUNT] Decord len() fallback gave {n} for "
                f"{os.path.basename(video_path)}"
            )
            return n
    except Exception as e:
        logger.warning(f"[CANONICAL_COUNT] Decord fallback failed for {video_path}: {e}")

    logger.error(f"[CANONICAL_COUNT] Could not determine any frame count for {video_path}")
    return 0


def read_video_frames_decord(
    video_path: str,
    process_length: int = -1,
    target_fps: float = -1.0,
    set_res_width: Optional[int] = None,
    set_res_height: Optional[int] = None,
    decord_ctx=cpu(0),
) -> Tuple[np.ndarray, float, int, int, int, int, Optional[dict]]:
    """Read video frames using decord with optional resizing and fps conversion.

    Args:
        video_path: Path to the video file
        process_length: Number of frames to process (-1 for all)
        target_fps: Target fps (-1 for original)
        set_res_width: Target width (None for original)
        set_res_height: Target height (None for original)
        decord_ctx: Decord context for reading

    Returns:
        Tuple of (frames as float32 numpy array [T,H,W,C] normalized to 0-1,
                  fps, original_height, original_width, output_height, output_width,
                  stream_info)
    """
    info = get_video_stream_info(video_path)
    temp_reader = VideoReader(video_path, ctx=cpu(0))
    oh, ow = temp_reader.get_batch([0]).shape[1:3]
    del temp_reader
    dw, dh = (set_res_width, set_res_height) if set_res_width and set_res_height else (ow, oh)
    vid = VideoReader(video_path, ctx=decord_ctx, width=dw, height=dh)
    total = len(vid)
    # Prefer robust count now that get_video_stream_info is authoritative
    try:
        robust = get_video_stream_info(video_path)
        for k in ("nb_frames", "nb_read_frames"):
            if robust and robust.get(k):
                n = int(float(robust[k]))
                if n > 0:
                    total = n
                    break
    except Exception:
        pass
    fps = target_fps if target_fps > 0 else vid.get_avg_fps()
    stride = max(round(vid.get_avg_fps() / fps), 1)
    idxs = list(range(0, total, stride))
    if process_length != -1:
        idxs = idxs[:process_length]
    frames = vid.get_batch(idxs).asnumpy().astype("float32") / 255.0
    return frames, fps, oh, ow, frames.shape[1], frames.shape[2], info


def encode_frames_to_mp4(
    temp_png_dir: str,
    final_output_mp4_path: str,
    fps: float,
    total_output_frames: int,
    video_stream_info: Optional[dict],
    stop_event: Optional[threading.Event] = None,
    sidecar_json_data: Optional[dict] = None,
    user_output_crf: Optional[int] = None,
    output_sidecar_ext: str = ".json",
) -> bool:
    """Encode a directory of PNG frames to an MP4 video using FFmpeg.

    Args:
        temp_png_dir: Directory containing PNG frames named %05d.png
        final_output_mp4_path: Path to the output MP4 file
        fps: Output video frame rate
        total_output_frames: Total number of frames to encode
        video_stream_info: Source video stream info for matching color space
        stop_event: Optional threading event to cancel encoding
        sidecar_json_data: Optional data to save to a JSON sidecar file
        user_output_crf: Optional override for CRF (quality) setting
        output_sidecar_ext: Extension for the sidecar file

    Returns:
        True if encoding succeeded, False otherwise
    """
    if total_output_frames == 0:
        logger.warning(f"No frames to encode for {os.path.basename(final_output_mp4_path)}. Skipping.")
        if os.path.exists(temp_png_dir):
            shutil.rmtree(temp_png_dir)
        return False

    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-framerate",
        str(fps),
        "-i",
        os.path.join(temp_png_dir, "%05d.png"),
    ]

    output_codec, output_pix_fmt, default_cpu_crf, output_profile = "libx264", "yuv420p", "23", "main"

    enc_config = get_encoding_config_from_dict({})  # Use empty dict as default
    crf = user_output_crf if user_output_crf is not None else enc_config.get("crf", 23)

    is_hdr = (
        video_stream_info
        and video_stream_info.get("color_primaries") == "bt2020"
        and video_stream_info.get("transfer_characteristics") in ("smpte2084", "arib-std-b67")
    )
    orig_pix = video_stream_info.get("pix_fmt", "") if video_stream_info else ""
    is_high_bit = "10" in orig_pix or "12" in orig_pix or "16" in orig_pix
    output_color_mode = str(video_stream_info.get("color_tags_mode", "")).lower() if video_stream_info else ""

    force_10bit = is_hdr or output_color_mode in ("bt.2020 pq", "bt.2020 hlg", "bt.2020")

    enc_args = build_encoder_args(
        encoder=enc_config.get("encoder", "Auto"),
        quality=enc_config.get("quality", "Medium"),
        tune=enc_config.get("tune", "None"),
        crf=crf,
        force_10bit=force_10bit,
        nvenc_options={
            "lookahead_enabled": enc_config.get("nvenc_lookahead_enabled", False),
            "lookahead": enc_config.get("nvenc_lookahead", 16),
            "spatial_aq": enc_config.get("nvenc_spatial_aq", False),
            "temporal_aq": enc_config.get("nvenc_temporal_aq", False),
            "aq_strength": enc_config.get("nvenc_aq_strength", 8),
        },
    )

    output_codec = enc_args["codec"]
    output_pix_fmt = enc_args["pix_fmt"]
    output_profile = "main10" if "10" in output_pix_fmt else "main"

    ffmpeg_cmd.extend(["-c:v", output_codec])
    ffmpeg_cmd.extend(enc_args["extra_args"])
    ffmpeg_cmd.extend(["-pix_fmt", output_pix_fmt])
    if output_profile:
        ffmpeg_cmd.extend(["-profile:v", output_profile])

    if video_stream_info:
        for k, f in [
            ("color_primaries", "-color_primaries"),
            ("transfer_characteristics", "-color_trc"),
            ("color_space", "-colorspace"),
            ("color_range", "-color_range"),
        ]:
            if video_stream_info.get(k):
                ffmpeg_cmd.extend([f, video_stream_info[k]])

    if os.path.splitext(final_output_mp4_path)[1].lower() in (".mp4", ".mov", ".m4v"):
        ffmpeg_cmd.extend(["-movflags", "+write_colr"])

    ffmpeg_cmd.append(final_output_mp4_path)

    try:
        process = subprocess.Popen(
            ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8"
        )
        while process.poll() is None:
            if stop_event and stop_event.is_set():
                process.terminate()
                return False
            time.sleep(0.1)
        if process.returncode != 0:
            return False
    except Exception as e:
        logger.error(f"Encoding failed: {e}")
        return False
    finally:
        if os.path.exists(temp_png_dir):
            shutil.rmtree(temp_png_dir)

    if sidecar_json_data:
        path = f"{os.path.splitext(final_output_mp4_path)[0]}{output_sidecar_ext}"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sidecar_json_data, f, indent=4)
    return True


def start_ffmpeg_pipe_process(
    content_width: int,
    content_height: int,
    final_output_mp4_path: str,
    fps: float,
    video_stream_info: Optional[dict] = None,
    output_format_str: str = "",
    user_output_crf: Optional[int] = None,
    pad_to_16_9: bool = False,
    debug_label: Optional[str] = None,
    encoding_options: Optional[dict] = None,
) -> Optional[subprocess.Popen]:
    """Start an FFmpeg process that reads raw video from a pipe.

    Args:
        content_width: Width of input frames
        content_height: Height of input frames
        final_output_mp4_path: Output path for the video
        fps: Frame rate
        video_stream_info: Source video stream info (currently unused in this version)
        output_format_str: Optional format string
        user_output_crf: Optional CRF override
        pad_to_16_9: Whether to pad to 16:9 (currently unused)
        debug_label: Optional label for logging
        encoding_options: Optional extra encoding options

    Returns:
        The subprocess.Popen instance
    """
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "verbose",
        "-y",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-s",
        f"{content_width}x{content_height}",
        "-pix_fmt",
        "bgr48le",
        "-r",
        str(fps),
        "-i",
        "-",
    ]
    enc_config = get_encoding_config_from_dict(encoding_options or {})
    crf = user_output_crf if user_output_crf is not None else enc_config.get("crf", 23)

    color_tags_mode = str(video_stream_info.get("color_tags_mode", "")).lower() if video_stream_info else ""
    force_10bit = color_tags_mode in ("bt.2020 pq", "bt.2020 hlg", "bt.2020")

    enc_args = build_encoder_args(
        encoder=enc_config.get("encoder", "Auto"),
        quality=enc_config.get("quality", "Medium"),
        tune=enc_config.get("tune", "None"),
        crf=crf,
        force_10bit=force_10bit,
        nvenc_options={
            "lookahead_enabled": enc_config.get("nvenc_lookahead_enabled", False),
            "lookahead": enc_config.get("nvenc_lookahead", 16),
            "spatial_aq": enc_config.get("nvenc_spatial_aq", False),
            "temporal_aq": enc_config.get("nvenc_temporal_aq", False),
            "aq_strength": enc_config.get("nvenc_aq_strength", 8),
        },
    )

    cmd.extend(["-c:v", enc_args["codec"]])
    cmd.extend(enc_args["extra_args"])
    cmd.extend(["-pix_fmt", enc_args["pix_fmt"]])

    if force_10bit and video_stream_info:
        for k, f in [
            ("color_primaries", "-color_primaries"),
            ("transfer_characteristics", "-color_trc"),
            ("color_space", "-colorspace"),
            ("color_range", "-color_range"),
        ]:
            if video_stream_info.get(k):
                cmd.extend([f, video_stream_info[k]])

    cmd.extend(["-movflags", "+write_colr", final_output_mp4_path])
    logger.info(f"Starting FFmpeg pipe: {' '.join(cmd)}")
    return subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def start_ffmpeg_pipe_process_dnxhr(
    content_width: int, content_height: int, final_output_mov_path: str, fps: float, dnxhr_profile: str = "HQX"
) -> Optional[subprocess.Popen]:
    """Start an FFmpeg process for high-quality DNxHR output via pipe.

    Args:
        content_width: Width of input frames
        content_height: Height of input frames
        final_output_mov_path: Output path for the MOV file
        fps: Frame rate
        dnxhr_profile: DNxHR profile (SQ, HQ, HQX, 444)

    Returns:
        The subprocess.Popen instance
    """
    prof = {"SQ": "dnxhr_sq", "HQ": "dnxhr_hq", "HQX": "dnxhr_hqx", "444": "dnxhr_444"}.get(
        dnxhr_profile.strip().upper()[:3], "dnxhr_hqx"
    )
    pix = "yuv444p10le" if prof == "dnxhr_444" else "yuv422p10le"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "verbose",
        "-y",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-s",
        f"{content_width}x{content_height}",
        "-pix_fmt",
        "bgr48le",
        "-r",
        str(fps),
        "-i",
        "-",
        "-c:v",
        "dnxhd",
        "-profile:v",
        prof,
        "-pix_fmt",
        pix,
        "-an",
        final_output_mov_path,
    ]
    logger.info(f"Starting DNxHR pipe: {' '.join(cmd)}")
    return subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
