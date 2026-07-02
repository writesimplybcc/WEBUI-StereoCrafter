import os
import gc
import numpy as np
import torch
import time
import warnings
warnings.filterwarnings("ignore", category=FutureWarning, module="diffusers.models.transformers.transformer_2d")
import logging # Import standard logging

# Use WARNING or ERROR to silence model loading messages.
logging.getLogger("diffusers").setLevel(logging.WARNING) 
logging.getLogger("transformers").setLevel(logging.WARNING) 
logging.getLogger("huggingface_hub").setLevel(logging.WARNING)

# Configure a logger for this module
_logger = logging.getLogger(__name__)

from diffusers.training_utils import set_seed
from depthcrafter.depth_crafter_ppl import DepthCrafterPipeline
from depthcrafter.unet import DiffusersUNetSpatioTemporalConditionModelDepthCrafter

# --- MODIFIED IMPORTS from depthcrafter.utils ---
from depthcrafter.utils import (
    save_video, read_video_frames,
    save_depth_visual_as_mp4_util,
    save_depth_visual_as_png_sequence_util,
    save_depth_visual_as_exr_sequence_util,
    save_depth_visual_as_single_exr_util,
    read_image_sequence_as_frames,
    create_frames_from_single_image,
    format_duration,
    get_segment_output_folder_name,
    get_segment_npz_output_filename,
    get_full_video_output_filename,
    get_sidecar_json_filename,
    save_json_file
)

# Import VRAM utility for dynamic resolution cap
from dependency.stereocrafter_util import get_current_vram_usage
# --- END MODIFIED IMPORTS ---

try:
    import OpenEXR
    import Imath
    OPENEXR_AVAILABLE_LOGIC = True
except ImportError:
    OPENEXR_AVAILABLE_LOGIC = False
    _logger.warning("OpenEXR/Imath libraries not found. EXR features will be limited/unavailable. Context: depth_crafter_logic.py")


warnings.filterwarnings("ignore", category=FutureWarning, module="diffusers.models.transformers.transformer_2d")

from typing import Optional, Tuple, List, Dict, Union

# --- Global Configuration Flags ---


_ENABLE_XFORMERS_ATTENTION = True # Enabled by default; GUI can override via disable_xformers checkbox. Disabled for low-VRAM Docker stability.

class DepthCrafterDemo:
    def __init__(
        self,
        unet_path: str,
        pre_train_path: str,
        cpu_offload: Union[str, None] = "model",
        use_cudnn_benchmark: bool = False,
        local_files_only: bool = False,
        disable_xformers=False,
        token: Optional[str] = None
    ):
        torch.backends.cudnn.benchmark = use_cudnn_benchmark
        try:
            unet = DiffusersUNetSpatioTemporalConditionModelDepthCrafter.from_pretrained(
                unet_path,
                low_cpu_mem_usage=True,
                torch_dtype=torch.float16,
                local_files_only=local_files_only,
                token=token
            )
            self.pipe = DepthCrafterPipeline.from_pretrained(
                pre_train_path,
                unet=unet,
                torch_dtype=torch.float16,
                local_files_only=local_files_only,
                token=token
            )
            cpu_offload_lower = cpu_offload
            if cpu_offload_lower == "sequential":
                self.pipe.enable_sequential_cpu_offload()
                _logger.info("CPU Offload set to 'sequential'.")
            elif cpu_offload_lower == "model":
                self.pipe.enable_model_cpu_offload()
                _logger.info("CPU Offload set to 'model'.")
            else:
                cpu_offload_lower = 'none'
                self.pipe.to("cuda")
                _logger.info(f"CPU Offload set to '{cpu_offload_lower}'. Model loaded entirely on CUDA.")
            
            try:
                self.pipe.disable_attention_slicing()
                _logger.info("Attention slicing DISABLED.")
            except Exception as e:
                _logger.warning(f"Could not disable attention slicing: {e}")
            should_enable_xformers = _ENABLE_XFORMERS_ATTENTION and not disable_xformers
            if should_enable_xformers:
                try:
                    from diffusers.utils.logging import set_verbosity_info
                    set_verbosity_info()
                    self.pipe.enable_xformers_memory_efficient_attention()
                    _logger.info("xFormers memory-efficient attention ENABLED.")
                except ImportError:
                    _logger.warning("xFormers library not found, cannot enable.")
                except Exception as e:
                    _logger.warning(f"Failed to enable xFormers: {e}. Falling back to standard attention.")
            else:
                if disable_xformers:
                    try:
                        self.pipe.disable_xformers_memory_efficient_attention()
                        _logger.info("xFormers memory-efficient attention DISABLED by GUI setting (VRAM Save Mode).")
                    except Exception:
                        _logger.debug("Attempt to disable xformers failed, likely already disabled or not present.")
                else:
                    _logger.info("xFormers memory-efficient attention disabled by global setting.")
            
            try:
                if cpu_offload_lower in ("model", "sequential"):
                    if hasattr(self.pipe.unet, 'disable_gradient_checkpointing'):
                        self.pipe.unet.disable_gradient_checkpointing()
                        _logger.info("Gradient checkpointing DISABLED for CPU offload stability.")
                elif cpu_offload_lower == 'none':
                    if hasattr(self.pipe.unet, 'disable_gradient_checkpointing'):
                        self.pipe.unet.disable_gradient_checkpointing()
                        _logger.info("Gradient checkpointing DISABLED (full CUDA mode, speed priority).")
                else:
                    self.pipe.unet.enable_gradient_checkpointing()
                    _logger.info("Gradient checkpointing enabled on UNet for memory efficiency.")
            except Exception as e:
                _logger.warning(f"Could not configure checkpointing: {e}")
            
            try:
                from dependency.stereocrafter_util import get_current_vram_usage
                vram_info = get_current_vram_usage()
                total_vram = vram_info.get('total', 8)
                if total_vram < 24:
                    try:
                        if hasattr(self.pipe, 'enable_vae_slicing'):
                            self.pipe.enable_vae_slicing()
                            _logger.info("VAE slicing enabled for memory efficiency.")
                    except Exception as e:
                        _logger.warning(f"VAE slicing not supported: {e}")
                else:
                    _logger.info("VAE slicing/tiling disabled (sufficient VRAM).")
            except Exception as e:
                _logger.warning(f"Could not determine VRAM for VAE optimizations: {e}")
        except Exception as e:
            _logger.critical(f"CRITICAL: Failed to initialize DepthCrafterPipeline: {e}", exc_info=True)
            raise # Re-raise after logging

    def _setup_paths(self, base_output_folder: str, original_video_basename: str,
                     segment_job_info: Optional[dict]) -> Tuple[str, str, str]:
        actual_save_folder_for_output = base_output_folder
        output_filename_for_meta = ""

        if segment_job_info:
            segment_subfolder_name = get_segment_output_folder_name(original_video_basename)
            actual_save_folder_for_output = os.path.join(base_output_folder, segment_subfolder_name)
            output_filename_for_meta = get_segment_npz_output_filename(
                original_video_basename,
                segment_job_info['segment_id'],
                segment_job_info['total_segments']
            )
        else:
            output_filename_for_meta = get_full_video_output_filename(original_video_basename)

        full_save_path = os.path.join(actual_save_folder_for_output, output_filename_for_meta)
        os.makedirs(actual_save_folder_for_output, exist_ok=True)
        return actual_save_folder_for_output, output_filename_for_meta, full_save_path

    def _initialize_job_metadata(self, guidance_scale: float, num_denoising_steps: int,
                                    user_target_height: int, user_target_width: int, seed_val: int,
                                    target_fps_for_read: float, segment_job_info: Optional[dict],
                                    output_filename_for_meta: str, pipe_call_window_size: int,
                                    pipe_call_overlap: int,
                                    original_video_basename: str) -> dict:
        job_specific_metadata = {
            "original_video_basename": original_video_basename, 
            "guidance_scale": float(guidance_scale),
            "inference_steps": int(num_denoising_steps),
            "target_height_during_process": int(user_target_height),
            "target_width_during_process": int(user_target_width),
            "seed": int(seed_val),
            "target_fps_setting": float(target_fps_for_read),
            "status": "pending",
            "_individual_metadata_path": None
        }

        if segment_job_info:
            job_specific_metadata.update({
                "segment_id": int(segment_job_info["segment_id"]),
                "source_start_frame_raw_index": int(segment_job_info["start_frame_raw_index"]),
                "source_num_frames_raw_for_segment": int(segment_job_info["num_frames_to_load_raw"]),
                "output_segment_filename": output_filename_for_meta,
                "output_segment_format": "npz",
                "segment_definition_window_setting": int(pipe_call_window_size),
                "segment_definition_overlap_setting": int(pipe_call_overlap)
            })
        else:
            job_specific_metadata.update({
                "output_video_filename": output_filename_for_meta,
                "pipeline_window_size_used_for_full_video_pass": int(pipe_call_window_size),
                "pipeline_overlap_used_for_full_video_pass": int(pipe_call_overlap)
            })
        return job_specific_metadata

    def _load_frames(self,
                     video_path_or_job_info: Union[str, dict],
                     frames_array_if_provided: Optional[np.ndarray],
                     process_length_for_read: int,
                     user_target_height: int,
                     user_target_width: int,
                     segment_job_info: Optional[dict],
                     job_specific_metadata: dict
                      ) -> Tuple[Optional[np.ndarray], float, int, int, float]:
        # Automatically reduce resolution for very high res to prevent OOM during loading
        # Dynamic max_res based on available VRAM
        try:
            vram_info = get_current_vram_usage()
            total_vram = vram_info.get('total', 8)  # Fixed: was 'total_gb'
            free_vram = vram_info.get('free', total_vram)  # Fixed: was 'free_gb'
            gpu_name = vram_info.get('gpu_name', '').lower()
            free_percentage = free_vram / total_vram if total_vram > 0 else 0
            
            # For RTX 3060 12GB and similar: even with model loaded, we should handle 1024px
            if total_vram >= 12 and free_vram >= 3:
                effective_vram = total_vram  # Trust total VRAM for 12GB+ cards with reasonable free space
            else:
                effective_vram = total_vram if free_percentage > 0.8 else free_vram * 1.5  # Increased from 1.2 for safety
            # Set max_res based on effective VRAM tiers
            if effective_vram < 7.5:
                max_res = 512
            elif effective_vram < 11.5:
                max_res = 768
            elif effective_vram < 23.5:
                max_res = 1024
            elif effective_vram < 31.5:
                max_res = 1920
            elif effective_vram < 47.5:
                max_res = 1920
            elif effective_vram < 79.5:
                max_res = 2048
            else:
                max_res = 4096
        except Exception as e:
            _logger.warning(f"Could not determine VRAM for dynamic resolution cap, using default 1024: {e}")
            effective_vram = 8.0
            max_res = 1024
        if user_target_height > max_res:
            _logger.warning(f"Target height {user_target_height} > {max_res}, reducing to {max_res} to prevent OOM")
            user_target_height = max_res
        if user_target_width > max_res:
            _logger.warning(f"Target width {user_target_width} > {max_res}, reducing to {max_res} to prevent OOM")
            user_target_width = max_res

        actual_frames_to_process = None
        actual_fps_for_save = 30.0
        original_h_loaded, original_w_loaded = None, None

        if frames_array_if_provided is not None:
            actual_frames_to_process = frames_array_if_provided
            if segment_job_info and "original_video_fps" in segment_job_info:
                 actual_fps_for_save = segment_job_info["original_video_fps"]
            elif "target_fps_setting" in job_specific_metadata:
                 actual_fps_for_save = job_specific_metadata["target_fps_setting"] if job_specific_metadata["target_fps_setting"] != -1 else 24.0
            else:
                 actual_fps_for_save = 24.0
            _logger.debug(f"Loaded {len(actual_frames_to_process)} frames from numpy array. Using FPS: {actual_fps_for_save:.2f}")
            if actual_frames_to_process.ndim > 0 and len(actual_frames_to_process) > 0:
                 original_h_loaded, original_w_loaded = actual_frames_to_process.shape[1:3]

        elif isinstance(video_path_or_job_info, str):
            video_path_for_read = video_path_or_job_info
            start_frame_idx = 0
            num_frames_to_load_for_seg = -1
            
            if segment_job_info:
                start_frame_idx = segment_job_info["start_frame_raw_index"]
                num_frames_to_load_for_seg = segment_job_info["num_frames_to_load_raw"]
                target_fps_for_video_read = segment_job_info.get("gui_fps_setting_at_definition", -1)
            else:
                target_fps_for_video_read = job_specific_metadata.get("target_fps_setting", -1)

            # --- ADDED: Check for cached ffprobe info and pass it to read_video_frames ---
            cached_ffprobe_info = None
            if segment_job_info and "video_stream_ffprobe_info" in segment_job_info:
                cached_ffprobe_info = segment_job_info["video_stream_ffprobe_info"]
                _logger.debug(f"Reusing cached ffprobe info for {os.path.basename(video_path_for_read)}.")
            # -----------------------------------------------------------------------------

            loaded_frames, fps_from_read, original_h, original_w, processed_h, processed_w, video_stream_info, ffprobe_raw_stdout = read_video_frames(
                video_path_for_read, 
                process_length=process_length_for_read if not segment_job_info else -1,
                target_fps=target_fps_for_video_read,
                target_height=user_target_height, target_width=user_target_width,
                start_frame_index=start_frame_idx, 
                num_frames_to_load=num_frames_to_load_for_seg,
                cached_ffprobe_info=cached_ffprobe_info
            )
            actual_frames_to_process = loaded_frames
            actual_fps_for_save = fps_from_read
            job_specific_metadata["original_height_detected"] = original_h
            job_specific_metadata["original_width_detected"] = original_w
            job_specific_metadata["processed_height"] = processed_h # This is the actual height Decord delivered
            job_specific_metadata["processed_width"] = processed_w  # This is the actual width Decord delivered
            job_specific_metadata["video_stream_metadata"] = video_stream_info # Keep ffprobe info
            job_specific_metadata["ffprobe_raw_stdout"] = ffprobe_raw_stdout
            _logger.debug(f"Loaded {len(actual_frames_to_process) if actual_frames_to_process is not None else 0} frames from video '{video_path_for_read}'. Original FPS for save: {actual_fps_for_save:.2f}")
        
        elif isinstance(video_path_or_job_info, dict):
            source_info = video_path_or_job_info
            source_type = source_info.get("type")
            source_path = source_info.get("path")
            
            if "target_fps_setting" in job_specific_metadata and job_specific_metadata["target_fps_setting"] != -1.0:
                effective_output_fps = job_specific_metadata["target_fps_setting"]
            else: 
                effective_output_fps = 24.0
            
            actual_fps_for_save = effective_output_fps

            if source_type == "image_sequence_folder":
                start_idx_for_segment = 0
                num_img_to_load_for_segment = process_length_for_read

                if segment_job_info:
                    start_idx_for_segment = segment_job_info.get("start_frame_raw_index", 0)
                    num_img_to_load_for_segment = segment_job_info.get("num_frames_to_load_raw", -1)

                frames_this_segment, h, w = read_image_sequence_as_frames(
                    folder_path=source_path,
                    num_frames_to_load=num_img_to_load_for_segment, 
                    target_height=user_target_height,
                    target_width=user_target_width,
                    start_index=start_idx_for_segment
                )
                actual_frames_to_process = frames_this_segment
                original_h_loaded, original_w_loaded = h, w
                _logger.debug(f"Frames Load: Attempting to load image sequence from '{source_path}'. Target FPS: {actual_fps_for_save:.3f}. Segment Start Idx: {start_idx_for_segment}, Num to Load: {num_img_to_load_for_segment}. Loaded: {len(actual_frames_to_process) if actual_frames_to_process is not None else 0} frames.")

            elif source_type == "single_image_file":
                num_frames_gen = segment_job_info["num_frames_to_load_raw"] if segment_job_info else int(round(effective_output_fps))
                
                frames_this_segment, h, w = create_frames_from_single_image(
                    image_path=source_path,
                    num_frames_to_generate=num_frames_gen,
                    target_height=user_target_height,
                    target_width=user_target_width
                )
                actual_frames_to_process = frames_this_segment
                original_h_loaded, original_w_loaded = h, w
                _logger.debug(f"Frames Load: Loaded {len(actual_frames_to_process) if actual_frames_to_process is not None else 0} frames from single image '{source_path}' at {actual_fps_for_save:.1f} FPS (for 1s clip).")
            else:
                job_specific_metadata["status"] = "failure_unknown_source_type_in_dict"
                _logger.error(f"Frames Load: Unknown source type '{source_type}' in input dictionary.")
                return None, 0.0, 0, 0, 8.0

        else:
            job_specific_metadata["status"] = "failure_no_input_source"
            _logger.error("Cannot load frames: No video path or numpy array provided.")
            return None, 0.0, 0, 0, 8.0
        
        if original_h_loaded is not None:
            job_specific_metadata["original_height_loaded"] = original_h_loaded
            job_specific_metadata["original_width_loaded"] = original_w_loaded

        return actual_frames_to_process, actual_fps_for_save, job_specific_metadata["processed_height"], job_specific_metadata["processed_width"], effective_vram

    def _handle_no_frames_failure(self, job_specific_metadata: dict, full_save_path: str,
                                  infer_start_time: float, actual_fps_for_save: float,
                                  segment_job_info: Optional[dict],
                                  save_final_output_json_config_passed_in: bool) -> Tuple[None, dict]:
        video_basename_for_log = job_specific_metadata.get("original_video_basename", "unknown_video")
        _logger.warning(f"No frames to process for {video_basename_for_log}. Skipping.")

        job_specific_metadata["status"] = "failure_no_frames"
        job_specific_metadata["frames_in_output_video"] = 0
        job_specific_metadata["processed_at_fps"] = float(actual_fps_for_save if actual_fps_for_save is not None and actual_fps_for_save > 0 else 0)
        
        infer_duration_sec_noframes = time.perf_counter() - infer_start_time
        job_specific_metadata["internal_processing_duration_seconds"] = round(infer_duration_sec_noframes, 2)
        job_specific_metadata["internal_processing_duration_formatted"] = format_duration(infer_duration_sec_noframes)
        job_specific_metadata["processing_timestamp_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        should_save_failure_json = (segment_job_info is not None) or \
                                   (not segment_job_info and save_final_output_json_config_passed_in)
        
        if should_save_failure_json and full_save_path:
            individual_metadata_json_path_noframes = get_sidecar_json_filename(full_save_path)
            if save_json_file(job_specific_metadata, individual_metadata_json_path_noframes):
                job_specific_metadata["_individual_metadata_path"] = os.path.abspath(individual_metadata_json_path_noframes)
                _logger.info(f"Saved failure JSON (no frames): {individual_metadata_json_path_noframes}")
            else:
                job_specific_metadata["_individual_metadata_path"] = None
        else:
            job_specific_metadata["_individual_metadata_path"] = None
        return None, job_specific_metadata

    def _perform_inference(self, actual_frames_to_process: np.ndarray,
                           guidance_scale: float, num_denoising_steps: int,
                           pipe_call_window_size: int, pipe_call_overlap: int,
                           segment_job_info: Optional[dict],
                           actual_processed_height: int, actual_processed_width: int, # <--- RENAMED
                           effective_vram: float,
                           enable_tiling: bool = False, tile_size: int = 512, tile_overlap: int = 128
                           ) -> np.ndarray:
        current_pipe_window_for_call = pipe_call_window_size
        current_pipe_overlap_for_call = pipe_call_overlap
        if segment_job_info:
            # Cap window size for segments to prevent OOM, while maintaining temporal consistency
            max_window_for_segments = 16  # Adjust based on memory constraints
            current_pipe_window_for_call = min(actual_frames_to_process.shape[0], max_window_for_segments)
            current_pipe_overlap_for_call = max(0, current_pipe_window_for_call // 4)  # Small overlap for continuity
        # For high resolution, reduce window size to prevent OOM based on available VRAM
        if actual_processed_height > 1000 or actual_processed_width > 1000:
            if effective_vram >= 79.5:
                max_win, max_ovlp = 110, 20
            elif effective_vram >= 47.5:
                max_win, max_ovlp = 64, 15
            elif effective_vram >= 31.5:
                max_win, max_ovlp = 48, 12
            elif effective_vram >= 23.5:
                max_win, max_ovlp = 32, 10
            elif effective_vram >= 19.5:
                max_win, max_ovlp = 24, 6
            elif effective_vram >= 15.5:
                max_win, max_ovlp = 16, 4
            else:
                max_win, max_ovlp = 8, 2
            current_pipe_window_for_call = min(current_pipe_window_for_call, max_win)
            current_pipe_overlap_for_call = min(current_pipe_overlap_for_call, max_ovlp)

        _logger.debug(f"Starting inference: Frames: {actual_frames_to_process.shape[0]}, Res: {actual_frames_to_process.shape[1]}x{actual_frames_to_process.shape[2]}, Scale: {guidance_scale}, Steps: {num_denoising_steps}, Win: {current_pipe_window_for_call}, Ovlp: {current_pipe_overlap_for_call}, Tiling: {enable_tiling}")

        if enable_tiling and (actual_processed_height > tile_size or actual_processed_width > tile_size):
            _logger.info(f"Applying spatial tiling: Tile size {tile_size}, Overlap {tile_overlap}")
            res = self._perform_tiled_inference(actual_frames_to_process, guidance_scale, num_denoising_steps,
                                                current_pipe_window_for_call, current_pipe_overlap_for_call,
                                                actual_processed_height, actual_processed_width, tile_size, tile_overlap)
        else:
            _clear_device = False
            torch.cuda.empty_cache()
            with torch.inference_mode():
                # Determine safe decode_chunk_size based on VRAM to prevent VAE OOM
                # Adjust safe_chunk_size based on resolution
                pixels = actual_processed_height * actual_processed_width
                base_pixels = 1024 * 1024
                pixel_ratio = max(1.0, pixels / base_pixels)

                try:
                    from dependency.stereocrafter_util import get_current_vram_usage
                    vram_info = get_current_vram_usage()
                    total_vram = vram_info.get('total', 8)
                    if total_vram <= 8:
                        base_chunk = 1
                    elif total_vram <= 12:
                        base_chunk = 2
                    elif total_vram <= 16:
                        base_chunk = 3
                    elif total_vram <= 24:
                        base_chunk = 6
                    elif total_vram <= 32:
                        base_chunk = 10
                    elif total_vram <= 48:
                        base_chunk = 10
                    elif total_vram <= 80:
                        base_chunk = 12
                    else:
                        base_chunk = 14
                except Exception:
                    if effective_vram >= 79.5:
                        base_chunk = 14
                    elif effective_vram >= 47.5:
                        base_chunk = 12
                    elif effective_vram >= 31.5:
                        base_chunk = 10
                    elif effective_vram >= 23.5:
                        base_chunk = 10
                    elif effective_vram >= 19.5:
                        base_chunk = 6
                    elif effective_vram >= 15.5:
                        base_chunk = 3
                    else:
                        base_chunk = 2
                
                safe_chunk_size = max(1, int(base_chunk / pixel_ratio))

                pipe_kwargs = dict(
                    video=actual_frames_to_process,
                    height=actual_processed_height,
                    width=actual_processed_width,
                    output_type="np",
                    guidance_scale=guidance_scale,
                    num_inference_steps=num_denoising_steps,
                    window_size=current_pipe_window_for_call,
                    overlap=current_pipe_overlap_for_call,
                    decode_chunk_size=safe_chunk_size,
                )

                def _run_pipe():
                    try:
                        if _clear_device:
                            try:
                                torch.cuda.synchronize()
                                torch.cuda.empty_cache()
                            except Exception:
                                pass
                        return self.pipe(**pipe_kwargs).frames[0]
                    except (RuntimeError, OSError) as e:
                        msg = str(e).lower()
                        if 'device not ready' in msg or 'cuda device error' in msg or 'cuda error:' in msg:
                            raise
                        raise

                try:
                    res = _run_pipe()
                except Exception as e:
                    msg = str(e).lower()
                    if any(m in msg for m in ['device not ready', 'cuda device error', 'cuda error:']):
                        _logger.warning("CUDA device not ready error during inference, retrying after reset: %s", e)
                        try:
                            torch.cuda.synchronize()
                            torch.cuda.empty_cache()
                            torch.cuda.reset_peak_memory_stats()
                            gc.collect()
                            import time as _time
                            _time.sleep(1.5)
                            _clear_device = True
                            res = _run_pipe()
                        except Exception as e2:
                            _logger.exception("Retry failed after CUDA driver error; attempting device reset")
                            try:
                                torch.cuda.synchronize()
                                torch.cuda.empty_cache()
                                import time as _time
                                _time.sleep(2.0)
                                torch.cuda.reset_peak_memory_stats()
                                gc.collect()
                                _clear_device = True
                                res = _run_pipe()
                            except Exception as e3:
                                _logger.exception("Inference failed after multiple CUDA retries")
                                raise RuntimeError("CUDA device not ready during inference") from e2
                    else:
                        raise
        inference_result = res
        _logger.debug(f"Inference completed. Result shape: {inference_result.shape}")

        torch.cuda.synchronize()
        gc.collect()
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        if inference_result is not None and inference_result.ndim >= 3: 
            res = res.sum(-1) / res.shape[-1]
            _logger.debug(f"Inference result (RGB/RGBA) averaged to grayscale. Final shape: {res.shape}")
        return res

    def _perform_tiled_inference(self, frames: np.ndarray, guidance_scale: float, num_denoising_steps: int,
                                 window_size: int, overlap: int, height: int, width: int, tile_size: int, tile_overlap: int) -> np.ndarray:
        """Perform inference with spatial tiling for high resolutions."""
        import torch

        # Ensure tile_size is multiple of 64 for model compatibility
        tile_size = (tile_size // 64) * 64
        if tile_size < 64:
            tile_size = 64

        import math
        # Calculate number of tiles
        stride = tile_size - tile_overlap
        num_tiles_h = 1 if height <= tile_size else 1 + math.ceil((height - tile_size) / stride)
        num_tiles_w = 1 if width <= tile_size else 1 + math.ceil((width - tile_size) / stride)

        _logger.debug(f"Tiling: {num_tiles_h}x{num_tiles_w} tiles, size {tile_size}, stride {stride}")

        # Initialize output array (frames, H, W)
        depth_output = np.zeros((frames.shape[0], height, width), dtype=np.float32)
        weight_mask = np.zeros((height, width), dtype=np.float32)

        for i in range(num_tiles_h):
            for j in range(num_tiles_w):
                y_start = i * stride
                x_start = j * stride
                y_end = min(y_start + tile_size, height)
                x_end = min(x_start + tile_size, width)

                tile_h = y_end - y_start
                tile_w = x_end - x_start

                # Extract tile from frames
                tile_frames = frames[:, y_start:y_end, x_start:x_end]

                # Pad if necessary for model
                pad_h = tile_size - tile_h
                pad_w = tile_size - tile_w
                if pad_h > 0 or pad_w > 0:
                    # Provide padding for all 4 dimensions: (frames, H, W, channels)
                    tile_frames = np.pad(
                        tile_frames,
                        ((0, 0), (0, pad_h), (0, pad_w), (0, 0)),
                        mode='reflect'
                    )

                torch.cuda.empty_cache()
                with torch.inference_mode():
                    tile_depth = self.pipe(
                        tile_frames,
                        height=tile_size,
                        width=tile_size,
                        output_type="np",
                        guidance_scale=guidance_scale,
                        num_inference_steps=num_denoising_steps,
                        window_size=window_size,
                        overlap=overlap,
                    ).frames[0]

                # Average to grayscale if model returns RGB/A
                if tile_depth.ndim == 4 and tile_depth.shape[-1] > 1:
                    tile_depth = tile_depth.sum(-1) / tile_depth.shape[-1]

                # Crop padding
                tile_depth = tile_depth[:, :tile_h, :tile_w]

                # --- ALIGNMENT LOGIC ---
                # Align the new tile to the already-processed canvas using the overlapping region
                if i > 0 or j > 0:
                    current_weight_mask = weight_mask[y_start:y_end, x_start:x_end]
                    # Only use pixels where the existing weight is significant
                    overlap_mask = current_weight_mask > 1e-4
                    if np.any(overlap_mask):
                        current_depth_output = depth_output[:, y_start:y_end, x_start:x_end]
                        ref_depth = current_depth_output / np.maximum(current_weight_mask, 1e-8)
                        
                        for f_idx in range(tile_depth.shape[0]):
                            x_vals = tile_depth[f_idx][overlap_mask]
                            y_vals = ref_depth[f_idx][overlap_mask]
                            
                            if len(x_vals) > 10:
                                x_min, x_max = np.percentile(x_vals, 5), np.percentile(x_vals, 95)
                                y_min, y_max = np.percentile(y_vals, 5), np.percentile(y_vals, 95)
                                
                                if x_max - x_min > 1e-5:
                                    s_k = (y_max - y_min) / (x_max - x_min)
                                    t_k = y_min - s_k * x_min
                                else:
                                    s_k = 1.0
                                    t_k = np.median(y_vals) - np.median(x_vals)
                                
                                # Clip scale to prevent extreme distortions
                                s_k = np.clip(s_k, 0.1, 10.0)
                                tile_depth[f_idx] = tile_depth[f_idx] * s_k + t_k
                # --- END ALIGNMENT LOGIC ---

                # Create weight mask for blending
                weight = np.ones((tile_h, tile_w), dtype=np.float32)
                if i > 0:
                    weight[:tile_overlap, :] *= np.linspace(0.0, 1.0, tile_overlap)[:, None]
                if j > 0:
                    weight[:, :tile_overlap] *= np.linspace(0.0, 1.0, tile_overlap)[None, :]
                if i < num_tiles_h - 1:
                    weight[-tile_overlap:, :] *= np.linspace(1.0, 0.0, tile_overlap)[:, None]
                if j < num_tiles_w - 1:
                    weight[:, -tile_overlap:] *= np.linspace(1.0, 0.0, tile_overlap)[None, :]

                # Accumulate depth and weights
                depth_output[:, y_start:y_end, x_start:x_end] += tile_depth * weight[None, :, :]
                weight_mask[y_start:y_end, x_start:x_end] += weight

        # Normalize by weights
        weight_mask = np.maximum(weight_mask, 1e-8)
        depth_output /= weight_mask[None, :, :]

        return depth_output

    def _save_segment_npz(self, res: np.ndarray, full_save_path: str, job_specific_metadata: dict) -> bool:
        try:
            np.savez_compressed(full_save_path, frames=res)
            job_specific_metadata["npz_segment_path"] = os.path.abspath(full_save_path)
            _logger.debug(f"Successfully saved: {full_save_path}")
            return True
        except Exception as e_save_npz:
            _logger.error(f"Failed to save: {full_save_path}. Reason: NPZ segment save error: {e_save_npz}")
            job_specific_metadata["status"] = "failure_npz_save"
            return False

    def _save_intermediate_visual_for_segment(self, res_normalized_for_visual: np.ndarray,
                                               actual_save_folder_for_output: str,
                                               output_filename_for_meta: str,
                                               intermediate_visual_format_to_save: str,
                                               actual_fps_for_save: float,
                                               job_specific_metadata: dict):
        base_filename_no_ext_for_visual = os.path.splitext(os.path.basename(output_filename_for_meta))[0]
        
        visual_save_path_or_dir = None
        visual_save_error = None 
        target_fps_for_visual_float = actual_fps_for_save if actual_fps_for_save > 0 else 23.976

        save_func = None
        save_args = []
        save_kwargs = {} 
        
        if intermediate_visual_format_to_save == "mp4":
            mp4_path = os.path.join(actual_save_folder_for_output, f"{base_filename_no_ext_for_visual}_visual.mp4")
            save_func = save_depth_visual_as_mp4_util
            save_args = [res_normalized_for_visual, mp4_path, target_fps_for_visual_float]
            save_kwargs = {"output_format": "mp4"}
        elif intermediate_visual_format_to_save == "main10_mp4":
            mp4_path = os.path.join(actual_save_folder_for_output, f"{base_filename_no_ext_for_visual}_visual.mp4")
            save_func = save_depth_visual_as_mp4_util
            save_args = [res_normalized_for_visual, mp4_path, target_fps_for_visual_float]
            save_kwargs = {"output_format": "main10_mp4"}
        elif intermediate_visual_format_to_save == "png_sequence":
            save_func = save_depth_visual_as_png_sequence_util
            save_args = [res_normalized_for_visual, actual_save_folder_for_output, base_filename_no_ext_for_visual]
        elif intermediate_visual_format_to_save == "exr_sequence":
            if OPENEXR_AVAILABLE_LOGIC:
                save_func = save_depth_visual_as_exr_sequence_util
                save_args = [res_normalized_for_visual, actual_save_folder_for_output, base_filename_no_ext_for_visual]
            else:
                visual_save_error = "OpenEXR libraries not available in logic module."
        elif intermediate_visual_format_to_save == "exr":
            if OPENEXR_AVAILABLE_LOGIC:
                first_frame_to_save = res_normalized_for_visual[0] if len(res_normalized_for_visual) > 0 else None
                if first_frame_to_save is None: 
                    visual_save_error = "No frame data for single EXR."
                else: 
                    save_func = save_depth_visual_as_single_exr_util
                    save_args = [first_frame_to_save, actual_save_folder_for_output, base_filename_no_ext_for_visual]
            else:
                visual_save_error = "OpenEXR libraries not available in logic module."
        elif intermediate_visual_format_to_save == "none":
            pass 
        else:
            visual_save_error = f"Unknown intermediate visual format: {intermediate_visual_format_to_save}"

        if save_func and not visual_save_error:
            visual_save_path_or_dir, visual_save_error = save_func(*save_args, **save_kwargs)

        if visual_save_path_or_dir:
            job_specific_metadata["intermediate_visual_path"] = os.path.abspath(visual_save_path_or_dir)
            job_specific_metadata["intermediate_visual_format_saved"] = intermediate_visual_format_to_save
            _logger.debug(f"Saved intermediate segment visual in {intermediate_visual_format_to_save}")
        
        if visual_save_error: 
            job_specific_metadata["intermediate_visual_save_error"] = visual_save_error 
            _logger.error(f"Error saving intermediate segment visual ({intermediate_visual_format_to_save}): {visual_save_error}")

    def _save_full_video_output(self, res: np.ndarray, full_save_path: str,
                                actual_fps_for_save: float, job_specific_metadata: dict) -> bool:
        res_min_full, res_max_full = res.min(), res.max()
        if res_max_full != res_min_full:
            res_normalized_for_mp4 = (res - res_min_full) / (res_max_full - res_min_full)
        else:
            res_normalized_for_mp4 = np.zeros_like(res)
        res_normalized_for_mp4 = np.clip(res_normalized_for_mp4, 0, 1)

        try:
            save_video_fps_full = actual_fps_for_save
            if save_video_fps_full == -1.0:
                _logger.warning(f"Logic Save Video: FPS value is still -1.0 at save point, falling back to 30.0. FPS: {save_video_fps_full}")
                save_video_fps_full = 30.0 
            elif save_video_fps_full <= 0:
                _logger.warning(f"Logic Save Video: FPS value is zero or negative at save point, falling back to 30.0. FPS: {save_video_fps_full}")
                save_video_fps_full = 30.0
            
            output_format_for_full_video = job_specific_metadata.get("preferred_output_format", "mp4")

            save_video(res_normalized_for_mp4, full_save_path, fps=save_video_fps_full, output_format=output_format_for_full_video)
            _logger.debug(f"Successfully saved: {full_save_path}")
            return True
        except Exception as e_save_mp4:
            _logger.error(f"Failed to save: {full_save_path}. Reason: Full video MP4 save error: {e_save_mp4}")
            job_specific_metadata["status"] = "failure_mp4_save"
            return False

    def _finalize_job_metadata_and_save_json(self, job_specific_metadata: dict, infer_start_time: float,
                                           actual_fps_for_save: float, frames_processed_count: int,
                                           saved_output_successfully: bool, full_save_path: Optional[str],
                                           segment_job_info: Optional[dict],
                                           save_final_output_json_config_passed_in: bool):
        if "internal_processing_duration_seconds" not in job_specific_metadata: 
            infer_duration_sec = time.perf_counter() - infer_start_time
            job_specific_metadata["internal_processing_duration_seconds"] = round(infer_duration_sec, 2)
            job_specific_metadata["internal_processing_duration_formatted"] = format_duration(infer_duration_sec)

        job_specific_metadata["processed_at_fps"] = float(actual_fps_for_save)
        job_specific_metadata["frames_in_output_video"] = frames_processed_count
        
        if saved_output_successfully and job_specific_metadata["status"] == "pending":
            job_specific_metadata["status"] = "success"
        elif job_specific_metadata["status"] == "pending": 
            job_specific_metadata["status"] = "failure_at_finalize" 
            
        if "processing_timestamp_utc" not in job_specific_metadata: 
            job_specific_metadata["processing_timestamp_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        should_save_this_job_json = (segment_job_info is not None) or \
                                    (not segment_job_info and save_final_output_json_config_passed_in)
        
        if should_save_this_job_json and full_save_path:
            individual_metadata_json_path = get_sidecar_json_filename(full_save_path)
            if save_json_file(job_specific_metadata, individual_metadata_json_path):
                job_specific_metadata["_individual_metadata_path"] = os.path.abspath(individual_metadata_json_path)
            else:
                if job_specific_metadata["status"] == "success": 
                    job_specific_metadata["status"] = "failure_metadata_save" 
                job_specific_metadata["_individual_metadata_path"] = None
        elif job_specific_metadata.get("_individual_metadata_path") is None : 
            job_specific_metadata["_individual_metadata_path"] = None

    def _internal_infer(self,
                        video_path_or_job_info_dict: Union[str, dict],
                        frames_array_if_provided: Optional[np.ndarray],
                        num_denoising_steps: int, guidance_scale: float,
                        base_output_folder: str,
                        user_target_height: int, user_target_width: int,
                        seed_val: int, original_video_basename: str,
                        process_length_for_read: int, gui_target_fps_for_job: float,
                        pipe_call_window_size: int, pipe_call_overlap: int,
                        segment_job_info: Optional[dict] = None,
                        should_save_intermediate_visuals: bool = False,
                        intermediate_visual_format_to_save: str = "none",
                        save_final_output_json_config_passed_in: bool = False,
                        enable_tiling: bool = False, tile_size: int = 512, tile_overlap: int = 128
                        ) -> Tuple[Optional[str], dict]:

        infer_start_time = time.perf_counter()
        set_seed(seed_val)
        _logger.debug(f"Starting inference job for: {original_video_basename} (Seed: {seed_val}, Segment: {bool(segment_job_info)}, ID: {segment_job_info.get('segment_id', -1) if segment_job_info else -1})")

        actual_save_folder_for_output, output_filename_for_meta, full_save_path = \
            self._setup_paths(base_output_folder, original_video_basename, segment_job_info)

        job_specific_metadata = self._initialize_job_metadata(
            guidance_scale, num_denoising_steps, user_target_height, user_target_width, seed_val,
            gui_target_fps_for_job,
            segment_job_info, output_filename_for_meta,
            pipe_call_window_size, pipe_call_overlap, original_video_basename
        )

        actual_frames_to_process, actual_fps_for_save, actual_processed_h, actual_processed_w, effective_vram = self._load_frames(
            video_path_or_job_info=video_path_or_job_info_dict,
            frames_array_if_provided=frames_array_if_provided,
            process_length_for_read=process_length_for_read,
            user_target_height=user_target_height,
            user_target_width=user_target_width,
            segment_job_info=segment_job_info,
            job_specific_metadata=job_specific_metadata
        )
        # Update job_specific_metadata with the *actual* processed H/W if not already set (e.g. from np.array input)
        job_specific_metadata["processed_height"] = actual_processed_h
        job_specific_metadata["processed_width"] = actual_processed_w

        if job_specific_metadata["status"] == "failure_no_input_source":
            self._finalize_job_metadata_and_save_json(
                job_specific_metadata, infer_start_time,
                0.0, 0, False, 
                full_save_path, segment_job_info, save_final_output_json_config_passed_in
            )
            return None, job_specific_metadata

        if actual_frames_to_process is None or actual_frames_to_process.shape[0] == 0:
            return self._handle_no_frames_failure(
                job_specific_metadata, full_save_path, infer_start_time,
                actual_fps_for_save if actual_fps_for_save is not None else 0.0,
                segment_job_info, save_final_output_json_config_passed_in
            )

        inference_result = self._perform_inference(
            actual_frames_to_process, guidance_scale, num_denoising_steps,
            pipe_call_window_size, pipe_call_overlap, segment_job_info,
            actual_processed_h, actual_processed_w, effective_vram,
            enable_tiling, tile_size, tile_overlap
        )

        if inference_result is not None and inference_result.ndim >= 3: # Should be (T, H, W)
            job_specific_metadata["processed_height"] = inference_result.shape[1]
            job_specific_metadata["processed_width"] = inference_result.shape[2]
        else:
            _logger.warning(f"Inference result was not valid for dimension extraction. Inference_result shape: {inference_result.shape if inference_result is not None else 'None'}")
            job_specific_metadata["processed_height"] = "N/A"
            job_specific_metadata["processed_width"] = "N/A"

        saved_output_successfully = False
        if segment_job_info:
            saved_output_successfully = self._save_segment_npz(
                inference_result, full_save_path, job_specific_metadata 
            )
            if saved_output_successfully and should_save_intermediate_visuals and \
               intermediate_visual_format_to_save != "none" and inference_result.size > 0:
                
                res_min_seg, res_max_seg = inference_result.min(), inference_result.max()
                if res_max_seg != res_min_seg:
                    res_normalized_for_visual = (inference_result - res_min_seg) / (res_max_seg - res_min_seg)
                else:
                    res_normalized_for_visual = np.zeros_like(inference_result)
                res_normalized_for_visual = np.clip(res_normalized_for_visual, 0, 1)

                self._save_intermediate_visual_for_segment(
                    res_normalized_for_visual, actual_save_folder_for_output, 
                    output_filename_for_meta, 
                    intermediate_visual_format_to_save,
                    actual_fps_for_save, job_specific_metadata
                )
        else: 
            saved_output_successfully = self._save_full_video_output(
                inference_result, full_save_path, actual_fps_for_save, job_specific_metadata 
            )

        self._finalize_job_metadata_and_save_json(
            job_specific_metadata, infer_start_time,
            actual_fps_for_save, actual_frames_to_process.shape[0],
            saved_output_successfully, full_save_path, 
            segment_job_info, save_final_output_json_config_passed_in
        )
        
        _logger.debug(f"Inference job for {original_video_basename} finished. Status: {job_specific_metadata['status']}. Duration: {job_specific_metadata['internal_processing_duration_formatted']}. Output: {full_save_path if saved_output_successfully else 'N/A'}")
        return full_save_path if saved_output_successfully else None, job_specific_metadata
    
    def run(self,
            video_path_or_frames_or_info: Union[str, np.ndarray, dict],
            num_denoising_steps: int, guidance_scale: float,
            base_output_folder: str, gui_window_size: int, gui_overlap: int,
            process_length_for_read_full_video: int, target_height: int, target_width: int,
            seed: int, original_video_basename_override: Optional[str] = None,
            segment_job_info_param: Optional[dict] = None,
            keep_intermediate_npz_config: bool = False,
            intermediate_segment_visual_format_config: str = "none",
            save_final_json_for_this_job_config: bool = False,
            enable_tiling: bool = False, tile_size: int = 512, tile_overlap: int = 128
            ):
        
        video_path_or_info_for_infer_load: Union[str, dict]
        frames_array_input = None
        original_basename_for_job: str

        current_job_spec: dict
        if segment_job_info_param:
            current_job_spec = segment_job_info_param
            video_path_or_info_for_infer_load = current_job_spec["video_path"]
            if current_job_spec["source_type"] != "video_file":
                 video_path_or_info_for_infer_load = {
                     "type": current_job_spec["source_type"],
                     "path": current_job_spec["video_path"],
                     "gui_fps": current_job_spec["gui_fps_setting_at_definition"]
                 }
            original_basename_for_job = current_job_spec["original_basename"]
        elif isinstance(video_path_or_frames_or_info, dict):
            current_job_spec = video_path_or_frames_or_info
            video_path_or_info_for_infer_load = current_job_spec["video_path"]
            if current_job_spec["source_type"] != "video_file":
                 video_path_or_info_for_infer_load = {
                     "type": current_job_spec["source_type"],
                     "path": current_job_spec["video_path"],
                     "gui_fps": current_job_spec["gui_fps_setting_at_definition"]
                 }
            original_basename_for_job = current_job_spec["original_basename"]
        elif isinstance(video_path_or_frames_or_info, str):
            current_job_spec = {}
            video_path_or_info_for_infer_load = video_path_or_frames_or_info
            original_basename_for_job = original_video_basename_override if original_video_basename_override else os.path.splitext(os.path.basename(video_path_or_frames_or_info))[0]
            _logger.warning(f"DepthCrafterDemo.run received a direct video path '{video_path_or_frames_or_info}' without a full job specification dictionary. Assuming default FPS of -1 (original). It is recommended to pass a job dictionary for full metadata tracking.")
        elif isinstance(video_path_or_frames_or_info, np.ndarray):
            current_job_spec = {}
            frames_array_input = video_path_or_frames_or_info
            video_path_or_info_for_infer_load = None
            if not original_video_basename_override:
                _logger.error("DepthCrafterDemo.run: original_video_basename_override is required for np.ndarray input.")
                raise ValueError("original_video_basename_override needed for np.ndarray input.")
            original_basename_for_job = original_video_basename_override
        else:
            _logger.error(f"DepthCrafterDemo.run: video_path_or_frames must be str or np.ndarray or dict, got {type(video_path_or_frames_or_info).__name__}.")
            raise ValueError("video_path_or_frames_or_info invalid.")


        gui_fps_setting_for_job = current_job_spec.get("gui_fps_setting_at_definition", -1.0)
        if gui_fps_setting_for_job == -1.0 and isinstance(video_path_or_info_for_infer_load, dict):
            gui_fps_setting_for_job = video_path_or_info_for_infer_load.get("gui_fps", -1.0)
        if gui_fps_setting_for_job == -1.0 and not frames_array_input and video_path_or_info_for_infer_load is None:
             _logger.warning(f"Run Logic: Target FPS setting missing in job spec for {original_basename_for_job} and frames/video path not directly available to infer. Defaulting to -1 (original).")


        should_save_visuals_for_infer = False
        intermediate_visual_fmt_for_infer = "none"
        if segment_job_info_param and keep_intermediate_npz_config:
            should_save_visuals_for_infer = True
            intermediate_visual_fmt_for_infer = intermediate_segment_visual_format_config
        
        effective_process_length_for_infer = current_job_spec.get("num_frames_to_load_raw") \
                                             if segment_job_info_param else process_length_for_read_full_video


        save_path, job_metadata_dict = self._internal_infer(
            video_path_or_job_info_dict=video_path_or_info_for_infer_load,
            frames_array_if_provided=frames_array_input,
            num_denoising_steps=num_denoising_steps, guidance_scale=guidance_scale,
            base_output_folder=base_output_folder,
            user_target_width=target_width, user_target_height=target_height,
            seed_val=seed,
            original_video_basename=original_basename_for_job,
            process_length_for_read=effective_process_length_for_infer,
            gui_target_fps_for_job=gui_fps_setting_for_job,
            pipe_call_window_size=gui_window_size, pipe_call_overlap=gui_overlap,
            segment_job_info=segment_job_info_param,
            should_save_intermediate_visuals=should_save_visuals_for_infer,
            intermediate_visual_format_to_save=intermediate_visual_fmt_for_infer,
            save_final_output_json_config_passed_in=save_final_json_for_this_job_config,
            enable_tiling=enable_tiling, tile_size=tile_size, tile_overlap=tile_overlap
        )
        gc.collect(); torch.cuda.empty_cache()
        return save_path, job_metadata_dict