
"""
Inpainting WebUI Component - Complete Gradio Implementation API compatible
Combines features from tkinter GUI, Flask reference, and existing Gradio implementation
"""

import os
import gc
import threading
import queue
import glob
import json
import shutil
import numpy as np
import torch

# Optimize CUDA memory allocation to avoid fragmentation
# This must be set before any CUDA operations
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True,max_split_size_mb:512")

import gradio as gr
from typing import Optional, Tuple, List
import torch.nn.functional as F
import time
import cv2
from decord import VideoReader, cpu
import base64
from io import BytesIO
from PIL import Image as PILImage

from pipelines.stereo_video_inpainting import (
    load_inpainting_pipeline, 
    StableVideoDiffusionInpaintingPipeline, 
    tensor2vid
)

# Import additional components for local loading
from transformers import CLIPImageProcessor, CLIPVisionModelWithProjection
from diffusers.models import AutoencoderKLTemporalDecoder, UNetSpatioTemporalConditionModel
from diffusers.schedulers import EulerDiscreteScheduler
from diffusers.image_processor import VaeImageProcessor
from diffusers.models.attention_processor import AttnProcessor2_0, XFormersAttnProcessor


def load_inpainting_pipeline_hf(
    svd_path: str,
    unet_path: str,
    device: str = "cuda",
    dtype: torch.dtype = torch.float16,
    offload_type: str = "model",
    token: Optional[str] = None
) -> StableVideoDiffusionInpaintingPipeline:
    """
    Load inpainting pipeline from HuggingFace.
    Downloads models if not cached locally.
    """
    logger.info(f"Loading SVD from HuggingFace: {svd_path}")
    logger.info(f"Loading UNet from HuggingFace: {unet_path}")
    
    try:
        # Load entire pipeline from HuggingFace using proper repo IDs
        # SVD components
        logger.info("Loading SVD components from HF...")
        image_encoder = CLIPVisionModelWithProjection.from_pretrained(
            svd_path,
            subfolder="image_encoder",
            variant="fp16",
            torch_dtype=dtype,
            token=token,
        )
        vae = AutoencoderKLTemporalDecoder.from_pretrained(
            svd_path,
            subfolder="vae",
            variant="fp16",
            torch_dtype=dtype,
            token=token,
        )
        feature_extractor = CLIPImageProcessor.from_pretrained(
            svd_path,
            subfolder="feature_extractor",
            token=token,
        )
        scheduler = EulerDiscreteScheduler.from_pretrained(
            svd_path,
            subfolder="scheduler",
            token=token,
        )
        
        # UNet from DepthCrafter
        logger.info("Loading UNet from HF...")
        unet = UNetSpatioTemporalConditionModel.from_pretrained(
            unet_path,
            low_cpu_mem_usage=True,
            torch_dtype=dtype,
            token=token,
        )
        
        image_encoder.requires_grad_(False)
        vae.requires_grad_(False)
        unet.requires_grad_(False)

        # Create pipeline
        pipeline = StableVideoDiffusionInpaintingPipeline(
            vae=vae,
            image_encoder=image_encoder,
            unet=unet,
            scheduler=scheduler,
            feature_extractor=feature_extractor,
        )
        pipeline = pipeline.to(device, dtype=dtype)

        # Configure attention processors
        attention_set = False
        if AttnProcessor2_0 is not None:
            try:
                pipeline.unet.set_attn_processor(AttnProcessor2_0())
                logger.info("Efficient attention (AttnProcessor2_0) enabled for UNet")
                attention_set = True
            except Exception as e:
                logger.warning(f"Failed to enable AttnProcessor2_0: {e}")
        if not attention_set and XFormersAttnProcessor is not None:
            try:
                pipeline.unet.set_attn_processor(XFormersAttnProcessor())
                logger.info("xFormers attention enabled for UNet")
                attention_set = True
            except Exception as e:
                logger.warning(f"Failed to enable xFormers attention: {e}")
        if not attention_set:
            logger.info("Using default attention processor")

        # Apply offloading
        if offload_type == "model":
            pipeline.enable_model_cpu_offload()
        elif offload_type == "sequential":
            pipeline.enable_sequential_cpu_offload()
        elif offload_type == "shared_memory":
            logger.info("Using shared memory offload mode (hybrid)")
            pipeline.image_encoder = pipeline.image_encoder.cpu()
            pipeline.enable_model_cpu_offload()
        elif offload_type == "none":
            pass
        else:
            raise ValueError("Invalid offload_type")

        # Enable VAE slicing to reduce VRAM during VAE encode/decode
        try:
            pipeline.vae.enable_slicing()
            logger.info("VAE slicing enabled for reduced VRAM usage")
        except Exception as e:
            logger.warning(f"Failed to enable VAE slicing: {e}")

        # Enable gradient checkpointing on UNet to reduce VRAM
        try:
            pipeline.unet.enable_gradient_checkpointing()
            logger.info("UNet gradient checkpointing enabled for reduced VRAM usage")
        except Exception as e:
            logger.warning(f"Failed to enable UNet gradient checkpointing: {e}")

        logger.info("Pipeline loaded successfully from HuggingFace!")
        return pipeline
        
    except Exception as e:
        logger.error(f"Error loading from HuggingFace: {e}")
        logger.error("Please ensure you have internet connection and HuggingFace access.")
        raise


def load_inpainting_pipeline_local(
    svd_path: str,
    unet_path: str,
    device: str = "cuda",
    dtype: torch.dtype = torch.float16,
    offload_type: str = "model",
    token: Optional[str] = None
) -> StableVideoDiffusionInpaintingPipeline:
    """
    Load inpainting pipeline from local weights folder.
    Loads StereoCrafter UNet directly without subfolder (HF repo has no unet_diffusers folder).
    Falls back to HuggingFace download if local weights don't exist.
    """
    logger.info("Loading pipeline from local weights...")

    # Check if local paths exist
    svd_exists = os.path.isdir(svd_path)
    unet_exists = os.path.isdir(unet_path)

    if not svd_exists or not unet_exists:
        logger.warning(f"Local weights not found (SVD: {svd_path}, UNet: {unet_path})")
        logger.info("Falling back to HuggingFace download...")
        return load_inpainting_pipeline_hf(
            svd_path="stabilityai/stable-video-diffusion-img2vid-xt-1-1",
            unet_path="tencent/DepthCrafter",
            device=device,
            dtype=dtype,
            offload_type=offload_type,
            token=token
        )

    # Load components from local paths
    logger.info(f"Loading SVD from: {svd_path}")
    logger.info(f"Loading UNet from: {unet_path}")

    try:
        image_encoder = CLIPVisionModelWithProjection.from_pretrained(
            svd_path,
            subfolder="image_encoder",
            variant="fp16",
            torch_dtype=dtype,
            token=token,
            local_files_only=True,
        )
        vae = AutoencoderKLTemporalDecoder.from_pretrained(
            svd_path,
            subfolder="vae",
            variant="fp16",
            torch_dtype=dtype,
            token=token,
            local_files_only=True,
        )
        # Load UNet directly from StereoCrafter root (no unet_diffusers subfolder in HF repo)
        unet = UNetSpatioTemporalConditionModel.from_pretrained(
            unet_path,
            low_cpu_mem_usage=True,
            torch_dtype=dtype,
            token=token,
            local_files_only=True,
        )

        image_encoder.requires_grad_(False)
        vae.requires_grad_(False)
        unet.requires_grad_(False)

        # Load feature extractor and scheduler from SVD path
        feature_extractor = CLIPImageProcessor.from_pretrained(
            svd_path,
            subfolder="feature_extractor",
            local_files_only=True,
        )
        scheduler = EulerDiscreteScheduler.from_pretrained(
            svd_path,
            subfolder="scheduler",
            local_files_only=True,
        )

        # Create pipeline
        pipeline = StableVideoDiffusionInpaintingPipeline(
            vae=vae,
            image_encoder=image_encoder,
            unet=unet,
            scheduler=scheduler,
            feature_extractor=feature_extractor,
        )
        pipeline = pipeline.to(device, dtype=dtype)

        # Configure attention processors
        attention_set = False
        if AttnProcessor2_0 is not None:
            try:
                pipeline.unet.set_attn_processor(AttnProcessor2_0())
                logger.info("Efficient attention (AttnProcessor2_0) enabled for UNet")
                attention_set = True
            except Exception as e:
                logger.warning(f"Failed to enable AttnProcessor2_0: {e}")
        if not attention_set and XFormersAttnProcessor is not None:
            try:
                pipeline.unet.set_attn_processor(XFormersAttnProcessor())
                logger.info("xFormers attention enabled for UNet")
                attention_set = True
            except Exception as e:
                logger.warning(f"Failed to enable xFormers attention: {e}")
        if not attention_set:
            logger.info("Using default attention processor")

        # Apply offloading
        if offload_type == "model":
            pipeline.enable_model_cpu_offload()
        elif offload_type == "sequential":
            pipeline.enable_sequential_cpu_offload()
        elif offload_type == "shared_memory":
            # Hybrid approach: Keep critical components on GPU, offload others to shared memory
            # Best for systems with shared GPU memory (e.g., RTX 3060 12GB + 32GB shared)
            logger.info("Using shared memory offload mode (hybrid)")
            # UNet and VAE stay on GPU (already loaded)
            # Move image_encoder to CPU (used only once per chunk)
            pipeline.image_encoder = pipeline.image_encoder.cpu()
            # Enable model offload for remaining components
            pipeline.enable_model_cpu_offload()
        elif offload_type == "none":
            pass
        else:
            raise ValueError("Invalid offload_type")

        # Enable VAE slicing to reduce VRAM during VAE encode/decode
        # This processes the VAE in smaller spatial slices instead of all at once
        try:
            pipeline.vae.enable_slicing()
            logger.info("VAE slicing enabled for reduced VRAM usage")
        except Exception as e:
            logger.warning(f"Failed to enable VAE slicing: {e}")

        # Enable gradient checkpointing on UNet to reduce VRAM
        # Trades compute for memory by recomputing activations during forward pass
        try:
            pipeline.unet.enable_gradient_checkpointing()
            logger.info("UNet gradient checkpointing enabled for reduced VRAM usage")
        except Exception as e:
            logger.warning(f"Failed to enable UNet gradient checkpointing: {e}")

        return pipeline
        
    except Exception as e:
        logger.error(f"Error loading from local weights: {e}")
        logger.info("Falling back to HuggingFace download...")
        return load_inpainting_pipeline_hf(
            svd_path="stabilityai/stable-video-diffusion-img2vid-xt-1-1",
            unet_path="tencent/DepthCrafter",
            device=device,
            dtype=dtype,
            offload_type=offload_type,
            token=token
        )
from dependency.stereocrafter_util import (
    get_video_stream_info, draw_progress_bar,
    release_cuda_memory, set_util_logger_level,
    encode_frames_to_mp4, read_video_frames_decord, logger
)
import dependency.stereocrafter_util as sc_util

# ==================== HELPER FUNCTIONS (moved to top for availability) ====================

def blend_h(a: torch.Tensor, b: torch.Tensor, overlap_size: int) -> torch.Tensor:
    """Blend two tensors horizontally"""
    weight_b = (torch.arange(overlap_size).view(1, 1, 1, -1) / overlap_size).to(b.device)
    b[:, :, :, :overlap_size] = (
        (1 - weight_b) * a[:, :, :, -overlap_size:] + weight_b * b[:, :, :, :overlap_size]
    )
    return b

def blend_v(a: torch.Tensor, b: torch.Tensor, overlap_size: int) -> torch.Tensor:
    """Blend two tensors vertically"""
    weight_b = (torch.arange(overlap_size).view(1, 1, -1, 1) / overlap_size).to(b.device)
    b[:, :, :overlap_size, :] = (
        (1 - weight_b) * a[:, :, -overlap_size:, :] + weight_b * b[:, :, :overlap_size, :]
    )
    return b

def pad_for_tiling(frames: torch.Tensor, tile_num: int, tile_overlap=(128, 128)) -> torch.Tensor:
    """
    Zero-pads a batch of frames (shape [T, C, H, W]) so that (H, W) fits perfectly into 'tile_num' splits plus overlap.
    """
    if tile_num <= 1:
        return frames

    T, C, H, W = frames.shape
    overlap_y, overlap_x = tile_overlap

    # Calculate ideal tile dimensions and strides
    stride_y = max(1, (H + overlap_y * (tile_num - 1)) // tile_num - overlap_y)
    stride_x = max(1, (W + overlap_x * (tile_num - 1)) // tile_num - overlap_x)

    # Recalculate size based on stride
    ideal_H = stride_y * tile_num + overlap_y
    ideal_W = stride_x * tile_num + overlap_x

    pad_bottom = max(0, ideal_H - H)
    pad_right = max(0, ideal_W - W)

    if pad_bottom > 0 or pad_right > 0:
        frames = F.pad(frames, (0, pad_right, 0, pad_bottom), mode="constant", value=0.0)
    return frames

def spatial_tiled_process(
    cond_frames: torch.Tensor,
    mask_frames: torch.Tensor,
    process_func,
    tile_num: int,
    spatial_n_compress: int = 8,
    num_inference_steps: int = 5,
    **kwargs,
) -> torch.Tensor:
    """
    Splits frames into tiles, processes them with process_func, then blends result.
    Enhanced with better memory management for lower VRAM cards like RTX 3060.
    """
    height = cond_frames.shape[2]
    width = cond_frames.shape[3]

    # Reduce tile overlap for better memory management on lower VRAM cards
    tile_overlap = (64, 64)  # Reduced from 128 to 64
    overlap_y, overlap_x = tile_overlap

    # Calculate tile sizes and strides
    size_y = (height + overlap_y * (tile_num - 1)) // tile_num
    size_x = (width + overlap_x * (tile_num - 1)) // tile_num

    # Force tile sizes to be multiples of spatial_n_compress (8) to prevent fractional dimension loss during VAE encode/decode
    size_y = ((size_y + spatial_n_compress - 1) // spatial_n_compress) * spatial_n_compress
    size_x = ((size_x + spatial_n_compress - 1) // spatial_n_compress) * spatial_n_compress

    tile_size = (size_y, size_x)
    tile_stride = (max(1, size_y - overlap_y), max(1, size_x - overlap_x))

    cols = []
    for i in range(tile_num):
        row_tiles = []
        for j in range(tile_num):
            y_start = i * tile_stride[0]
            x_start = j * tile_stride[1]
            y_end = min(y_start + tile_size[0], height)
            x_end = min(x_start + tile_size[1], width)

            cond_tile = cond_frames[:, :, y_start:y_end, x_start:x_end]
            mask_tile = mask_frames[:, :, y_start:y_end, x_start:x_end]

            # Pad tile to multiple of 8
            h_tile, w_tile = cond_tile.shape[2], cond_tile.shape[3]
            pad_h = (8 - h_tile % 8) % 8
            pad_w = (8 - w_tile % 8) % 8

            if pad_h > 0 or pad_w > 0:
                cond_tile_proc = F.pad(cond_tile, (0, pad_w, 0, pad_h), mode="constant", value=0.0)
                mask_tile_proc = F.pad(mask_tile, (0, pad_w, 0, pad_h), mode="constant", value=0.0)
            else:
                cond_tile_proc = cond_tile
                mask_tile_proc = mask_tile

            with torch.no_grad():
                tile_output_padded = process_func(
                    frames=cond_tile_proc,
                    frames_mask=mask_tile_proc,
                    height=cond_tile_proc.shape[2],
                    width=cond_tile_proc.shape[3],
                    num_frames=len(cond_tile_proc),
                    output_type="latent",
                    num_inference_steps=num_inference_steps,
                    **kwargs,
                ).frames[0]

                # Crop back
                h_latent = h_tile // 8
                w_latent = w_tile // 8
                tile_output = tile_output_padded[:, :, :h_latent, :w_latent]

            # Clean up intermediate tensors to save memory
            del cond_tile_proc, mask_tile_proc, tile_output_padded
            # NOTE: Cache clearing moved to end of function for better VRAM utilization

            row_tiles.append(tile_output)
        cols.append(row_tiles)

    # Blend tiles
    latent_stride = (tile_stride[0] // spatial_n_compress, tile_stride[1] // spatial_n_compress)
    latent_overlap = (overlap_y // spatial_n_compress, overlap_x // spatial_n_compress)

    blended_rows = []
    for i, row_tiles in enumerate(cols):
        row_result = []
        for j, tile in enumerate(row_tiles):
            if i > 0:
                tile = blend_v(cols[i - 1][j], tile, latent_overlap[0])
            if j > 0:
                tile = blend_h(row_result[j - 1], tile, latent_overlap[1])
            row_result.append(tile)
        blended_rows.append(row_result)

    final_rows = []
    for i, row_tiles in enumerate(blended_rows):
        for j, tile in enumerate(row_tiles):
            if i < len(blended_rows) - 1:
                tile = tile[:, :, :latent_stride[0], :]
            if j < len(row_tiles) - 1:
                tile = tile[:, :, :, :latent_stride[1]]
            row_tiles[j] = tile
        final_rows.append(torch.cat(row_tiles, dim=3))

    x = torch.cat(final_rows, dim=2)
    # Clean up intermediate lists to save memory
    del cols, blended_rows, final_rows
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return x

# ==================== END HELPER FUNCTIONS ====================



class InpaintingWebUI:
    """Complete Gradio-based UI for stereo video inpainting with all features"""

    def __init__(self):
        # Configuration
        self.app_config = self.load_config()
        
        # Load VRAM-aware defaults
        from dependency.stereocrafter_util import get_vram_config
        vram_config = get_vram_config()
        self.vram_defaults = {
            'frames_chunk': vram_config['frames_chunk'],
            'frame_overlap': vram_config['overlap'],
            'decode_chunk_size': vram_config['decode_chunk_size']
        }

        # Processing control
        self.stop_event = threading.Event()
        self.progress_queue = queue.Queue()
        self.processing_thread = None
        self.pipeline = None

    def read_input_resolution(self, input_folder):
        """Scan the input folder, read the first splatted video, and auto-adjust VRAM settings based on resolution."""
        try:
            if not os.path.isdir(input_folder):
                return (
                    gr.update(value="❌ Input folder does not exist"),
                    gr.update(), gr.update(), gr.update(), gr.update(),
                    gr.update(value="N/A"),
                )

            videos = sorted(glob.glob(os.path.join(input_folder, "*.mp4")))
            splatted = [
                v for v in videos
                if "_splatted2" in os.path.basename(v) or "_splatted4" in os.path.basename(v)
            ]
            if not splatted:
                return (
                    gr.update(value="⚠️ No splatted videos found in folder"),
                    gr.update(), gr.update(), gr.update(), gr.update(),
                    gr.update(value="N/A"),
                )

            first_video = splatted[0]
            frames, fps, orig_h, orig_w, proc_h, proc_w, _ = read_video_frames_decord(
                first_video, process_length=1
            )

            from dependency.stereocrafter_util import get_gpu_memory_info
            gpu_info = get_gpu_memory_info()
            total_dedicated_gb = gpu_info.get('total_dedicated_gb', 0)
            
            # Default fallback values
            new_tile = 1
            new_chunk = 10
            new_offload = 'model'
            new_steps = 5
            
            # Logic for 4K (width >= 3000)
            if orig_w >= 3000:
                if total_dedicated_gb >= 30:
                    # 32GB+ RTX 5090 / 6000 Ada -> Max Speed
                    new_tile = 2
                    new_chunk = 24
                    new_offload = 'none'
                elif total_dedicated_gb >= 20:
                    # 24GB RTX 3090 / 4090 -> Balanced
                    new_tile = 4
                    new_chunk = 24
                    new_offload = 'model'
                else:
                    # < 20GB -> Max Safety
                    new_tile = 4
                    new_chunk = 10
                    new_offload = 'model'
            else:
                # Logic for 1080p (width < 3000)
                new_tile = 1
                if total_dedicated_gb >= 12:
                    new_chunk = 24
                    new_offload = 'none'
                else:
                    new_chunk = 10
                    new_offload = 'model'

            res_str = f"{orig_w}x{orig_h} original | inpainting width: {orig_w // 2}px"
            status_msg = (
                f"✓ Detected {orig_w}x{orig_h} ({total_dedicated_gb:.1f}GB VRAM): "
                f"Applied Tile {new_tile}, Chunk {new_chunk}, Offload {new_offload}, Steps {new_steps}"
            )

            return (
                gr.update(value=status_msg),
                gr.update(value=new_tile),
                gr.update(value=new_chunk),
                gr.update(value=new_offload),
                gr.update(value=new_steps),
                gr.update(value=res_str),
            )
        except Exception as e:
            logger.error(f"Failed to read input resolution: {e}", exc_info=True)
            return (
                gr.update(value=f"❌ Error: {e}"),
                gr.update(), gr.update(), gr.update(), gr.update(),
                gr.update(value="Error"),
            )



    def load_config(self):
        """Load configuration from config_inpaint.json"""
        try:
            with open("config_inpaint.json", "r") as f:
                return json.load(f)
        except FileNotFoundError:
            # Default structure with VRAM-aware defaults
            # Load VRAM config for GPU-appropriate defaults
            from dependency.stereocrafter_util import get_vram_config, get_gpu_memory_info
            
            vram_config = get_vram_config()
            gpu_info = get_gpu_memory_info()
            
            # Auto-detect best offload type based on GPU configuration
            gpu_name = gpu_info.get('gpu_name', '').lower()
            total_dedicated_gb = gpu_info.get('total_dedicated_gb', 0)
            
            # RTX 3060 12GB or better: Use 'none' for maximum speed
            # Shared memory mode introduces PCIe overhead that slows down processing
            if total_dedicated_gb >= 12:
                # 12GB+ dedicated VRAM is enough for full GPU processing
                default_offload = 'none'
            elif total_dedicated_gb >= 8:
                # 8-12GB: Model offload for safety
                default_offload = 'model'
            else:
                # <8GB: Sequential offload (slowest but necessary)
                default_offload = 'sequential'
            
            logger.info(f"Auto-selected offload_type='{default_offload}' based on GPU: {gpu_info.get('gpu_name', 'Unknown')} ({total_dedicated_gb:.1f}GB)")
            
            return {
                'input_folder': './output_splatted/lowres',
                'output_folder': './output_inpainted',
                'hires_blend_folder': './output_splatted/hires',
                'num_inference_steps': 5,
                'tile_num': 1,
                'frames_chunk': vram_config['frames_chunk'],
                'frame_overlap': vram_config['overlap'],
                'original_input_blend_strength': 0.0,
                'output_crf': 18,
                'process_length': -1,
                'offload_type': default_offload,
                'mask_initial_threshold': 0.3,
                'mask_morph_kernel_size': 0.0,
                'mask_dilate_kernel_size': 5,
                'mask_blur_kernel_size': 10,
                'enable_post_inpainting_blend': True,  # Enabled for quality
                'enable_color_transfer': True,  # Enabled for quality
                'decode_chunk_size': vram_config['decode_chunk_size']
            }
    
    def save_config(self, config_dict):
        """Save configuration to config_inpaint.json"""
        try:
            with open("config_inpaint.json", "w", encoding='utf-8') as f:
                json.dump(config_dict, f, indent=4)
            return "✓ Configuration saved successfully"
        except Exception as e:
            return f"✗ Failed to save config: {e}"
    
    def load_config_to_ui(self):
        """Load configuration and return values for all UI components"""
        try:
            config = self.load_config()
            return (
                config.get('input_folder', './output_splatted/lowres'),
                config.get('output_folder', './output_inpainted'),
                config.get('hires_blend_folder', './output_splatted/hires'),
                config.get('num_inference_steps', 5),
                config.get('decode_chunk_size', self.vram_defaults['decode_chunk_size']),
                config.get('tile_num', 1),
                config.get('frames_chunk', self.vram_defaults['frames_chunk']),
                config.get('frame_overlap', self.vram_defaults['frame_overlap']),
                config.get('original_input_blend_strength', 0.0),
                config.get('output_crf', 18),
                config.get('process_length', -1),
                config.get('offload_type', 'none'),
                config.get('mask_initial_threshold', 0.3),
                config.get('mask_morph_kernel_size', 0.0),
                config.get('mask_dilate_kernel_size', 5),
                config.get('mask_blur_kernel_size', 10),
                config.get('enable_post_inpainting_blend', False),
                config.get('enable_color_transfer', True),
                config.get('hf_token', ''),
                "✓ Configuration loaded successfully"
            )
        except Exception as e:
            # Return current values on error
            return tuple([None] * 19 + [f"✗ Failed to load config: {e}"])
    
    def reset_to_defaults(self):
        """Reset all parameters to default values (VRAM-aware)"""
        return (
            './output_splatted/lowres',  # input_folder
            './output_inpainted',  # output_folder
            './output_splatted/hires',  # hires_blend_folder
            5,  # num_inference_steps
            self.vram_defaults['decode_chunk_size'],  # decode_chunk_size (VRAM-aware)
            1,  # tile_num
            self.vram_defaults['frames_chunk'],  # frames_chunk (VRAM-aware)
            self.vram_defaults['frame_overlap'],  # frame_overlap (VRAM-aware)
            0.0,  # original_input_blend_strength
            18,  # output_crf
            -1,  # process_length
            'none',  # offload_type (changed for better VRAM utilization)
            0.3,  # mask_initial_threshold
            0.0,  # mask_morph_kernel_size
            5,  # mask_dilate_kernel_size
            10,  # mask_blur_kernel_size
            False,  # enable_post_inpainting_blend
            True,  # enable_color_transfer
            '',  # hf_token
            "✓ Reset to default values"
        )

    def create_interface(self, hf_token=None):
        """Create the complete Gradio interface"""
        
        with gr.Blocks() as interface:
            gr.Markdown("## 🎨 Stereocrafter Inpainting (Batch)")
            
            # Folders Section (Top)
            with gr.Group():
                gr.Markdown("### Folders")
                with gr.Row():
                    with gr.Column(scale=3):
                        input_folder = gr.Textbox(
                            label="Input Folder",
                            value=self.app_config.get("input_folder", "./output_splatted/lowres"),
                            info="Select the directory containing your input MP4 videos. The script expects '_splatted4' for quad inputs (Original, Depth, Mask, Warped) or '_splatted2' for dual inputs (Mask, Warped)."
                        )
                    with gr.Column(scale=2):
                        read_res_button = gr.Button("Read Input Resolution", elem_id="read-res-btn", variant="primary")
                
                gr.Markdown(
                    "**Only press this button after you've set your Input Folder.**\n\n"
                    "**Method 1 (Precise Inpainting)**: Requires ONLY the hi-res splat files. Change 'Input Folder' to your hi-res folder, and leave 'Hi-Res Blend Folder' empty. Maximum quality, native 4K processing.\n\n"
                    "**Method 2 (Fast Inpainting)**: (Default) Requires BOTH folders. Set 'Input Folder' to lowres and 'Hi-Res Blend Folder' to hires. AI processes at 1080p for massive speed, then stitches into 4K."
                )

                with gr.Row():
                    hires_blend_folder = gr.Textbox(
                        label="Hi-Res Blend Folder",
                        value=self.app_config.get("hires_blend_folder", "./output_splatted/hires"),
                        info="Path to hi-res splatted videos for final blending (optional)."
                    )
                with gr.Row():
                    output_folder = gr.Textbox(
                        label="Output Folder",
                        value=self.app_config.get("output_folder", "./output_inpainted"),
                        info="Choose the directory where the processed (inpainted) videos will be saved. Output will be Side-by-Side (original | inpainted) for quad inputs, or only the inpainted right eye for dual inputs."
                    )
                with gr.Row():
                    input_res_display = gr.Textbox(label="Detected Input Resolution", value="Not read yet", interactive=False)
            
            # Parameters Section
            with gr.Group():
                gr.Markdown("### Parameters")
                with gr.Row():
                    with gr.Column():
                        num_inference_steps = gr.Slider(
                            minimum=1, maximum=50, value=float(self.app_config.get("num_inference_steps", 6)),
                            step=1, label="Inference Steps",
                            info="Number of denoising steps. Higher = better quality but slower. Default: 6"
                        )
                        
                        with gr.Accordion("⚡ Performance Settings (Advanced)", open=False):
                            gr.Markdown("""
                            **Decode Chunk Size**: Higher values = faster but more VRAM
                            - RTX 5090/6000 Ada (48GB+): Use 14-25 (optimal) or 25+ (maximum performance)
                            - RTX 4090/5090 (24GB+): Use 8-14 (safe) or 14-20 (aggressive)
                            - RTX 3090/4080 (12-24GB): Use 4-8 (safe) or 8-12 (aggressive)
                            - RTX 3060/4060 (8-12GB): Use 2-6 (recommended) or 6-10 (aggressive)

                            ⚠️ **Warning**: Values above 12 may cause OOM on GPUs with less than 24GB VRAM!
                            """)
                            decode_chunk_size = gr.Slider(
                                minimum=1, maximum=25, value=int(self.app_config.get("decode_chunk_size", self.vram_defaults['decode_chunk_size'])),
                                step=1, label="Decode Chunk Size",
                                info=f"Frames decoded at once. Higher = faster + more VRAM. Default: {self.vram_defaults['decode_chunk_size']} (auto-detected based on GPU VRAM)"
                            )
                        tile_num = gr.Slider(
                            minimum=1, maximum=10, value=float(self.app_config.get("tile_num", 1)),
                            step=1, label="Tile Splits",
                            info="Number of spatial tiles to split each video frame into. Set to 1 to disable tiling (HIGHLY RECOMMENDED). Values > 1 cause severe spatial smearing and seams. Default: 1"
                        )
                        frames_chunk = gr.Slider(
                            minimum=1, maximum=50, value=float(self.app_config.get("frames_chunk", self.vram_defaults['frames_chunk'])),
                            step=1, label="Frames Chunk",
                            info=f"The number of frames processed together in a single temporal batch. Adjust based on your GPU memory. Larger chunks can be faster but require more VRAM. Default: {self.vram_defaults['frames_chunk']} (auto-detected based on GPU VRAM)"
                        )
                        process_length = gr.Number(
                            label="Process Length (-1 for all)",
                            value=int(self.app_config.get("process_length", -1)),
                            precision=0,
                            info="Number of frames to process for each video. Enter -1 to process all frames, or a positive integer to limit the processing to the first N frames. Useful for quick testing."
                        )
                    
                    with gr.Column():
                        original_input_blend_strength = gr.Slider(
                            minimum=0.0, maximum=1.0, value=float(self.app_config.get("original_input_blend_strength", 0.0)),
                            step=0.01, label="Original Input Bias",
                            info="Controls how much the original warped input (1.0) versus the previous generated inpainted frame (0.0) influences the blend during temporal overlap. Higher for less hallucination but less consistency. Default: 0 = Off"
                        )
                        frame_overlap = gr.Slider(
                            minimum=0, maximum=20, value=float(self.app_config.get("frame_overlap", self.vram_defaults['frame_overlap'])),
                            step=1, label="Frame Overlap",
                            info="The number of frames that temporally overlap between consecutive processing chunks. These overlapping frames from the previous generated output and original input are smoothly blended to condition the start of the current chunk, reducing visual glitches. Default: 6 (balanced for speed and quality, user-optimized)"
                        )
                        output_crf = gr.Slider(
                            minimum=0, maximum=51, value=float(self.app_config.get("output_crf", 18)),
                            step=1, label="Output CRF",
                            info="Constant Rate Factor for video encoding (lower is higher quality). Adjust based on codec (H.264/H.265)."
                        )
                        offload_type = gr.Dropdown(
                            choices=["none", "model", "sequential", "shared_memory"],
                            value=self.app_config.get("offload_type", "model"),
                            label="CPU Offload Type",
                            info="Determines how parts of the model are moved to CPU memory. 'model' offloads components between steps (balanced, default). 'none' keeps everything on GPU (fastest, for 48GB+ VRAM). 'sequential' offloads layers one-by-one (slowest, for <8GB). 'shared_memory' experimental mode for systems with shared GPU memory (RAM higher than 32GB)."
                        )
            
            # Mask Processing Section
            with gr.Group():
                gr.Markdown("### Mask Processing")
                with gr.Row():
                    mask_initial_threshold = gr.Slider(
                        minimum=0.0, maximum=1.0, value=float(self.app_config.get("mask_initial_threshold", 0.3)),
                        step=0.01, label="Mask Binarize Threshold",
                        info="Sets a mid value to turn a grayscale image into black and white, separating light and dark areas (0 to 1). Set to 0 to disable."
                    )
                    mask_morph_kernel_size = gr.Slider(
                        minimum=0, maximum=50, value=float(self.app_config.get("mask_morph_kernel_size", 0.0)),
                        step=0.5, label="Morph Close Kernel",
                        info="Kernel size for morphological closing: Defines the size of the shape used to fill small holes and smooth edges in an image during the closing process (e.g., 3, 5). Set to 0 to disable."
                    )
                
                with gr.Row():
                    mask_dilate_kernel_size = gr.Slider(
                        minimum=0, maximum=150, value=float(self.app_config.get("mask_dilate_kernel_size", 5.0)),
                        step=0.5, label="Mask Dilate Kernel",
                        info="Sets the size of the shape used to expand white areas in a mask, making objects larger and filling small gaps during dilation (e.g., 7, 15). Set to 0 to disable. This default value is based on the current input resolution."
                    )
                    mask_blur_kernel_size = gr.Slider(
                        minimum=0, maximum=250, value=float(self.app_config.get("mask_blur_kernel_size", 10.0)),
                        step=0.5, label="Mask Blur Kernel",
                        info="Kernel size for Gaussian blur (e.g., 15, 25). Sigma is derived automatically. Set to 0 to disable. This default value is based on the current input resolution."
                    )
            
            # Post-Processing Section
            with gr.Group():
                gr.Markdown("### Post-Processing")
                with gr.Row():
                    enable_post_inpainting_blend = gr.Checkbox(
                        label="Enable Post-Inpainting Blend",
                        value=self.app_config.get("enable_post_inpainting_blend", False),
                        info="Toggle the final post-inpainting blending step and enable/disable its parameters."
                    )
                    enable_color_transfer = gr.Checkbox(
                        label="Enable Color Transfer",
                        value=self.app_config.get("enable_color_transfer", True),
                        info="Adjusts inpainted colors to match original footage. Adds ~15-20 seconds per 127 frames (optimized). Recommended for final renders."
                    )

            # Progress Section
            with gr.Group():
                gr.Markdown("### Progress")
                status_label = gr.Textbox(label="Status", value="Ready", interactive=False)
                with gr.Row():
                    video_name = gr.Textbox(label="Name", value="N/A", interactive=False)
                    video_res = gr.Textbox(label="Resolution", value="N/A", interactive=False)
                    video_frames = gr.Textbox(label="Frames", value="N/A", interactive=False)
                progress_bar = gr.Slider(
                    minimum=0, maximum=100, value=0,
                    label="File Progress (%)", interactive=False
                )
                batch_progress = gr.Textbox(label="Batch Progress", value="0/0", interactive=False)



            # Control Buttons
            with gr.Row():
                start_button = gr.Button("Start", variant="primary")
                stop_button = gr.Button("Stop", variant="secondary", interactive=False)
            
            with gr.Row():
                save_config_button = gr.Button("Save Config", variant="secondary")
                load_config_button = gr.Button("Load Config", variant="secondary")
                reset_config_button = gr.Button("Reset to Defaults", variant="secondary")
            


            # ==================== EVENT HANDLERS ====================

            # Toggle mask sliders based on Post-Inpainting Blend checkbox (matches GUI)
            def toggle_mask_sliders(enabled):
                return [
                    gr.update(interactive=enabled),  # mask_initial_threshold
                    gr.update(interactive=enabled),  # mask_morph_kernel_size
                    gr.update(interactive=enabled),  # mask_dilate_kernel_size
                    gr.update(interactive=enabled)   # mask_blur_kernel_size
                ]
            
            enable_post_inpainting_blend.change(
                fn=toggle_mask_sliders,
                inputs=[enable_post_inpainting_blend],
                outputs=[mask_initial_threshold, mask_morph_kernel_size, mask_dilate_kernel_size, mask_blur_kernel_size]
            )
            
            # Read input resolution and auto-adjust for VRAM and speed
            read_res_button.click(
                fn=self.read_input_resolution,
                inputs=[input_folder],
                outputs=[status_label, tile_num, frames_chunk, offload_type, num_inference_steps, input_res_display]
            )
            
            # Collect all parameters
            all_params = [
                input_folder, output_folder, hires_blend_folder,
                num_inference_steps, decode_chunk_size, tile_num, frames_chunk, frame_overlap,
                original_input_blend_strength, output_crf, process_length, offload_type,
                mask_initial_threshold, mask_morph_kernel_size,
                mask_dilate_kernel_size, mask_blur_kernel_size,
                enable_post_inpainting_blend, enable_color_transfer, hf_token
            ]
            
            # All output components
            all_outputs = [status_label, progress_bar, batch_progress, video_name, video_res, 
                          video_frames, start_button, stop_button]

            # Start processing
            start_button.click(
                fn=self.start_processing,
                inputs=all_params,
                outputs=all_outputs,
                show_progress="hidden"
            )

            # Stop processing
            stop_button.click(
                fn=self.stop_processing,
                inputs=[],
                outputs=[status_label, start_button, stop_button]
            )

            # Save config
            save_config_button.click(
                fn=lambda *args: self.save_config({
                    "input_folder": args[0], "output_folder": args[1], "hires_blend_folder": args[2],
                    "num_inference_steps": int(args[3]), "decode_chunk_size": int(args[4]),
                    "tile_num": int(args[5]), "frames_chunk": int(args[6]),
                    "frame_overlap": int(args[7]), "original_input_blend_strength": float(args[8]),
                    "output_crf": int(args[9]), "process_length": int(args[10]), "offload_type": args[11],
                    "mask_initial_threshold": float(args[12]), "mask_morph_kernel_size": float(args[13]),
                    "mask_dilate_kernel_size": float(args[14]), "mask_blur_kernel_size": float(args[15]),
                    "enable_post_inpainting_blend": args[16], "enable_color_transfer": args[17],
                    "hf_token": args[18]
                }),
                inputs=all_params,
                outputs=[status_label]
            )
            
            # Load config
            load_config_button.click(
                fn=self.load_config_to_ui,
                outputs=[input_folder, output_folder, hires_blend_folder,
                        num_inference_steps, decode_chunk_size, tile_num, frames_chunk, frame_overlap,
                        original_input_blend_strength, output_crf, process_length, offload_type,
                        mask_initial_threshold, mask_morph_kernel_size,
                        mask_dilate_kernel_size, mask_blur_kernel_size,
                        enable_post_inpainting_blend, enable_color_transfer, hf_token, status_label]
            )
            
            # Reset to defaults
            reset_config_button.click(
                fn=self.reset_to_defaults,
                outputs=[input_folder, output_folder, hires_blend_folder,
                        num_inference_steps, decode_chunk_size, tile_num, frames_chunk, frame_overlap,
                        original_input_blend_strength, output_crf, process_length, offload_type,
                        mask_initial_threshold, mask_morph_kernel_size,
                        mask_dilate_kernel_size, mask_blur_kernel_size,
                        enable_post_inpainting_blend, enable_color_transfer, hf_token, status_label]
            )

        return interface

    def scan_for_videos(self, input_folder):

        """Scan for splatted videos"""
        logger.info(f"Scanning for videos in: {input_folder}")
        if not os.path.exists(input_folder):
            logger.warning(f"Input folder does not exist: {input_folder}")
            return []

        logger.info("Starting glob search for *.mp4 files...")
        videos = sorted(glob.glob(os.path.join(input_folder, "*.mp4")))
        logger.info(f"Found {len(videos)} MP4 files")
        
        # Filter for splatted videos
        splatted_videos = [v for v in videos if ('_splatted2' in os.path.basename(v) or 
                                                  '_splatted4' in os.path.basename(v))]
        logger.info(f"Found {len(splatted_videos)} splatted videos")
        return splatted_videos

    # ==================== PROCESSING METHODS ====================

    def start_processing(self, *args, ):
        """Start batch processing with live logging"""
        # Extract parameters
        (input_folder, output_folder, hires_blend_folder,
         num_inference_steps, decode_chunk_size, tile_num, frames_chunk, frame_overlap,
         original_input_blend_strength, output_crf, process_length, offload_type,
         mask_initial_threshold, mask_morph_kernel_size,
         mask_dilate_kernel_size, mask_blur_kernel_size,
         enable_post_inpainting_blend, enable_color_transfer, hf_token) = args

        # Validate
        try:
            num_inference_steps = int(num_inference_steps)
            decode_chunk_size = int(decode_chunk_size)
            tile_num = int(tile_num)
            frames_chunk = int(frames_chunk)
            frame_overlap = int(frame_overlap)
            original_input_blend_strength = float(original_input_blend_strength)
            output_crf = int(output_crf)
            process_length = int(process_length)

            if num_inference_steps < 1 or tile_num < 1 or frames_chunk < 1:
                yield ("❌ Error: Invalid parameter values", 0, "0/0", "N/A", "N/A", "N/A", "N/A", "N/A",
                       gr.update(interactive=True), gr.update(interactive=False))
                return
        except ValueError:
            yield ("❌ Error: Please enter valid numeric values", 0, "0/0", "N/A", "N/A", "N/A", "N/A", "N/A",
                   gr.update(interactive=True), gr.update(interactive=False))
            return

        if not os.path.isdir(input_folder):
            yield (f"❌ Error: Input folder '{input_folder}' does not exist", 0, "0/0", "N/A", "N/A", "N/A", "N/A", "N/A",
                   gr.update(interactive=True), gr.update(interactive=False))
            return

        os.makedirs(output_folder, exist_ok=True)

        # Store parameters
        params = {
            'input_folder': input_folder,
            'output_folder': output_folder,
            'hires_blend_folder': hires_blend_folder,
            'num_inference_steps': num_inference_steps,
            'decode_chunk_size': decode_chunk_size,
            'tile_num': tile_num,
            'frames_chunk': frames_chunk,
            'frame_overlap': frame_overlap,
            'original_input_blend_strength': original_input_blend_strength,
            'output_crf': output_crf,
            'process_length': process_length,
            'offload_type': offload_type,
            'mask_initial_threshold': mask_initial_threshold,
            'mask_morph_kernel_size': mask_morph_kernel_size,
            'mask_dilate_kernel_size': mask_dilate_kernel_size,
            'mask_blur_kernel_size': mask_blur_kernel_size,
            'enable_post_inpainting_blend': enable_post_inpainting_blend,
            'enable_color_transfer': enable_color_transfer,
            'hf_token': hf_token
        }

        # Start processing thread
        self.stop_event.clear()
        # Clear the queue
        while not self.progress_queue.empty():
            try:
                self.progress_queue.get_nowait()
            except:
                break
                
        self.processing_thread = threading.Thread(
            target=self.process_batch,
            args=(params,),
            daemon=True
        )
        self.processing_thread.start()

        # Poll for progress updates
        import time
        last_status = "🚀 Processing started..."
        last_progress = 0
        last_batch = "0/0"
        last_video_name = "N/A"
        last_video_res = "N/A"
        last_video_frames = "N/A"

        # No timeout - wait for processing to complete naturally
        # For very long videos, timeout would cause premature exit
        
        while self.processing_thread.is_alive():
            # Check if stop was requested
            if self.stop_event.is_set():
                # Give thread a moment to clean up
                self.processing_thread.join(timeout=2.0)
                last_status = "⏹️ Processing stopped by user"
                break

            # Check queue for updates
            updated = False
            while not self.progress_queue.empty():
                try:
                    msg_type, msg_value = self.progress_queue.get_nowait()
                    updated = True
                    
                    if msg_type == "status":
                        last_status = msg_value
                    elif msg_type == "progress":
                        last_progress = msg_value
                    elif msg_type == "batch_progress":
                        last_batch = msg_value
                    elif msg_type == "video_name":
                        last_video_name = msg_value
                    elif msg_type == "video_res":
                        last_video_res = msg_value
                    elif msg_type == "video_frames":
                        last_video_frames = msg_value
                except:
                    break
            
            if updated:
                # Update progress bar
                
                
                # Yield current state
                yield (last_status, last_progress, last_batch, last_video_name, last_video_res,
                      last_video_frames,
                      gr.update(interactive=False), gr.update(interactive=True))
            
            time.sleep(0.1)  # Poll every 100ms
        
        # Final update after thread completes
        while not self.progress_queue.empty():
            try:
                msg_type, msg_value = self.progress_queue.get_nowait()
                if msg_type == "status":
                    last_status = msg_value
                elif msg_type == "progress":
                    last_progress = msg_value
                elif msg_type == "batch_progress":
                    last_batch = msg_value
                elif msg_type == "video_name":
                    last_video_name = msg_value
                elif msg_type == "video_res":
                    last_video_res = msg_value
                elif msg_type == "video_frames":
                    last_video_frames = msg_value
            except:
                break
        
        yield (last_status, last_progress, last_batch, last_video_name, last_video_res,
                last_video_frames,
                gr.update(interactive=True), gr.update(interactive=False))

    def stop_processing(self):
        """Stop processing"""
        self.stop_event.set()
        if self.pipeline:
            try:
                release_cuda_memory()
            except RuntimeError as e:
                logger.warning(f"Failed to clear CUDA cache: {e}")
        return ("⏹️ Stopping processing...", 0, "0/0", "N/A", "N/A", "N/A",
                gr.update(interactive=True), gr.update(interactive=False))

    def process_batch(self, params):
        """Main batch processing function"""
        try:
            # Load pipeline
            self.progress_queue.put(("status", "Loading inpainting pipeline..."))
            self.progress_queue.put(("logs", "Loading inpainting pipeline..."))
            
            # Use local weights loader (loads StereoCrafter UNet without subfolder)
            svd_path = os.path.abspath("./weights/stable-video-diffusion-img2vid-xt-1-1")
            unet_path = os.path.abspath("./weights/StereoCrafter")
            
            self.pipeline = load_inpainting_pipeline_local(
                svd_path=svd_path,
                unet_path=unet_path,
                device="cuda",
                dtype=torch.float16,
                offload_type=params['offload_type'],
                token=params['hf_token'] if params['hf_token'] else None
            )

            # Find videos
            input_videos = self.scan_for_videos(params['input_folder'])
            if not input_videos:
                self.progress_queue.put(("status", "No splatted videos found"))
                self.progress_queue.put(("batch_progress", "0/0"))
                return

            # Analyze videos for complexity and sort (simple videos first)
            video_metadata = []
            for video_path in input_videos:
                try:
                    info = get_video_stream_info(video_path)
                    width = info['width']
                    height = info['height']
                    duration = info['duration']
                    fps = info['fps']
                    num_frames = int(fps * duration)
                    resolution_factor = (width * height) / (1920 * 1080)
                    frame_factor = num_frames / 127
                    complexity = resolution_factor * frame_factor
                    video_metadata.append((video_path, complexity))
                except Exception as e:
                    logger.warning(f"Could not get metadata for {video_path}: {e}. Assuming low complexity.")
                    video_metadata.append((video_path, 1.0))

            # Sort by complexity ascending (simple videos processed first)
            video_metadata.sort(key=lambda x: x[1])
            input_videos = [v[0] for v in video_metadata]

            total_videos = len(input_videos)
            self.progress_queue.put(("status", f"Processing {total_videos} videos (sorted by complexity)..."))
            self.progress_queue.put(("logs", f"Processing {total_videos} videos (sorted by complexity)..."))
            self.progress_queue.put(("batch_progress", f"0/{total_videos}"))

            processed_count = 0

            # Process each video
            for idx, video_path in enumerate(input_videos):
                if self.stop_event.is_set():
                    self.progress_queue.put(("status", "Processing stopped by user"))
                    break

                basename = os.path.basename(video_path)
                self.progress_queue.put(("status", f"Processing {idx+1}/{total_videos}: {basename}"))
                self.progress_queue.put(("logs", f"Processing {idx+1}/{total_videos}: {basename}"))
                self.progress_queue.put(("batch_progress", f"{idx}/{total_videos}"))
                
                # Update video info
                self.progress_queue.put(("video_name", basename))
                self.progress_queue.put(("video_res", "Loading..."))
                self.progress_queue.put(("video_frames", "Loading..."))
                self.progress_queue.put(("progress", 0))

                success, hires_path = self.process_single_video(
                    pipeline=self.pipeline,
                    input_video_path=video_path,
                    params=params
                )

                if success:
                    processed_count += 1
                    msg = f"Completed {basename}"
                    if hires_path:
                        msg += " (+HiRes)"
                    self.progress_queue.put(("status", msg))
                else:
                    self.progress_queue.put(("status", f"Failed {basename}"))

                # Clear GPU memory between videos to prevent accumulation and fragmentation
                try:
                    torch.cuda.synchronize()
                    for _ in range(3):
                        torch.cuda.empty_cache()
                    gc.collect()
                    torch.cuda.reset_peak_memory_stats()
                    logger.debug(f"Cleared GPU memory after processing video {idx + 1}")
                except Exception as e:
                    logger.warning(f"Failed to clear memory after video {idx + 1}: {e}")

                self.progress_queue.put(("batch_progress", f"{idx+1}/{total_videos}"))

            if self.stop_event.is_set():
                logger.info("❌ Processing stopped.")
                self.progress_queue.put(("status", "❌ Processing stopped."))
            else:
                logger.info(f"✅ Batch completed! ({processed_count}/{total_videos} successful)")
                self.progress_queue.put(("status", f"✅ Batch completed! ({processed_count}/{total_videos} successful)"))
                self.progress_queue.put(("logs", f"✅ Batch completed! ({processed_count}/{total_videos} successful)"))
            self.progress_queue.put(("progress", 100))
            self.progress_queue.put(("batch_progress", f"{total_videos}/{total_videos}"))
            
            # Reset video info
            self.progress_queue.put(("video_name", "N/A"))
            self.progress_queue.put(("video_res", "N/A"))
            self.progress_queue.put(("video_frames", "N/A"))

        except Exception as e:
            logger.exception(f"Error during batch processing: {e}")
            self.progress_queue.put(("status", f"❌ Error: {str(e)}"))
        finally:
            if self.pipeline:
                try:
                    del self.pipeline
                    release_cuda_memory()
                except:
                    pass
                self.pipeline = None

    def process_single_video(self, pipeline, input_video_path, params):
        """Process a single video through the complete pipeline"""
        try:
            save_dir = params['output_folder']
            hires_blend_folder = params.get('hires_blend_folder', '')

            # 1. Setup & Hi-Res Detection
            base_video_name = os.path.basename(input_video_path)
            video_name_without_ext = os.path.splitext(base_video_name)[0]
            is_dual_input = video_name_without_ext.endswith("_splatted2")

            output_video_path, hires_data = self._setup_video_info_and_hires(
                input_video_path, save_dir, is_dual_input, hires_blend_folder
            )

            # Read sidecar if available (update params for this video specific)
            sidecar_params = self._read_sidecar_json(input_video_path)

            # Merge sidecar params with global params
            current_overlap = sidecar_params.get('frame_overlap', params['frame_overlap'])
            current_blend = sidecar_params.get('original_input_blend_strength', params['original_input_blend_strength'])
            current_crf = sidecar_params.get('output_crf', params['output_crf'])

            # 2. Input Preparation
            prepared_inputs = self._prepare_video_inputs(
                input_video_path=input_video_path,
                base_video_name=base_video_name,
                is_dual_input=is_dual_input,
                frames_chunk=params['frames_chunk'],
                tile_num=params['tile_num'],
                overlap=current_overlap,
                original_input_blend_strength=current_blend,
                process_length=params['process_length'],
                mask_params=params
            )

            if prepared_inputs is None:
                return False, None

            (frames_warpped_padded, frames_mask_padded, frames_left_original_cropped,
             num_frames_original, padded_H, padded_W, video_stream_info, fps,
             frames_warpped_original_unpadded, frames_mask_original_unpadded_processed) = prepared_inputs

            # 3. Inpainting Loop
            total_frames = num_frames_original
            frames_chunk = params['frames_chunk']
            overlap = current_overlap
            
            # Validate overlap vs frames_chunk to prevent zero-output chunks
            # Each chunk produces (frames_chunk - overlap) new frames, so we need frames_chunk > overlap
            if frames_chunk <= overlap:
                logger.warning(
                    f"frames_chunk ({frames_chunk}) must be greater than overlap ({overlap}) "
                    f"to produce new frames. Reducing overlap from {overlap} to {frames_chunk - 1}."
                )
                overlap = frames_chunk - 1
                current_overlap = overlap  # Update for later use
            
            stride = max(1, frames_chunk - overlap)
            total_chunks = (total_frames + stride - 1) // stride  # Calculate total chunks
            results = []
            previous_chunk_output = None

            logger.info(f"Processing {total_frames} frames in {total_chunks} chunks (chunk_size={frames_chunk}, overlap={overlap}, stride={stride})")

            for i in range(0, total_frames, stride):
                if self.stop_event.is_set():
                    return False, None

                # Slice frames - OPTIMIZED: Use .narrow() instead of indexing for zero-copy view
                end_idx = min(i + frames_chunk, total_frames)
                actual_len = end_idx - i
                
                # Use narrow() for zero-copy tensor view when possible
                input_slice = frames_warpped_padded.narrow(0, i, actual_len).clone()
                mask_slice = frames_mask_padded.narrow(0, i, actual_len).clone()

                # Pad only if necessary (last chunk with < 5 frames)
                if actual_len <= 4:
                    padding_needed = 6 - actual_len
                    # Pad with last frame repetition - more efficient
                    last_frame = input_slice[-1:]
                    last_mask = mask_slice[-1:]
                    input_slice = torch.cat([input_slice, last_frame.expand(padding_needed, -1, -1, -1)], dim=0)
                    mask_slice = torch.cat([mask_slice, last_mask.expand(padding_needed, -1, -1, -1)], dim=0)

                # Input blending - OPTIMIZED: In-place operations where possible
                if previous_chunk_output is not None and overlap > 0:
                    overlap_actual = min(overlap, input_slice.shape[0], previous_chunk_output.shape[0])
                    prev_overlap = previous_chunk_output[-overlap_actual:]

                    if current_blend > 0:
                        # Vectorized blending - already optimal
                        weights = torch.linspace(0.0, 1.0, overlap_actual, device=prev_overlap.device).view(-1, 1, 1, 1) * current_blend
                        input_slice[:overlap_actual] = (1 - weights) * prev_overlap + weights * input_slice[:overlap_actual]
                    else:
                        # Direct copy instead of blend
                        input_slice[:overlap_actual].copy_(prev_overlap)

                # 4. Inference - OPTIMIZED FOR HIGH-END GPU
                with torch.no_grad():
                    video_latents = spatial_tiled_process(
                        cond_frames=input_slice,
                        mask_frames=mask_slice,
                        process_func=pipeline,
                        tile_num=params['tile_num'],
                        spatial_n_compress=8,
                        min_guidance_scale=1.01,
                        max_guidance_scale=1.01,
                        decode_chunk_size=params['decode_chunk_size'],  # Use user setting
                        fps=7,
                        motion_bucket_id=127,
                        noise_aug_strength=0.0,
                        num_inference_steps=params['num_inference_steps']
                    )

                    video_latents = video_latents.unsqueeze(0)

                    # --- CRITICAL: Aggressive VRAM cleanup before VAE decode ---
                    # The UNet forward pass (spatial_tiled_process) has already consumed
                    # significant VRAM. We need to free intermediate tensors before decode.
                    del input_slice, mask_slice
                    torch.cuda.empty_cache()
                    gc.collect()

                    # Log VRAM status before decode for debugging
                    if torch.cuda.is_available():
                        vram_used_gb = torch.cuda.memory_allocated(0) / (1024**3)
                        vram_total_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                        vram_free_gb = vram_total_gb - vram_used_gb
                        logger.info(f"VRAM before VAE decode: {vram_used_gb:.1f} GB used / {vram_total_gb:.1f} GB total ({vram_free_gb:.1f} GB free)")

                    # Adaptive decode_chunk_size based on resolution
                    # The VAE Temporal Decoder is extremely memory intensive. 
                    # At 4K or higher, use 1. At 1080p, use 2. At 720p, use 4.
                    user_decode_chunk = params['decode_chunk_size']
                    frame_h = video_latents.shape[3] * 8  # Latent height * 8 = actual pixel height
                    
                    if frame_h >= 2000:  # 4K or higher
                        adaptive_decode_chunk = 1
                    elif frame_h >= 1000:  # 1080p range
                        adaptive_decode_chunk = min(2, user_decode_chunk)
                    else:  # 720p or lower
                        adaptive_decode_chunk = min(4, user_decode_chunk)

                    if adaptive_decode_chunk < user_decode_chunk:
                        logger.info(
                            f"Resolution {frame_h}px requires reducing decode_chunk_size "
                            f"from {user_decode_chunk} to {adaptive_decode_chunk} to avoid OOM"
                        )

                    # Decode - Use adaptive chunk size for 4K safety
                    decoded_frames = pipeline.decode_latents(
                        video_latents,
                        num_frames=video_latents.shape[1],
                        decode_chunk_size=adaptive_decode_chunk
                    )

                    # Free latent tensor after decode
                    del video_latents
                    torch.cuda.empty_cache()

                # Convert to tensor [T, C, H, W] - OPTIMIZED: Skip PIL conversion
                # decoded_frames shape: [batch, channels, frames, height, width]
                # Extract frames directly from tensor (much faster than PIL round-trip)
                # VAE output is in [-1, 1] range, normalize to [0, 1]
                chunk_generated = decoded_frames[0].permute(1, 0, 2, 3)  # Keep on GPU! [frames, channels, height, width]
                chunk_generated = (chunk_generated + 1) / 2  # Normalize from [-1, 1] to [0, 1]
                chunk_generated = chunk_generated.clamp(0, 1)  # Ensure valid range

                # Handle output collection - OPTIMIZED: Pre-allocate list capacity
                if i == 0:
                    results.append(chunk_generated[:actual_len])
                else:
                    # Skip overlap frames from current chunk
                    results.append(chunk_generated[overlap:actual_len])

                previous_chunk_output = chunk_generated

                # Update progress - calculate based on frames processed so far
                frames_processed = min(i + actual_len, total_frames)
                current_percent = int((frames_processed / total_frames) * 90)  # 0-90% for inference
                chunk_num = min(i // stride + 1, total_chunks)
                self.progress_queue.put(("progress", current_percent))
                self.progress_queue.put(("status", f"Chunk {chunk_num}/{total_chunks} ({current_percent}%)"))

            # Concatenate results - OPTIMIZED: Use more efficient concatenation
            if not results:
                return False, None

            # Pre-calculate total output size for efficient allocation
            frames_output = torch.cat(results, dim=0)  # Keep on GPU initially

            # Crop to original size - OPTIMIZED: Use narrow for zero-copy view
            frames_output_final = frames_output.narrow(0, 0, num_frames_original).narrow(2, 0, padded_H).narrow(3, 0, padded_W)
            
            # Only transfer to CPU once at the end if needed for finalization
            # frames_output_final stays on GPU for finalization

            # 5. Finalization (Color Transfer, Blending, Hi-Res)
            self.progress_queue.put(("status", f"Finalizing {base_video_name}..."))
            self.progress_queue.put(("logs", f"Finalizing {base_video_name}..."))
            final_output = self._finalize_output_frames(
                inpainted_frames=frames_output_final,
                mask_frames=frames_mask_original_unpadded_processed,
                original_warped_frames=frames_warpped_original_unpadded,
                original_left_frames=frames_left_original_cropped,
                hires_data=hires_data,
                base_video_name=base_video_name,
                is_dual_input=is_dual_input,
                params=params
            )
            self.progress_queue.put(("progress", 90))  # 90% after finalization

            if final_output is None:
                return False, None

            # 6. Encoding - OPTIMIZED: Use NVENC GPU encoding
            self.progress_queue.put(("status", f"Encoding {base_video_name}..."))
            self.progress_queue.put(("logs", f"Encoding {base_video_name}..."))
            self.progress_queue.put(("progress", 92))  # 92% at start of encoding
            
            try:
                # Move final output to CPU first to free GPU memory before the encoding loop.
                # Without this, a 4K tensor (e.g. 165 frames ~ 8 GB float16) stays on GPU
                # while the CPU frames list simultaneously grows, causing OOM on smaller cards.
                final_output_cpu = final_output.cpu()
                del final_output
                torch.cuda.empty_cache()
                gc.collect()
                
                # Encode directly using FFmpeg with NVENC (much faster than PNG intermediate)
                # Prepare frames for encoding
                frames_to_encode = []
                total_frames_to_encode = len(final_output_cpu)
                for idx, frame in enumerate(final_output_cpu):
                    if self.stop_event.is_set():
                        return False, None
                    # Convert from [C,H,W] float32 [0,1] to uint8 [0,255]
                    frame_np = (frame.permute(1, 2, 0).numpy() * 255.0).astype(np.uint8)
                    frames_to_encode.append(frame_np)
                    
                    # Update progress during encoding (every 10 frames)
                    if (idx + 1) % 10 == 0:
                        enc_progress = 92 + int((idx + 1) / total_frames_to_encode * 8)
                        self.progress_queue.put(("progress", min(99, enc_progress)))
                
                # Free CPU tensor once frames are collected (helps lower-RAM systems)
                del final_output_cpu
                gc.collect()
                
                # Use NVENC encoding (GPU accelerated)
                original_cuda_flag = sc_util.CUDA_AVAILABLE
                sc_util.CUDA_AVAILABLE = True  # Enable CUDA for NVENC
                try:
                    encode_frames_to_mp4(
                        temp_png_dir=None,  # Skip PNG saving
                        final_output_mp4_path=output_video_path,
                        fps=fps,
                        total_output_frames=total_frames_to_encode,
                        video_stream_info=video_stream_info,
                        user_output_crf=current_crf,
                        output_sidecar_ext=".spsidecar",
                        frames_list=frames_to_encode  # Pass frames directly
                    )
                finally:
                    sc_util.CUDA_AVAILABLE = original_cuda_flag
            except Exception as e:
                logger.exception(f"Encoding failed: {e}")
                return False, None
            
            self.progress_queue.put(("progress", 100))  # 100% complete

            return True, hires_data.get('hires_video_path')

        except Exception as e:
            logger.exception(f"Error processing single video {input_video_path}: {e}")
            return False, None

    # ==================== HELPER METHODS ====================

    def _prepare_video_inputs(self, input_video_path, base_video_name, is_dual_input, 
                             frames_chunk, tile_num, overlap, original_input_blend_strength, 
                             process_length, mask_params):
        """Prepare video frames, masks and padding for processing"""
        try:
            # Load video
            vr = VideoReader(input_video_path, ctx=cpu(0))
            # Prefer robust count (fixes frame mismatch with DepthCrafter-produced assets)
            total_frames = len(vr)
            try:
                from core.common.video_io import get_video_stream_info as core_gsi
                info = core_gsi(input_video_path)
                if info:
                    for k in ("nb_frames", "nb_read_frames"):
                        if info.get(k):
                            try:
                                n = int(float(info[k]))
                                if n > 0:
                                    total_frames = n
                                    break
                            except Exception:
                                pass
            except Exception:
                pass

            fps = vr.get_avg_fps()

            if process_length > 0:
                total_frames = min(process_length, total_frames)

            # Read all frames (returns numpy array normalized to 0-1 from read_video_frames_decord)
            frames, fps, orig_h, orig_w, proc_h, proc_w, video_stream_info = read_video_frames_decord(input_video_path, total_frames)
            # frames is [T, H, W, C] float32 0-1

            frames = torch.from_numpy(frames).permute(0, 3, 1, 2) # Convert to tensor [T,C,H,W]
            
            # Ensure we only have 3 channels (RGB), not 4 (RGBA)
            if frames.shape[1] == 4:
                logger.warning(f"Input video has 4 channels (RGBA), dropping alpha channel to use RGB only")
                frames = frames[:, :3, :, :]  # Drop alpha channel
            elif frames.shape[1] != 3:
                logger.error(f"Input video has {frames.shape[1]} channels, expected 3 (RGB) or 4 (RGBA)")
                raise ValueError(f"Invalid channel count: {frames.shape[1]}, expected 3 or 4")

            # --- GUI ALIGNMENT: Quantize to uint8 (0-255) immediately ---
            # The GUI performs this step: frames = (frames * 255).to(torch.uint8)
            # We must replicate this to ensure identical "artifacts" and processing behavior.
            frames = (frames * 255.0).clamp(0, 255).to(torch.uint8)
            
            # --- Dimension Divisibility Check and Resizing (if needed) ---
            _, _, total_h_raw_input_before_resize, total_w_raw_input_before_resize = frames.shape
            required_divisor = 16

            new_h = total_h_raw_input_before_resize
            new_w = total_w_raw_input_before_resize

            if new_h % required_divisor != 0:
                new_h = (new_h // required_divisor + 1) * required_divisor
                logger.warning(f"Video height {total_h_raw_input_before_resize} is not divisible by {required_divisor}. Resizing to {new_h}.")

            if new_w % required_divisor != 0:
                new_w = (new_w // required_divisor + 1) * required_divisor
                logger.warning(f"Video width {total_w_raw_input_before_resize} is not divisible by {required_divisor}. Resizing to {new_w}.")

            if new_h != total_h_raw_input_before_resize or new_w != total_w_raw_input_before_resize:
                if frames.shape[0] > 0:
                    # F.interpolate handles uint8 inputs (often by casting to float internally or returning float)
                    # To be essentially 1:1 with GUI, we call it on the current 'frames' tensor.
                    # Note: If frames is uint8, F.interpolate might return float depending on PyTorch version/backend.
                    frames = F.interpolate(frames.float(), size=(new_h, new_w), mode='bicubic', align_corners=False)
                    
                    # If interpolated to float, we should ideally cast back to uint8 if we strictly follow "keep it uint8" philosophy,
                    # BUT the GUI code (line 915) does: frames = F.interpolate(...) and does NOT explicitly cast back.
                    # However, subsequent lines in GUI treat it as if it might be uint8 or float-0-255.
                    # For safety and strict alignment with "quantized" look, we should enforce uint8.
                    frames = frames.clamp(0, 255).to(torch.uint8)
                    
                    logger.info(f"Frames resized from {total_h_raw_input_before_resize}x{total_w_raw_input_before_resize} to {new_h}x{new_w}.")
                else:
                    logger.warning("Attempted to resize empty frames tensor. Skipping resize.")
            
            # --- Update current dimensions after potential resize ---
            T, C, H, W = frames.shape

            # Split logic
            if is_dual_input:
                # Left=Mask, Right=Warped
                # Mask needs processing (it's grayscale usually)
                half_w = W // 2
                mask_frames = frames[:, :, :, :half_w]
                warped_frames = frames[:, :, :, half_w:]
                left_frames = warped_frames # No true left view in dual
            else:
                # Quad: TL=Source, TR=Depth, BL=Mask, BR=Warped
                half_h = H // 2
                half_w = W // 2
                left_frames = frames[:, :, :half_h, :half_w]
                mask_frames = frames[:, :, half_h:, :half_w]
                warped_frames = frames[:, :, half_h:, half_w:]

                H, W = half_h, half_w

            # --- GUI ALIGNMENT: Normalize left_frames immediately ---
            # The GUI normalizes this crop here. We must do the same to ensure valid float 0-1 for SBS output.
            if left_frames is not None:
                left_frames = left_frames.float() / 255.0
            
            # Mask Processing (Binarize, Dilate, Blur)
            # Convert to grayscale using OpenCV (matches GUI method exactly)
            processed_masks_grayscale = []
            for t in range(mask_frames.shape[0]):
                # frames is uint8 (0-255), so mask_frames is also uint8 [C, H, W]
                # Permute to [H, W, C] for OpenCV
                frame_nhwc = mask_frames[t].permute(1, 2, 0).cpu().numpy()
                
                # Ensure it is uint8 (should be already, but safety first if resize made it float coverage)
                if frame_nhwc.dtype != np.uint8:
                    frame_nhwc = frame_nhwc.astype(np.uint8)
                
                # Use OpenCV's proper RGB to grayscale conversion (luminance weights)
                frame_gray = cv2.cvtColor(frame_nhwc, cv2.COLOR_RGB2GRAY)
                
                # Convert back to float [0-1] tensor and add channel dimension
                frame_tensor = torch.from_numpy(frame_gray).float() / 255.0
                frame_tensor = frame_tensor.unsqueeze(0)  # Add channel dim [1, H, W]
                processed_masks_grayscale.append(frame_tensor)
            
            mask_frames = torch.stack(processed_masks_grayscale).to(frames.device)
            
            # Only apply mask processing if enable_post_inpainting_blend is True
            if mask_params.get('enable_post_inpainting_blend', False):
                # Binarize
                mask_frames = (mask_frames > mask_params['mask_initial_threshold']).float()

                # Apply Dilate
                k_d = int(mask_params['mask_dilate_kernel_size'])
                if k_d > 0:
                    k_d = k_d if k_d % 2 == 1 else k_d + 1
                    mask_frames = F.max_pool2d(mask_frames, kernel_size=k_d, stride=1, padding=k_d//2)

                # Apply Blur
                k_b = int(mask_params['mask_blur_kernel_size'])
                if k_b > 0:
                    mask_frames = self._apply_gaussian_blur(mask_frames, k_b)

            frames_mask_processed = mask_frames

            # Calculate Padding
            pad_h = (16 - H % 16) % 16
            pad_w = (16 - W % 16) % 16

            if pad_h > 0 or pad_w > 0:
                # Convert to float for padding and model input
                warped_padded = F.pad(warped_frames.float() / 255.0, (0, pad_w, 0, pad_h), mode='constant', value=0)
                mask_padded = F.pad(frames_mask_processed, (0, pad_w, 0, pad_h), mode='constant', value=0)
            else:
                # Convert to float for model input
                warped_padded = warped_frames.float() / 255.0
                mask_padded = frames_mask_processed

            # Info extraction
            video_stream_info = get_video_stream_info(input_video_path)

            # Send video info update
            self.progress_queue.put(("video_res", f"{W}x{H}"))
            self.progress_queue.put(("video_frames", str(T)))

            # Clean up VideoReader
            del vr

            return (warped_padded, mask_padded, left_frames,
                    T, H, W, video_stream_info, fps,
                    warped_frames, frames_mask_processed)

        except Exception as e:
            logger.error(f"Error preparing video input: {e}")
            return None

    def _finalize_output_frames(self, inpainted_frames, mask_frames, original_warped_frames, 
                               original_left_frames, hires_data, base_video_name, is_dual_input, params):
        """Finalize frames: blending, color transfer, hi-res application"""
        try:
            frames_output_final = inpainted_frames
            frames_mask_processed = mask_frames
            frames_warpped_original_unpadded = original_warped_frames # This is uint8 from _prepare_video_inputs
            frames_left_original_cropped = original_left_frames # This is uint8 from _prepare_video_inputs

            # --- Hi-Res Blending Logic ---
            if hires_data.get("is_hires_blend_enabled"):
                hires_H, hires_W = hires_data["hires_H"], hires_data["hires_W"]
                num_frames_original = frames_output_final.shape[0]
                hires_video_path = hires_data["hires_video_path"]

                logger.info(f"Starting Hi-Res Blending at {hires_W}x{hires_H}...")

                hires_reader = VideoReader(hires_video_path, ctx=cpu(0))
                # Process in smaller chunks to avoid CPU memory exhaustion
                hires_chunk_size = 5  # Process 5 frames at a time for 4K

                # Read first chunk to determine actual hires video dimensions
                first_indices = list(range(min(hires_chunk_size, num_frames_original)))
                first_hires_np = hires_reader.get_batch(first_indices).asnumpy()
                first_hires_torch = torch.from_numpy(first_hires_np).permute(0, 3, 1, 2).float()

                # Get actual dimensions from hires video
                full_h, full_w = first_hires_torch.shape[2], first_hires_torch.shape[3]

                # For 4-panel: full_h is 2*panel_h, full_w is 2*panel_w
                # For 2-panel: full_h is panel_h, full_w is 2*panel_w
                # hires_H and hires_W are already the individual panel sizes
                # So left/warped panels should match hires_H x hires_W directly
                warped_h, warped_w = hires_H, hires_W
                left_h, left_w = hires_H, hires_W

                # Pre-allocate output tensors on CPU with correct dimensions
                frames_output_final_hires = torch.empty(
                    (num_frames_original, frames_output_final.shape[1], hires_H, hires_W),
                    dtype=torch.float32, device='cpu'
                )
                frames_mask_processed_hires = torch.empty(
                    (num_frames_original, frames_mask_processed.shape[1], hires_H, hires_W),
                    dtype=torch.float32, device='cpu'
                )
                frames_warped_hires = torch.empty(
                    (num_frames_original, 3, warped_h, warped_w),
                    dtype=torch.float32, device='cpu'
                )
                frames_left_hires = None
                if not is_dual_input:
                    frames_left_hires = torch.empty(
                        (num_frames_original, 3, left_h, left_w),
                        dtype=torch.float32, device='cpu'
                    )

                def process_hires_mask(raw_mask_chunk, p_dilate, p_blur, p_thresh):
                    import cv2
                    import numpy as np
                    processed_masks = []
                    for t in range(raw_mask_chunk.shape[0]):
                        mask_np = raw_mask_chunk[t].permute(1, 2, 0).numpy()
                        mask_np_uint8 = np.clip(mask_np * 255, 0, 255).astype(np.uint8)
                        
                        if mask_np_uint8.shape[2] == 3:
                            mask_gray = cv2.cvtColor(mask_np_uint8, cv2.COLOR_RGB2GRAY)
                        else:
                            mask_gray = mask_np_uint8.squeeze(-1)
                            
                        _, binary_mask = cv2.threshold(mask_gray, int(p_thresh * 255), 255, cv2.THRESH_BINARY)
                        
                        if p_dilate > 0:
                            dilate_kernel = np.ones((int(p_dilate), int(p_dilate)), np.uint8)
                            binary_mask = cv2.dilate(binary_mask, dilate_kernel, iterations=1)
                            
                        if p_blur > 0:
                            blur_size = int(p_blur)
                            if blur_size % 2 == 0: blur_size += 1
                            binary_mask = cv2.GaussianBlur(binary_mask, (blur_size, blur_size), 0)
                            
                        processed_masks.append(torch.from_numpy(binary_mask).unsqueeze(0).float() / 255.0)
                    return torch.stack(processed_masks, dim=0)

                # Calculate scaling factor to ensure the mask parameters are proportional at 4K
                input_W = frames_output_final.shape[3]
                hires_scale = hires_W / input_W if input_W > 0 else 1.0
                
                scaled_dilate = max(0, int(round(params['mask_dilate_kernel_size'] * hires_scale)))
                scaled_blur = max(0, int(round(params['mask_blur_kernel_size'] * hires_scale)))

                # Process first chunk (already loaded)
                inpainted_chunk = frames_output_final[:len(first_indices)].cpu()
                inpainted_chunk_hires = F.interpolate(inpainted_chunk, size=(hires_H, hires_W), mode='bicubic', align_corners=False)

                if is_dual_input:
                    hires_warped_chunk = first_hires_torch[:, :, :, left_w:].float() / 255.0
                    hires_raw_mask = first_hires_torch[:, :, :, :left_w].float() / 255.0
                else:
                    hires_left_chunk = first_hires_torch[:, :, :left_h, :left_w].float() / 255.0
                    hires_warped_chunk = first_hires_torch[:, :, warped_h:, warped_w:].float() / 255.0
                    hires_raw_mask = first_hires_torch[:, :, left_h:, :left_w].float() / 255.0
                
                mask_chunk_hires = process_hires_mask(hires_raw_mask, scaled_dilate, scaled_blur, params['mask_initial_threshold'])

                frames_output_final_hires[:len(first_indices)] = inpainted_chunk_hires
                frames_mask_processed_hires[:len(first_indices)] = mask_chunk_hires
                frames_warped_hires[:len(first_indices)] = hires_warped_chunk
                if not is_dual_input:
                    frames_left_hires[:len(first_indices)] = hires_left_chunk

                del first_hires_np, first_hires_torch, inpainted_chunk, hires_raw_mask
                del inpainted_chunk_hires, mask_chunk_hires, hires_warped_chunk
                if not is_dual_input:
                    del hires_left_chunk

                # Process remaining chunks
                for i in range(hires_chunk_size, num_frames_original, hires_chunk_size):
                    start_idx, end_idx = i, min(i + hires_chunk_size, num_frames_original)
                    frame_indices = list(range(start_idx, end_idx))
                    if not frame_indices:
                        break
                    
                    inpainted_chunk = frames_output_final[start_idx:end_idx].cpu()
                    inpainted_chunk_hires = F.interpolate(inpainted_chunk, size=(hires_H, hires_W), mode='bicubic', align_corners=False)

                    hires_frames_np = hires_reader.get_batch(frame_indices).asnumpy()
                    hires_frames_torch = torch.from_numpy(hires_frames_np).permute(0, 3, 1, 2).float()

                    if is_dual_input:
                        hires_warped_chunk = hires_frames_torch[:, :, :, left_w:].float() / 255.0
                        hires_raw_mask = hires_frames_torch[:, :, :, :left_w].float() / 255.0
                    else:
                        hires_left_chunk = hires_frames_torch[:, :, :left_h, :left_w].float() / 255.0
                        hires_warped_chunk = hires_frames_torch[:, :, warped_h:, warped_w:].float() / 255.0
                        hires_raw_mask = hires_frames_torch[:, :, left_h:, :left_w].float() / 255.0

                    mask_chunk_hires = process_hires_mask(hires_raw_mask, scaled_dilate, scaled_blur, params['mask_initial_threshold'])

                    frames_output_final_hires[start_idx:end_idx] = inpainted_chunk_hires
                    frames_mask_processed_hires[start_idx:end_idx] = mask_chunk_hires
                    frames_warped_hires[start_idx:end_idx] = hires_warped_chunk
                    if not is_dual_input:
                        frames_left_hires[start_idx:end_idx] = hires_left_chunk

                    del inpainted_chunk, hires_raw_mask, inpainted_chunk_hires, mask_chunk_hires
                    del hires_frames_np, hires_frames_torch, hires_warped_chunk
                    if not is_dual_input:
                        del hires_left_chunk

                    if end_idx % 10 == 0 or end_idx == num_frames_original:
                        logger.info(f"  Hi-Res blending: {end_idx}/{num_frames_original} frames processed")

                # Replace original tensors with Hi-Res versions
                frames_output_final = frames_output_final_hires
                frames_mask_processed = frames_mask_processed_hires
                frames_warpped_original_unpadded = frames_warped_hires
                if not is_dual_input:
                    frames_left_original_cropped = frames_left_hires

                del hires_reader
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                import gc
                gc.collect()
                logger.info(f"Hi-Res blending complete. VRAM: {torch.cuda.memory_allocated(0) / 1024**3:.1f} GB used" if torch.cuda.is_available() else "Hi-Res blending complete.")
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

            # --- VRAM OPTIMIZATION: Chunked processing for Finalization ---
            # Moves massive 4K tensor to CPU and processes in 10-frame chunks
            frames_output_final_cpu = frames_output_final.cpu()
            del frames_output_final
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                
            chunk_size = 10
            num_frames = frames_output_final_cpu.shape[0]
            final_chunks = []
            
            for i in range(0, num_frames, chunk_size):
                end_i = min(i + chunk_size, num_frames)
                
                # All processing stays on CPU to save VRAM (Color Transfer requires CPU anyway)
                chunk_output = frames_output_final_cpu[i:end_i]
                
                # --- Color Transfer ---
                if params['enable_color_transfer']:
                    warped_for_ct = frames_warpped_original_unpadded[i:end_i].float() / 255.0 if frames_warpped_original_unpadded.dtype == torch.uint8 else frames_warpped_original_unpadded[i:end_i]
                    if frames_left_original_cropped is not None:
                        left_for_ct = frames_left_original_cropped[i:end_i].float() / 255.0 if frames_left_original_cropped.dtype == torch.uint8 else frames_left_original_cropped[i:end_i]
                    else:
                        left_for_ct = None

                    if is_dual_input:
                        warped_frames_base = warped_for_ct.cpu()
                        processed_mask = frames_mask_processed[i:end_i].cpu()
                        chunk_reference = self._apply_directional_dilation(
                            frame_chunk=warped_frames_base, mask_chunk=processed_mask
                        )
                    else:
                        chunk_reference = left_for_ct.cpu() if left_for_ct is not None else None

                    if chunk_reference is not None:
                        target_H, target_W = chunk_output.shape[2], chunk_output.shape[3]
                        ref_resized = F.interpolate(chunk_reference, size=(target_H, target_W), mode='bilinear', align_corners=False)
                        
                        ref_np = ref_resized.permute(0, 2, 3, 1).numpy()
                        tgt_np = chunk_output.permute(0, 2, 3, 1).numpy()
                        
                        ref_np_uint8 = np.clip(ref_np * 255, 0, 255).astype(np.uint8)
                        tgt_np_uint8 = np.clip(tgt_np * 255, 0, 255).astype(np.uint8)
                        adjusted = np.empty_like(ref_np_uint8)
                        
                        for t in range(ref_np_uint8.shape[0]):
                            ref_lab = cv2.cvtColor(ref_np_uint8[t], cv2.COLOR_RGB2LAB)
                            tgt_lab = cv2.cvtColor(tgt_np_uint8[t], cv2.COLOR_RGB2LAB)
                            s_m, s_s = cv2.meanStdDev(ref_lab)
                            t_m, t_s = cv2.meanStdDev(tgt_lab)
                            s_m, s_s = s_m.flatten(), s_s.flatten()
                            t_m, t_s = t_m.flatten(), t_s.flatten()
                            s_s = np.clip(s_s, 1e-6, None)
                            t_s = np.clip(t_s, 1e-6, None)
                            tgt_lab_f = tgt_lab.astype(np.float32)
                            for c in range(3):
                                tgt_lab_f[:, :, c] = (tgt_lab_f[:, :, c] - t_m[c]) / t_s[c] * s_s[c] + s_m[c]
                            tgt_lab_u = np.clip(tgt_lab_f, 0, 255).astype(np.uint8)
                            adjusted[t] = cv2.cvtColor(tgt_lab_u, cv2.COLOR_LAB2RGB)
                            
                        chunk_output = torch.from_numpy(adjusted).permute(0, 3, 1, 2).float() / 255.0

                # --- Post-Inpainting Blend ---
                if params['enable_post_inpainting_blend']:
                    chunk_mask_cpu = frames_mask_processed[i:end_i].cpu()
                    if chunk_mask_cpu.shape[1] != 1: 
                        chunk_mask_cpu = chunk_mask_cpu.mean(dim=1, keepdim=True)

                    chunk_orig = frames_warpped_original_unpadded[i:end_i].cpu()
                    chunk_orig_cpu = chunk_orig.float() / 255.0 if chunk_orig.dtype == torch.uint8 else chunk_orig
                    
                    if chunk_output.shape == chunk_orig_cpu.shape:
                        chunk_output = chunk_orig_cpu * (1 - chunk_mask_cpu) + chunk_output * chunk_mask_cpu

                # --- Final Concatenation ---
                if not is_dual_input:
                    if frames_left_original_cropped is not None:
                        chunk_left = frames_left_original_cropped[i:end_i].cpu()
                        chunk_left_norm = chunk_left.float() / 255.0 if chunk_left.dtype == torch.uint8 else chunk_left
                        if chunk_left_norm.shape[-2:] != chunk_output.shape[-2:]:
                            chunk_left_norm = F.interpolate(chunk_left_norm, size=chunk_output.shape[-2:], mode='bilinear', align_corners=False)
                        chunk_output = torch.cat([chunk_left_norm, chunk_output], dim=3)
                        
                final_chunks.append(chunk_output)
                
            return torch.cat(final_chunks, dim=0)

            return None

        except Exception as e:
            logger.error(f"Error finalization: {e}")
            logger.exception("Full traceback:")
            return None

    def _setup_video_info_and_hires(self, input_video_path, save_dir, is_dual_input, hires_blend_folder):
        """Determine output path and find hi-res match"""
        base = os.path.basename(input_video_path)
        name_no_ext = os.path.splitext(base)[0]

        # Determine output filename
        suffix = "_inpainted"
        out_name = name_no_ext.replace("_splatted2", "").replace("_splatted4", "")
        out_path = os.path.join(save_dir, f"{out_name}{suffix}.mp4")

        # Determine input folder from path for the check
        input_folder = os.path.dirname(input_video_path)

        hires_info = {"is_hires_blend_enabled": False}
        hires_path = self._find_high_res_match(input_video_path, input_folder, hires_blend_folder)

        if hires_path:
            try:
                # Read Hi-Res dimensions
                vr_hi = VideoReader(hires_path, ctx=cpu(0))
                # H, W, since decord format is usually HWC in get_batch, but check shape
                # get_batch returns [Batch, H, W, C]
                shape = vr_hi.get_batch([0]).shape
                hires_H, hires_W = shape[1], shape[2]

                # Handling Quad/Dual for actual frame size vs canvas size
                if is_dual_input:
                    # In Dual, width is 2x view width
                    hires_W_view = hires_W // 2
                    hires_H_view = hires_H
                    # We render view size usually.
                    hires_W = hires_W_view 
                else:
                     # Quad
                    hires_W = hires_W // 2
                    hires_H = hires_H // 2

                hires_info = {
                    "is_hires_blend_enabled": True,
                    "hires_video_path": hires_path,
                    "hires_H": hires_H,
                    "hires_W": hires_W
                }

                # Clean up VideoReader
                del vr_hi

            except Exception as e:
                logger.error(f"Failed to load Hi-Res info: {e}")
                hires_info = {"is_hires_blend_enabled": False}

        return out_path, hires_info

    def _find_high_res_match(self, low_res_video_path, input_folder, hires_blend_folder) -> Optional[str]:
        """Find matching hi-res video"""
        if not hires_blend_folder or not os.path.exists(hires_blend_folder):
            return None

        if os.path.normpath(input_folder) == os.path.normpath(hires_blend_folder):
            return None

        low_res_filename = os.path.basename(low_res_video_path)
        name_no_ext = os.path.splitext(low_res_filename)[0]

        splatted_suffix = None
        if name_no_ext.endswith('_splatted2'):
            splatted_suffix = '_splatted2.mp4'
            splatted_core = '_splatted2'
        elif name_no_ext.endswith('_splatted4'):
            splatted_suffix = '_splatted4.mp4'
            splatted_core = '_splatted4'
        else:
            return None

        # Strip resolution and suffix
        splat_index = name_no_ext.rfind(splatted_core)
        if splat_index == -1: return None

        name_core = name_no_ext[:splat_index]
        last_underscore = name_core.rfind('_')
        if last_underscore != -1:
            base_pattern = name_core[:last_underscore]
        else:
            base_pattern = name_core

        if not base_pattern: return None

        search_pattern = os.path.join(hires_blend_folder, f"{base_pattern}_*{splatted_suffix}")
        matches = glob.glob(search_pattern)

        matches = [m for m in matches if os.path.normpath(m) != os.path.normpath(low_res_video_path)]

        if not matches: return None

        # Check resolution
        hires_path = matches[0]
        try:
            vr_lo = VideoReader(low_res_video_path, ctx=cpu(0))
            lo_w = vr_lo.get_batch([0]).shape[2]

            vr_hi = VideoReader(hires_path, ctx=cpu(0))
            hi_w = vr_hi.get_batch([0]).shape[2]

            if hi_w <= lo_w:
                del vr_lo, vr_hi
                return None
            del vr_lo, vr_hi
            return hires_path
        except:
            return None

    def _read_sidecar_json(self, video_path):
        """Read .spsidecar file if exists"""
        json_path = os.path.splitext(video_path)[0] + ".spsidecar"
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def _apply_color_transfer(self, source_frame: torch.Tensor, target_frame: torch.Tensor) -> torch.Tensor:
        """Apply color transfer using LAB"""
        try:
            # Ensure tensors are on CPU and convert to numpy arrays in HWC format
            source_np = source_frame.permute(1, 2, 0).numpy()  # [H, W, C]
            target_np = target_frame.permute(1, 2, 0).numpy()  # [H, W, C]

            # Scale from [0, 1] to [0, 255] and convert to uint8
            source_np_uint8 = (np.clip(source_np, 0.0, 1.0) * 255).astype(np.uint8)
            target_np_uint8 = (np.clip(target_np, 0.0, 1.0) * 255).astype(np.uint8)

            # Convert to LAB color space
            source_lab = cv2.cvtColor(source_np_uint8, cv2.COLOR_RGB2LAB)
            target_lab = cv2.cvtColor(target_np_uint8, cv2.COLOR_RGB2LAB)

            # Compute mean and standard deviation
            src_mean, src_std = cv2.meanStdDev(source_lab)
            tgt_mean, tgt_std = cv2.meanStdDev(target_lab)

            src_mean, src_std = src_mean.flatten(), src_std.flatten()
            tgt_mean, tgt_std = tgt_mean.flatten(), tgt_std.flatten()

            src_std = np.clip(src_std, 1e-6, None)
            tgt_std = np.clip(tgt_std, 1e-6, None)

            # Normalize target LAB channels
            target_lab_float = target_lab.astype(np.float32)
            for i in range(3):
                target_lab_float[:, :, i] = (target_lab_float[:, :, i] - tgt_mean[i]) / tgt_std[i] * src_std[i] + src_mean[i]

            # Clip and convert back
            target_lab_float = np.clip(target_lab_float, 0, 255)
            adjusted_lab_uint8 = target_lab_float.astype(np.uint8)
            adjusted_rgb = cv2.cvtColor(adjusted_lab_uint8, cv2.COLOR_LAB2RGB)

            return torch.from_numpy(adjusted_rgb).permute(2, 0, 1).float() / 255.0
        except Exception as e:
            logger.error(f"Error during color transfer: {e}")
            return target_frame

    def _apply_directional_dilation(self, frame_chunk: torch.Tensor, mask_chunk: torch.Tensor) -> torch.Tensor:
        """Fills occluded areas by dilating from right to create clean reference"""
        try:
            if frame_chunk.shape[0] != mask_chunk.shape[0]:
                return frame_chunk

            filled_frames_list = []
            device = frame_chunk.device

            for t in range(frame_chunk.shape[0]):
                frame_np = (frame_chunk[t].permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
                mask_np = (mask_chunk[t].squeeze(0).cpu().numpy() * 255).astype(np.uint8)

                # Inpaint using Telea
                inpainted = cv2.inpaint(frame_np, mask_np, 3, cv2.INPAINT_TELEA)
                filled_tensor = torch.from_numpy(inpainted).permute(2, 0, 1).float() / 255.0
                filled_frames_list.append(filled_tensor.to(device))

            return torch.stack(filled_frames_list)
        except Exception as e:
            logger.error(f"Error during directional dilation: {e}")
            return frame_chunk

    def _apply_gaussian_blur(self, mask: torch.Tensor, kernel_size: int) -> torch.Tensor:
        """Apply Gaussian blur to mask"""
        if kernel_size <= 0:
            return mask

        kernel_val = kernel_size if kernel_size % 2 == 1 else kernel_size + 1
        if kernel_val < 3:
            kernel_val = 3

        sigma = kernel_val / 6.0
        if sigma < 0.1:
            sigma = 0.1

        kernel = self._create_1d_gaussian_kernel(kernel_val, sigma).to(mask.device)
        kernel_x = kernel.view(1, 1, 1, kernel_val)
        kernel_y = kernel.view(1, 1, kernel_val, 1)

        padding_x = kernel_val // 2
        blurred_mask = F.conv2d(mask, kernel_x, padding=(0, padding_x), groups=mask.shape[1])

        padding_y = kernel_val // 2
        blurred_mask = F.conv2d(blurred_mask, kernel_y, padding=(padding_y, 0), groups=mask.shape[1])

        return torch.clamp(blurred_mask, 0.0, 1.0)

    def _create_1d_gaussian_kernel(self, kernel_size: int, sigma: float) -> torch.Tensor:
        """Create 1D Gaussian kernel"""
        ax = torch.arange(-kernel_size // 2 + 1., kernel_size // 2 + 1.)
        gauss = torch.exp(-(ax ** 2) / (2 * sigma ** 2))
        kernel = gauss / gauss.sum()
        return kernel


