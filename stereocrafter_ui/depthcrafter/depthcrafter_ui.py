"""
DepthCrafter WebUI Component
Handles depth estimation interface and processing
"""

import os
import threading
import queue
import logging
import gradio as gr

from ..base.base_ui import BaseWebUI
from depthcrafter.depthcrafter_logic import DepthCrafterDemo
from depthcrafter.utils import (
    define_video_segments,
    get_segment_output_folder_name,
    get_segment_npz_output_filename,
    get_sidecar_json_filename,
    load_json_file,
    save_json_file,
)
# Import VRAM utility for dynamic resolution cap
from dependency.stereocrafter_util import get_current_vram_usage

logger = logging.getLogger(__name__)
try:
    from depthcrafter import merge_depth_segments
except ImportError as e:
    print(f"Warning: Could not import 'merge_depth_segments': {e}")
    merge_depth_segments = None


class DepthCrafterWebUI(BaseWebUI):
    """
    DepthCrafter UI component for depth map estimation from videos.
    Provides interface for configuring and running depth estimation with various parameters.
    """
    
    def __init__(self):
        super().__init__()
        
        # Auto-detect best offload type based on GPU configuration
        try:
            from dependency.stereocrafter_util import get_vram_config, get_gpu_memory_info
            
            vram_config = get_vram_config()
            gpu_info = get_gpu_memory_info()
            
            # Auto-detect best offload type based on GPU configuration
            gpu_name = gpu_info.get('gpu_name', '').lower()
            total_dedicated_gb = gpu_info.get('total_dedicated_gb', 0)
            
            # RTX 3060 12GB or better: Use model offload for better performance
            if total_dedicated_gb >= 12:
                # 12GB+ dedicated VRAM: Model offload for optimal performance
                default_offload = 'model'
            elif total_dedicated_gb >= 8:
                # 8-12GB: Model offload for safety
                default_offload = 'model'
            else:
                # <8GB: Sequential offload (slowest but necessary)
                default_offload = 'sequential'
                
            logger.info(f"DepthCrafter auto-selected offload_type='{default_offload}' based on GPU: {gpu_info.get('gpu_name', 'Unknown')} ({total_dedicated_gb:.1f}GB)")
        except Exception as e:
            logger.warning(f"Could not auto-detect GPU for DepthCrafter, using 'model' offload: {e}")
            default_offload = 'model'

        # Define all the variables that were in the original GUI
        self.input_dir_or_file_var = gr.Textbox(
            label="Input Folder/File", 
            value="./input_source_clips",
            info="Specify the folder containing your input video files or image sequences for batch processing, or select a single video file, image sequence folder, or single image file for individual processing."
        )
        self.upload_video = gr.File(
            label="Upload Video Files (Multiple)", 
            file_types=["video"],
            file_count="multiple"
        )
        self.output_dir = gr.Textbox(
            label="Output Folder", 
            value="./output_depthmaps",
            info="Specify the directory where output depth maps (merged videos, NPZ segments, or single video outputs) will be saved."
        )
        self.guidance_scale = gr.Slider(
            0.1, 10.0, value=1.0, 
            label="Guidance Scale",
            info="Controls how strongly the generation should adhere to the input image features for depth estimation. Higher values mean stricter adherence but can sometimes lead to less natural-looking depth if the model becomes too constrained. Default is often low (e.g., 1.0) for this type of model as it's primarily image-to-depth, not text-to-image guided. Experimentation might be needed for optimal results."
        )
        self.inference_steps = gr.Slider(
            1, 50, value=5, step=1, 
            label="Inference Steps",
            info="Number of denoising steps during the depth estimation process. More steps can potentially lead to higher quality and more detailed depth maps but will increase processing time. Common values: 5-20. The DepthCrafter paper often uses 5 steps for speed."
        )
        self.seed = gr.Number(
            label="Seed", 
            value=42,
            info="Random seed for the generation process. Using the same seed with identical parameters and input should ideally produce the same depth map output. Set to -1 for a random seed each time, leading to slight variations in output if other stochastic processes are involved."
        )
        self.cpu_offload = gr.Dropdown(
            ["none", "model", "sequential", "shared_memory"],
            value=default_offload,
            label="CPU Offload Mode",
            info="Moves parts of the model (like UNet, VAE) to CPU RAM when not actively used to save VRAM on the GPU. 'none': No offloading (fastest for 12GB+ VRAM). 'model': Offloads entire pipeline when idle (balanced, for 8-12GB). 'sequential': Fine-grained component offloading (slowest, for <8GB). 'shared_memory': Keeps UNet+VAE on GPU, moves image encoder to shared RAM (optimized for RTX 3060 12GB with 32GB+ system RAM)."
        )
        self.use_cudnn_benchmark = gr.Checkbox(
            label="Use CUDNN Benchmark", 
            value=False,
            info="Enables cuDNN auto-tuner. When enabled, cuDNN will try to find the optimal algorithms for the specific hardware and input sizes at the beginning of processing. This can lead to faster execution after an initial warm-up period, but the warm-up itself can take time. Best for consistent input sizes. Only applicable for Nvidia GPUs. If you change this setting, a full restart of the script might be needed for it to take effect properly for the model initialization."
        )
        self.process_length = gr.Number(
            label="Process Max Frames (-1 All)", 
            value=-1,
            info="Maximum number of frames to process from the input video. This count is applied *after* any 'Target FPS' adjustment. For example, if an input video is 300 frames at 30fps, and Target FPS is 15, the video becomes effectively 150 frames long for processing. If 'Process Max Frames' is set to 100, only the first 100 of these 150 frames will be processed. Set to -1 to process all available frames (up to the video's natural end or as limited by segment definitions if 'Process as Segments' is active)."
        )
        self.target_fps = gr.Number(
            label="Target FPS (-1 Original)", 
            value=-1.0,
            info="Desired frames per second for the output depth map. The input video will be sampled (frames possibly skipped or duplicated if necessary, though typically strided/downsampled) to approximate this FPS before processing. Set to -1 to use the original video's FPS. If the original FPS is very high, consider reducing it to save processing time."
        )
        # Use VRAM-aware configuration for window size and overlap
        from dependency.stereocrafter_util import get_vram_config
        vram_config = get_vram_config()
        self.window_size = gr.Slider(
            10, 200, value=vram_config['window_size'], step=1, 
            label="Window Size",
            info="This value has a dual role depending on the 'Process as Segments' setting: Full Video Mode (Unchecked 'Process as Segments'): Defines the size of the processing window (number of frames) that slides over the video. The model processes the video in these chunks. Segment Mode (Checked 'Process as Segments'): Defines the number of output frames in each generated segment NPZ file. This is the target length of each chunk before overlap is considered for processing. Typically 60-110 frames. Larger values can improve temporal consistency but require more VRAM and processing time per window/segment. Must be larger than 'Overlap'."
        )
        self.overlap = gr.Slider(
            0, 100, value=vram_config['overlap'], step=1,
            label="Overlap",
            info="This value also has a dual role: Full Video Mode (Unchecked 'Process as Segments'): Number of frames that consecutive processing windows overlap. This helps maintain temporal consistency across window boundaries. Segment Mode (Checked 'Process as Segments'): Number of frames that overlap between consecutive segments when they are defined and processed. For example, if Window Size is 100 and Overlap is 20, segment 1 might be frames 0-99, segment 2 might be frames 80-179 internally for processing, leading to an output overlap for smoother merging. Common values: 15-30 frames. Should be less than 'Window Size'."
        )
        self.decode_chunk_size = gr.Slider(
            2, 32, value=vram_config['decode_chunk_size'], step=1,
            label="Decode Chunk Size",
            info="Number of frames to decode at once during VAE decoding. Higher values = faster processing but more VRAM usage. Auto-detected based on your GPU (RTX 6000 Ada = 16). Reduce if you encounter OOM errors."
        )
        self.process_as_segments_var = gr.Checkbox(
            label="Process as Segments (Low VRAM Mode)", 
            value=False,
            info="Check this to process long videos or on systems with limited VRAM. When enabled, the input video is divided into smaller segments based on 'Window Size' and 'Overlap'. Each segment is processed individually to generate a raw depth data file (NPZ). After all segments are processed, they can be merged into a single, continuous depth map video or image sequence using the 'Merged Output Options'. This mode creates a subfolder named '[original_basename]_seg' in your output directory to store these intermediate NPZ files and a _master_meta.json file detailing the segments."
        )
        self.save_final_output_json_var = gr.Checkbox(
            label="Save Sidecar JSON for Final Output", 
            value=False,
            info="If checked: For 'Full Video' processing: A .json file with processing metadata will be saved alongside the final output depth video/sequence. For 'Process as Segments' mode: Individual .json files are saved for each raw segment NPZ *during processing* (if this option is on AND keep_intermediate_npz is on, these might be kept, otherwise they are usually deleted after master_meta is created). A _master_meta.json is always created in the segment subfolder. If a final merged output is created, a .json sidecar will be saved for that merged output, summarizing settings and pointing to the master_meta.json."
        )
        self.merge_output_format_var = gr.Dropdown(
            ["mp4", "main10_mp4", "png_sequence"], 
            value="mp4", 
            label="Merged Output Format",
            info="Only active if 'Process as Segments' is checked. Determines the file format of the final output after all processed segments are merged together. 'mp4': Creates a standard MP4 video file (typically 8-bit). 'main10_mp4': Creates HEVC HDR10 bit x265 MP4 video file. 'png_sequence': Creates a sequence of PNG images, one for each frame, in a new subfolder."
        )
        self.merge_alignment_method_var = gr.Dropdown(
            ["Shift & Scale", "Linear Blend"], 
            value="Shift & Scale", 
            label="Alignment Method",
            info="Only active if 'Process as Segments' is checked. Determines the method used to align and blend overlapping regions between consecutive depth segments during merging. 'Shift & Scale': Attempts to globally adjust the brightness (shift) and contrast (scale) of one segment to match the overlapping part of the previous segment. Good for consistent lighting. 'Linear Blend': Performs a simple linear cross-fade (alpha blend) in the overlapping region. Can be smoother but might lose some contrast if segments have very different overall brightness levels. Experiment to see which works best for your content."
        )
        self.merge_dither_var = gr.Checkbox(
            label="Dithering", 
            value=False,
            info="When enabled, applies dithering when converting the (often higher bit-depth) depth data to an 8-bit MP4 video. Dithering adds patterned noise to reduce visible banding artifacts that can occur in smooth gradients when color depth is reduced. Higher values mean stronger dithering noise. Typical range: 0.1 to 1.0. Experiment to find a good balance between reducing banding and avoiding excessive noise. Enable this if you see banding in your merged MP4 outputs."
        )
        self.merge_dither_strength_var = gr.Slider(
            0.0, 1.0, value=0.5, 
            label="Dither Strength",
            info="Strength of the dithering effect when converting to 8-bit MP4. Higher values result in more noticeable dithering (more noise, less banding). Range 0.0 to 1.0."
        )
        self.merge_gamma_correct_var = gr.Checkbox(
            label="Gamma Adjust", 
            value=False,
            info="When enabled and 'Merged Output Format' is 'mp4'. Applies gamma adjustment to the depth map values before saving as MP4. This can help adjust the perceived brightness and contrast of the depth map, boosting depth in the background while crushing in the forground. Useful if the default MP4 output appears too dark or too washed out. Values > 1.0 will generally make mid-tones brighter (pulling midground closer). Values < 1.0 will generally make mid-tones darker (pushing midground away). Default 1.5"
        )
        self.merge_gamma_value_var = gr.Slider(
            0.1, 3.0, value=1.5, 
            label="Gamma Value",
            info="The gamma value to apply if gamma correction is enabled. Values > 1.0 brighten mid-tones, values < 1.0 darken mid-tones."
        )
        self.merge_percentile_norm_var = gr.Checkbox(
            label="Normalization", 
            value=False,
            info="Only active if 'Process as Segments' is checked. When merging segments, this option normalizes the depth values based on percentiles across all segments rather than simple min/max. This can help to reduce the impact of extreme outliers (e.g., a few very bright or very dark pixels) on the overall brightness and contrast of the final merged output, leading to a more balanced result. If unchecked, a simpler global min/max normalization across all segments is typically used."
        )
        self.merge_norm_low_perc_var = gr.Slider(
            0.0, 5.0, value=0.1, 
            label="Norm Low Percentile",
            info="Specifies the lower percentile of depth values that will be mapped to black (or the minimum output value) if Percentile Normalization is enabled. Helps ignore extreme dark outliers. Typical value: 0.1 to 1.0."
        )
        self.merge_norm_high_perc_var = gr.Slider(
            95.0, 100.0, value=99.9, 
            label="Norm High Percentile",
            info="Specifies the upper percentile of depth values that will be mapped to white (or the maximum output value) if Percentile Normalization is enabled. Helps ignore extreme bright outliers. Typical value: 99.0 to 99.9."
        )
        self.keep_intermediate_npz_var = gr.Checkbox(
            label="Keep intermediate NPZ", 
            value=False,
            info="Only active if 'Process as Segments' is checked. If this option is checked, the individual segment NPZ files (raw depth data) and any generated intermediate visual outputs (like segment MP4s or PNG sequences, based on 'Segment Visual Format') will be kept in the '[basename]_seg' subfolder even after merging is complete. If unchecked (default), this subfolder and its contents are usually deleted after a successful merge to save space, leaving only the final merged output. The 'Min Orig. Vid Frames to Keep NPZ' setting can override this to delete for short videos."
        )
        self.min_frames_to_keep_npz_var = gr.Number(
            label="Min Frames to Keep NPZ", 
            value=0,
            info="Only active if 'Process as Segments' and 'Keep intermediate NPZ files' are both checked. This sets a threshold based on the *original* video's total frame count. If the original video has fewer frames than this number, the intermediate segment folder will be deleted even if 'Keep intermediate NPZ files' is checked. Set to 0 or a negative value to always respect the 'Keep intermediate NPZ files' checkbox, regardless of video length."
        )
        self.keep_intermediate_segment_visual_format_var = gr.Dropdown(
            ["png_sequence", "mp4", "none"], 
            value="mp4", 
            label="Segment Visual Format",
            info="Only active if 'Process as Segments' is checked and 'Keep intermediate NPZ files' is also checked (or visuals are generated manually via button). Determines the format for saving visual representations of each individual processed segment's depth map. These are saved alongside the NPZ files in the segment subfolder. 'png_sequence': Saves each frame as a PNG image in a sub-subfolder. 'mp4': Saves a playable MP4 video of the segment's depth map. 'none': No visual representation is saved for segments, only the NPZ data files. These visuals are for previewing or debugging individual segments."
        )
        self.merge_output_suffix_var = gr.Textbox(
            label="Output Suffix", 
            value="_depth",
            info="This suffix will be appended to the original video's basename to form the merged output filename (before the extension). Default is '_depth'. Example: If original is 'my_video.mp4' and suffix is '_custom_depth', merged output might be 'my_video_custom_depth.mp4'."
        )
        self.use_local_models_only_var = gr.Checkbox(
            label="Use Local Models Only", 
            value=False,
            info="If checked, the model will only attempt to load files from the local Hugging Face cache and will NOT attempt to connect to the Hugging Face Hub for verification or download. This can significantly speed up startup time if models are already cached locally. If a model is not found in the local cache, an error will occur."
        )
        self.target_height = gr.Slider(
            100, 2160, value=1080, step=1, 
            label="Target Height",
            info="Set your vertical resolution, must be a multple of 64."
        )
        self.target_width = gr.Slider(
            100, 3840, value=1920, step=1, 
            label="Target Width",
            info="Set your Horizonat resolution, must be a multple of 64."
        )
        self.enable_dual_output_robust_norm = gr.Checkbox(
            label="Enable Secondary Output", 
            value=False,
            info="If enabled, a second depth map video/sequence will be generated using a robust, global normalization method. This can help stabilize depth appearance by ignoring extreme outliers, preventing flicker caused by objects entering/exiting the scene."
        )
        self.robust_norm_low_percentile = gr.Slider(
            0.0, 100.0, value=0.0, 
            label="Robust Norm Low Percentile",
            info="The lower percentile of raw depth values to consider for robust normalization. Depths numerically smaller than this percentile will be mapped to the 'Low' output range. Helps ignore extreme closest outliers (e.g., 0.5 for 0.5%)."
        )
        self.robust_norm_high_percentile = gr.Slider(
            0.0, 100.0, value=75.5, 
            label="Robust Norm High Percentile",
            info="The upper percentile of raw depth values to consider for robust normalization. Depths numerically larger than this percentile will be mapped to the 'High' output range. Helps ignore extreme farthest outliers (e.g., 99.5 for 99.5%). Setting a lower value (e.g., 75.0) can aggressively compress the far background to black."
        )
        self.robust_norm_output_min = gr.Slider(
            0.0, 1.0, value=0.0, 
            label="Robust Output Min",
            info="The minimum value (0-1) that the normalized secondary output depth map will be clamped to. Typically 0.0 (black/far)."
        )
        self.robust_norm_output_max = gr.Slider(
            0.0, 1.0, value=1.0, 
            label="Robust Output Max",
            info="The maximum value (0-1) that the normalized secondary output depth map will be clamped to. Typically 1.0 (white/close). Lowering this (e.g., to 0.25) can compress the entire scene to a darker visual range, emphasizing relative changes more subtly."
        )
        self.robust_output_suffix = gr.Textbox(
            label="Robust Output Suffix", 
            value="_clipped_depth",
            info="The suffix added to the filename of the second (robustly normalized) output. E.g., '_clipped_depth' will result in 'video_name_clipped_depth.mp4'."
        )
        self.is_depth_far_black = gr.Checkbox(label="Is Depth Far Black", value=True)
        self.dark_mode_var = gr.Checkbox(label="Dark Mode", value=False)

        # Auto-detect GPU for xformers and cudnn defaults
        try:
            gpu_info = get_gpu_memory_info()
            total_dedicated_gb = gpu_info.get('total_dedicated_gb', 0)
            if total_dedicated_gb >= 8:
                # Enable optimizations for 8GB+ GPUs
                default_disable_xformers = False
                default_use_cudnn = True
            else:
                default_disable_xformers = True
                default_use_cudnn = False
        except:
            default_disable_xformers = True
            default_use_cudnn = False

        self.disable_xformers_var = gr.Checkbox(label="Disable xFormers (VRAM Save)", value=default_disable_xformers)
        self.use_cudnn_benchmark = gr.Checkbox(label="Use cuDNN Benchmark", value=default_use_cudnn)
        
        # Status and progress
        self.status_message_var = gr.Textbox(label="Status", value="Ready")
        self.progress = gr.Slider(0, 100, value=0, label="Progress")

    def create_interface(self):
        """Creates the Gradio interface for DepthCrafter"""
        
        print("[DEBUG] Creating Input Source section...")
        # Input Source Section
        with gr.Group():
            gr.Markdown("### Input Source")
            with gr.Row():
                self.input_dir_or_file_var.render()
            with gr.Row():
                self.upload_video.render()
            with gr.Row():
                self.output_dir.render()
        
        print("[DEBUG] Creating Main Settings container...")
        # Main Settings Container - Use accordions to reduce initial load
        with gr.Row():
            # Left Column
            with gr.Column():
                with gr.Accordion("Main Parameters", open=True):
                    self.guidance_scale.render()
                    self.inference_steps.render()
                    self.target_width.render()
                    self.target_height.render()
                    self.seed.render()
                    self.cpu_offload.render()
                    self.use_cudnn_benchmark.render()
                    self.disable_xformers_var.render()

                with gr.Accordion("Merged Output Options", open=False):
                    self.keep_intermediate_npz_var.render()
                    self.min_frames_to_keep_npz_var.render()
                    self.keep_intermediate_segment_visual_format_var.render()

                    self.merge_dither_var.render()
                    self.merge_dither_strength_var.render()

                    self.merge_gamma_correct_var.render()
                    self.merge_gamma_value_var.render()

                    self.merge_percentile_norm_var.render()
                    with gr.Row():
                        self.merge_norm_low_perc_var.render()
                        self.merge_norm_high_perc_var.render()

                    self.merge_alignment_method_var.render()
                    self.merge_output_format_var.render()
                    self.merge_output_suffix_var.render()

            # Right Column
            with gr.Column():
                with gr.Accordion("Frame & Segment Control", open=False):
                    self.window_size.render()
                    self.overlap.render()
                    self.decode_chunk_size.render()
                    self.target_fps.render()
                    self.process_length.render()
                    self.save_final_output_json_var.render()
                    self.process_as_segments_var.render()

                with gr.Accordion("Secondary Output", open=False):
                    self.enable_dual_output_robust_norm.render()
                    gr.Markdown("**Depth Output Range (0-1):**")
                    with gr.Row():
                        self.robust_norm_output_min.render()
                        self.robust_norm_output_max.render()
                    gr.Markdown("**Clipped Output % Range:**")
                    with gr.Row():
                        self.robust_norm_low_percentile.render()
                        self.robust_norm_high_percentile.render()
                    self.robust_output_suffix.render()



        # Controls Section
        with gr.Group():
            gr.Markdown("### Controls")
            with gr.Row():
                start_btn = gr.Button("Start", variant="primary")
                cancel_btn = gr.Button("Cancel")
                clear_vram_btn = gr.Button("Clear VRAM", variant="secondary")
                remerge_btn = gr.Button("Re-Merge Segments")

            self.progress.render()
            self.status_message_var.render()

        # Function to handle video upload
        def handle_video_upload(video_files):
            if video_files is not None and len(video_files) > 0:
                import shutil
                # Create input directory if it doesn't exist
                os.makedirs("./input_source_clips", exist_ok=True)
                
                # Handle multiple files
                uploaded_count = 0
                for video_file in video_files:
                    # Get the filename from the uploaded file path
                    filename = os.path.basename(video_file.name)
                    destination_path = os.path.join("./input_source_clips", filename)
                    
                    # Copy the uploaded file to the input directory
                    shutil.copy2(video_file.name, destination_path)
                    uploaded_count += 1
                
                # Return the input directory path to support batch processing
                print(f"✅ Uploaded {uploaded_count} video file(s) to ./input_source_clips")
                return "./input_source_clips"
            return gr.update()

        # Event handler for the upload component
        self.upload_video.change(
            fn=handle_video_upload,
            inputs=[self.upload_video],
            outputs=[self.input_dir_or_file_var]
        )

        # Event handlers
        start_btn.click(
            fn=self.start_processing,
            inputs=[
                self.input_dir_or_file_var, self.output_dir,
                self.guidance_scale, self.inference_steps, self.seed,
                self.cpu_offload, self.use_cudnn_benchmark,
                self.process_length, self.target_fps,
                self.window_size, self.overlap, self.decode_chunk_size,
                self.process_as_segments_var, self.save_final_output_json_var,
                self.merge_output_format_var, self.merge_alignment_method_var,
                self.merge_dither_var, self.merge_dither_strength_var,
                self.merge_gamma_correct_var, self.merge_gamma_value_var,
                self.merge_percentile_norm_var, self.merge_norm_low_perc_var,
                self.merge_norm_high_perc_var, self.keep_intermediate_npz_var,
                self.min_frames_to_keep_npz_var, self.keep_intermediate_segment_visual_format_var,
                self.merge_output_suffix_var, self.use_local_models_only_var,
                self.target_height, self.target_width,
                self.enable_dual_output_robust_norm, self.robust_norm_low_percentile,
                self.robust_norm_high_percentile, self.robust_norm_output_min,
                self.robust_norm_output_max, self.robust_output_suffix,
                self.is_depth_far_black, self.disable_xformers_var
            ],
            outputs=[self.status_message_var, self.progress]
        )
        
        cancel_btn.click(
            fn=self.stop_processing,
            inputs=[],
            outputs=[self.status_message_var]
        )

        clear_vram_btn.click(
            fn=self.clear_vram_memory,
            inputs=[],
            outputs=[self.status_message_var]
        )

        remerge_btn.click(
            fn=self.remerge_segments,
            inputs=[
                self.output_dir, self.merge_output_format_var, self.merge_alignment_method_var,
                self.merge_dither_var, self.merge_dither_strength_var,
                self.merge_gamma_correct_var, self.merge_gamma_value_var,
                self.merge_percentile_norm_var, self.merge_norm_low_perc_var,
                self.merge_norm_high_perc_var, self.merge_output_suffix_var,
                self.enable_dual_output_robust_norm, self.robust_norm_low_percentile,
                self.robust_norm_high_percentile, self.robust_norm_output_min,
                self.robust_norm_output_max, self.robust_output_suffix,
                self.is_depth_far_black
            ],
            outputs=[self.status_message_var, self.progress]
        )

        return [
            self.input_dir_or_file_var, self.output_dir,
            self.guidance_scale, self.inference_steps, self.seed,
            self.cpu_offload, self.use_cudnn_benchmark,
            self.process_length, self.target_fps,
            self.window_size, self.overlap, self.decode_chunk_size,
            self.process_as_segments_var, self.save_final_output_json_var,
            self.merge_output_format_var, self.merge_alignment_method_var,
            self.merge_dither_var, self.merge_dither_strength_var,
            self.merge_gamma_correct_var, self.merge_gamma_value_var,
            self.merge_percentile_norm_var, self.merge_norm_low_perc_var,
            self.merge_norm_high_perc_var, self.keep_intermediate_npz_var,
            self.min_frames_to_keep_npz_var, self.keep_intermediate_segment_visual_format_var,
            self.merge_output_suffix_var, self.use_local_models_only_var,
            self.target_height, self.target_width,
            self.enable_dual_output_robust_norm, self.robust_norm_low_percentile,
            self.robust_norm_high_percentile, self.robust_norm_output_min,
            self.robust_norm_output_max,             self.robust_output_suffix,
            self.is_depth_far_black, self.disable_xformers_var,
            self.progress, self.status_message_var
        ]

    def start_processing(self, *args, progress=gr.Progress()):
        """Starts the depth estimation processing"""
        import logging
        logger = logging.getLogger(__name__)

        # CRITICAL: Clear stop_event at the start of new processing
        self.stop_event.clear()
        logger.debug("stop_event cleared for new processing job")

        # Extract parameters from args
        (input_path, output_path, guidance_scale, inference_steps, seed,
         cpu_offload, use_cudnn_benchmark, process_length, target_fps,
         window_size, overlap, decode_chunk_size, process_as_segments, save_final_json,
         merge_output_format, merge_alignment_method, merge_dither,
         merge_dither_strength, merge_gamma_correct, merge_gamma_value,
         merge_percentile_norm, merge_norm_low_perc, merge_norm_high_perc,
         keep_intermediate_npz, min_frames_to_keep_npz,
         keep_intermediate_segment_visual_format, merge_output_suffix,
         use_local_models_only, target_height, target_width,
         enable_dual_output_robust_norm, robust_norm_low_percentile,
         robust_norm_high_percentile, robust_norm_output_min,
         robust_norm_output_max, robust_output_suffix,
         is_depth_far_black, disable_xformers) = args

        try:
            # Parameter validation and type conversion
            logger.info("=" * 80)
            logger.info("Starting DepthCrafter processing...")
            logger.info(f"Input: {input_path}")
            logger.info(f"Output: {output_path}")
            
            # Convert and validate boolean parameters
            use_cudnn_benchmark = bool(use_cudnn_benchmark) if use_cudnn_benchmark is not None else False
            use_local_models_only = bool(use_local_models_only) if use_local_models_only is not None else False
            disable_xformers = bool(disable_xformers) if disable_xformers is not None else True
            process_as_segments = bool(process_as_segments) if process_as_segments is not None else False
            save_final_json = bool(save_final_json) if save_final_json is not None else False
            keep_intermediate_npz = bool(keep_intermediate_npz) if keep_intermediate_npz is not None else False
            
            # Convert numeric parameters
            inference_steps = int(inference_steps)
            seed = int(seed)
            process_length = int(process_length)
            target_fps = float(target_fps)
            window_size = int(window_size)
            overlap = int(overlap)
            target_height = int(target_height)
            target_width = int(target_width)
            min_frames_to_keep_npz = int(min_frames_to_keep_npz)

            # Automatically reduce resolution for very high res to prevent OOM
            # Dynamic max_res based on available VRAM
            try:
                vram_info = get_current_vram_usage()
                total_vram = vram_info.get('total_gb', 8)  # Default to 8GB if unavailable
                free_vram = vram_info.get('free_gb', total_vram)
                free_percentage = free_vram / total_vram if total_vram > 0 else 0
                effective_vram = total_vram if free_percentage > 0.8 else free_vram * 1.2
                # Set max_res based on effective VRAM tiers
                if effective_vram < 8:
                    max_res = 512
                elif effective_vram < 12:
                    max_res = 768
                elif effective_vram < 24:
                    max_res = 1024
                elif effective_vram < 48:
                    max_res = 1024  # Conservative for 24-48GB
                else:
                    max_res = 1536  # Allow higher for 48GB+ GPUs, model may support up to 1536
            except Exception as e:
                logger.warning(f"Could not determine VRAM for dynamic resolution cap, using default 1024: {e}")
                max_res = 1024
            # Preserve aspect ratio when clamping resolution
            if target_height > max_res or target_width > max_res:
                scale = min(1.0, max_res / max(target_height, target_width))
                new_height = int(target_height * scale)
                new_width = int(target_width * scale)
                if new_height != target_height or new_width != target_width:
                    logger.warning(f"Target resolution {target_width}x{target_height} exceeds max_res {max_res}, scaling down to {new_width}x{new_height} to prevent OOM while preserving aspect ratio")
                    target_height = new_height
                    target_width = new_width

            logger.info("="*60)
            logger.info("PROCESSING STARTED - Actual Values Being Used")
            logger.info("="*60)
            logger.info(f"Parameters: steps={inference_steps}, seed={seed}, cudnn_benchmark={use_cudnn_benchmark}")
            logger.info(f"Window: size={window_size}, overlap={overlap}")
            logger.info(f"Target resolution: {target_width}x{target_height}")
            logger.info(f"CPU Offload: {cpu_offload}")
            logger.info("="*60)
            
            progress(0, desc="Initializing DepthCrafter...")
            
            # Initialize DepthCrafterDemo
            logger.info("Initializing DepthCrafter model...")
            demo = DepthCrafterDemo(
                unet_path="tencent/DepthCrafter",
                pre_train_path="stabilityai/stable-video-diffusion-img2vid-xt",
                cpu_offload=cpu_offload,
                use_cudnn_benchmark=use_cudnn_benchmark,
                local_files_only=use_local_models_only,
                disable_xformers=disable_xformers,
            )

            # Set PyTorch CUDA memory config to reduce fragmentation
            import os
            os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True,max_split_size_mb:512'
            logger.info("Model initialized successfully")
            
            progress(0.1, desc="Scanning for videos...")
            
            # Check if input is a folder - if so, scan for video files (batch mode)
            video_files_to_process = []
            if os.path.isdir(input_path):
                logger.info(f"Input is a folder - scanning for video files...")
                import glob
                video_extensions = ['*.mp4', '*.avi', '*.mov', '*.mkv', '*.webm', '*.flv', '*.gif']
                for ext in video_extensions:
                    video_files_to_process.extend(glob.glob(os.path.join(input_path, ext)))
                
                video_files_to_process = sorted(video_files_to_process)
                
                if not video_files_to_process:
                    # No video files found - might be an image sequence folder
                    logger.info(f"No video files found in folder. Checking if it's an image sequence...")
                    # Let it fall through to process as image sequence
                    video_files_to_process = [input_path]
                else:
                    logger.info(f"Found {len(video_files_to_process)} video files to process")
            else:
                # Single file mode
                video_files_to_process = [input_path]
                logger.info(f"Processing single file: {input_path}")
            
            # Process each video file
            total_videos = len(video_files_to_process)
            for video_idx, current_video_path in enumerate(video_files_to_process):
                if self.stop_event.is_set():
                    logger.warning("Processing cancelled by user")
                    return "Processing cancelled", 0
                
                logger.info("=" * 80)
                logger.info(f"Processing video {video_idx + 1}/{total_videos}: {os.path.basename(current_video_path)}")
                logger.info("=" * 80)
                
                # Update progress for this video
                video_progress_start = (video_idx / total_videos)
                video_progress_range = (1.0 / total_videos)
                
                progress(video_progress_start, desc=f"Video {video_idx + 1}/{total_videos}: Defining segments...")
            
                # Define video segments for this specific video
                original_basename = os.path.splitext(os.path.basename(current_video_path))[0]
                source_type = "video_file" if current_video_path.endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.gif')) else "image_sequence_folder"
                
                logger.info(f"Processing: {original_basename} (type: {source_type})")
                
                all_potential_segments, base_job_info = define_video_segments(
                    video_path_or_folder=current_video_path,
                    original_basename=original_basename,
                    gui_target_fps_setting=target_fps,
                    gui_process_length_overall=process_length,
                    gui_segment_output_window_frames=window_size,
                    gui_segment_output_overlap_frames=overlap,
                    source_type=source_type,
                    gui_target_height_setting=target_height,
                    gui_target_width_setting=target_width,
                )
                
                # Validate that segments were defined successfully
                if base_job_info is None:
                    error_msg = (
                        f"Failed to process: {current_video_path}\n\n"
                        f"Detected as: {source_type}\n\n"
                        f"Skipping this file and continuing with next..."
                    )
                    logger.error(error_msg)
                    continue  # Skip to next video instead of failing completely
                
                # Extract video information for display
                video_info_filename = os.path.basename(current_video_path)
                video_info_resolution = f"{base_job_info.get('original_video_width', 'N/A')}x{base_job_info.get('original_video_height', 'N/A')}"
                video_info_frames = str(base_job_info.get('original_video_raw_frame_count', 'N/A'))
                
                logger.info(f"Video Info - File: {video_info_filename}, Resolution: {video_info_resolution}, Frames: {video_info_frames}")

                # Process based on settings
                if process_as_segments and all_potential_segments:
                    # Process as segments
                    total_segments = len(all_potential_segments)
                    logger.info(f"Processing as {total_segments} segments...")
                    
                    progress(video_progress_start, desc=f"📹 {video_info_filename} | {video_info_resolution} | {video_info_frames} frames | {total_segments} segments")
                    
                    # Create segment subfolder for this video
                    segment_subfolder_name = get_segment_output_folder_name(original_basename)
                    segment_subfolder_path = os.path.join(output_path, segment_subfolder_name)
                    os.makedirs(segment_subfolder_path, exist_ok=True)
                    
                    # Initialize master metadata entry for this video
                    master_meta_for_this_vid = {
                        "original_video_basename": original_basename,
                        "original_video_details": {
                            "raw_frame_count": base_job_info.get("original_video_raw_frame_count", 0),
                            "original_fps": base_job_info.get("original_video_fps", 30.0)
                        },
                        "global_processing_settings": {
                            "guidance_scale": guidance_scale,
                            "inference_steps": inference_steps,
                            "target_height_setting": target_height,
                            "target_width_setting": target_width,
                            "seed_setting": seed,
                            "target_fps_setting": target_fps,
                            "process_max_frames_setting": process_length,
                            "gui_window_size_setting": window_size,
                            "gui_overlap_setting": overlap,
                            "processed_as_segments": process_as_segments,
                            "segment_definition_output_window_frames": window_size,  # Required for merging
                            "segment_definition_output_overlap_frames": overlap,    # Required for merging
                        },
                        "jobs_info": [],
                        "overall_status": "pending",
                        "total_expected_jobs": total_segments,
                        "completed_successful_jobs": 0,
                        "completed_failed_jobs": 0,
                    }
                    
                    for i, segment_info in enumerate(all_potential_segments):
                        if self.stop_event.is_set():
                            logger.warning("Processing cancelled by user")
                            return "Processing cancelled", 0
                            
                        # Update progress within this video's range
                        segment_progress = video_progress_start + (i / total_segments) * video_progress_range
                        progress(segment_progress, desc=f"📹 {video_info_filename} | Segment {i+1}/{total_segments}")
                        logger.info(f"Processing segment {i+1}/{total_segments}...")
                        
                        # Determine if we should keep NPZ files for this segment
                        keep_npz_for_this_job_run = False
                        is_segment_job = True
                        if is_segment_job:
                            if keep_intermediate_npz:
                                min_frames_thresh = min_frames_to_keep_npz
                                orig_vid_frame_count = base_job_info.get("original_video_raw_frame_count", 0)
                                if min_frames_thresh <= 0 or orig_vid_frame_count >= min_frames_thresh:
                                    keep_npz_for_this_job_run = True
                        
                        # Run the segment
                        saved_data_filepath, returned_job_specific_metadata = demo.run(
                            video_path_or_frames_or_info=segment_info,
                            num_denoising_steps=inference_steps,
                            guidance_scale=guidance_scale,
                            base_output_folder=output_path,  # Save to output path (logic handles subfolder)
                            gui_window_size=window_size,
                            gui_overlap=overlap,
                            process_length_for_read_full_video=-1,  # Process segment
                            target_height=target_height,
                            target_width=target_width,
                            seed=seed,
                            original_video_basename_override=original_basename,
                            segment_job_info_param=segment_info,
                            keep_intermediate_npz_config=keep_npz_for_this_job_run,  # Use the calculated value
                            intermediate_segment_visual_format_config=keep_intermediate_segment_visual_format,
                            save_final_json_for_this_job_config=save_final_json
                        )
                        
                        if returned_job_specific_metadata.get("status") == "success":
                            job_successful = True
                            logger.info(f"Segment {i+1}/{total_segments} completed successfully")
                            
                            # Get the actual output filename from the returned metadata
                            # The depthcrafter logic should return the filename in the metadata
                            actual_npz_filename = returned_job_specific_metadata.get("output_segment_filename", "")
                            
                            # If the filename is not provided in the metadata, construct it based on the known pattern
                            # The segment_id in segment_info starts from 0, but the filename pattern uses 1-based indexing
                            if not actual_npz_filename:
                                # Use the standard naming pattern from the utils function
                                # segment_info.get("segment_id") should give us the correct ID for the filename
                                segment_id_for_filename = segment_info.get("segment_id", i)
                                actual_npz_filename = get_segment_npz_output_filename(original_basename, segment_id_for_filename, total_segments)
                            
                            # Add job info to master metadata
                            job_info_entry = {
                                "segment_id": segment_info.get("segment_id", i),
                                "total_segments": total_segments,
                                "output_segment_filename": actual_npz_filename,
                                "status": "success",
                                "processed_at_fps": returned_job_specific_metadata.get("processed_at_fps", 30.0),
                                "frames_in_output_video": returned_job_specific_metadata.get("frames_in_output_video", 0),
                                "processed_height": returned_job_specific_metadata.get("processed_height", target_height),
                                "processed_width": returned_job_specific_metadata.get("processed_width", target_width),
                            }
                            master_meta_for_this_vid["jobs_info"].append(job_info_entry)
                            master_meta_for_this_vid["completed_successful_jobs"] += 1
                        else:
                            job_successful = False
                            logger.info(f"Segment {i+1}/{total_segments} failed")
                            
                            # Add failed job info to master metadata
                            job_info_entry = {
                                "segment_id": segment_info.get("segment_id", i),
                                "total_segments": total_segments,
                                "output_segment_filename": "",
                                "status": returned_job_specific_metadata.get("status", "failure"),
                                "error_message": returned_job_specific_metadata.get("error_message", "Unknown error"),
                            }
                            master_meta_for_this_vid["jobs_info"].append(job_info_entry)
                            master_meta_for_this_vid["completed_failed_jobs"] += 1
                    
                    # After all segments are processed, check if we should merge them
                    if master_meta_for_this_vid["completed_successful_jobs"] > 0:
                        master_meta_for_this_vid["overall_status"] = "all_success" if master_meta_for_this_vid["completed_failed_jobs"] == 0 else "partial_success"
                        
                        # Save master metadata file
                        master_meta_filepath = os.path.join(segment_subfolder_path, f"{original_basename}_master_meta.json")
                        if save_json_file(master_meta_for_this_vid, master_meta_filepath):
                            logger.info(f"Saved master metadata for {original_basename} to {master_meta_filepath}")
                            
                            # Perform merging if merge_depth_segments module is available
                            if merge_depth_segments:
                                try:
                                    progress(video_progress_start + 0.9 * video_progress_range, desc=f"📹 {video_info_filename} | Merging segments...")
                                    
                                    # Prepare merge parameters
                                    out_fmt = merge_output_format
                                    output_suffix = merge_output_suffix
                                    merged_base_name = f"{original_basename}{output_suffix}"
                                    
                                    align_method = "linear_blend" if merge_alignment_method == "Linear Blend" else "shift_scale"
                                    
                                    # Call the merge function
                                    primary_output_path = merge_depth_segments.merge_depth_segments(
                                        master_meta_path=master_meta_filepath,
                                        output_path_arg=output_path,
                                        do_dithering=merge_dither,
                                        dither_strength_factor=merge_dither_strength,
                                        apply_gamma_correction=merge_gamma_correct,
                                        gamma_value=merge_gamma_value,
                                        use_percentile_norm=merge_percentile_norm,
                                        norm_low_percentile=merge_norm_low_perc,
                                        norm_high_percentile=merge_norm_high_perc,
                                        output_format=out_fmt,
                                        merge_alignment_method=align_method,
                                        output_filename_override_base=merged_base_name,
                                        enable_dual_output_robust_norm=enable_dual_output_robust_norm,
                                        robust_norm_low_percentile=robust_norm_low_percentile,
                                        robust_norm_high_percentile=robust_norm_high_percentile,
                                        robust_norm_output_min=robust_norm_output_min,
                                        robust_norm_output_max=robust_norm_output_max,
                                        robust_output_suffix=robust_output_suffix,
                                        is_depth_far_black=is_depth_far_black
                                    )
                                    
                                    if primary_output_path:
                                        logger.info(f"Merging completed successfully. Output: {primary_output_path}")
                                    else:
                                        logger.warning(f"Merging completed but no output path was returned for {original_basename}")
                                    
                                except Exception as e:
                                    logger.error(f"Error during merging for {original_basename}: {e}", exc_info=True)
                                    # Continue processing other videos even if merging fails
                            else:
                                logger.warning(f"Merge module not available, skipping merge for {original_basename}")
                        else:
                            logger.error(f"Failed to save master metadata for {original_basename}")
                    else:
                        logger.warning(f"All segments failed for {original_basename}, skipping merge")
                else:
                    # Process as full video
                    progress(video_progress_start + 0.2 * video_progress_range, desc=f"📹 {video_info_filename} | {video_info_resolution} | {video_info_frames} frames | Processing...")
                    logger.info("Processing as full video...")
                    
                    job_info = {
                        **base_job_info,
                        "is_segment": False,
                        "gui_desired_output_window_frames": window_size,
                        "gui_desired_output_overlap_frames": overlap
                    }
                    
                    demo.run(
                        video_path_or_frames_or_info=job_info,
                        num_denoising_steps=inference_steps,
                        guidance_scale=guidance_scale,
                        base_output_folder=output_path,
                        gui_window_size=window_size,
                        gui_overlap=overlap,
                        process_length_for_read_full_video=process_length,
                        target_height=target_height,
                        target_width=target_width,
                        seed=seed,
                        original_video_basename_override=original_basename,
                        segment_job_info_param=None,
                        keep_intermediate_npz_config=keep_intermediate_npz,
                        intermediate_segment_visual_format_config=keep_intermediate_segment_visual_format,
                        save_final_json_for_this_job_config=save_final_json
                    )
                    logger.info("Full video processing completed")
                
                logger.info(f"Completed video {video_idx + 1}/{total_videos}: {original_basename}")

                # Clear GPU memory between videos to prevent accumulation and fragmentation
                try:
                    import torch
                    import gc
                    # Synchronize to ensure all CUDA operations complete
                    torch.cuda.synchronize()
                    # Empty cache multiple times to handle fragmentation
                    for _ in range(3):
                        torch.cuda.empty_cache()
                    gc.collect()
                    # Reset memory stats to clear any lingering references
                    torch.cuda.reset_peak_memory_stats()
                    logger.debug(f"Cleared GPU memory after processing video {video_idx + 1}")
                except Exception as e:
                    logger.warning(f"Failed to clear memory after video {video_idx + 1}: {e}")

            progress(1.0, desc="Processing completed!")
            logger.info("=" * 80)
            logger.info("Processing completed successfully!")
            logger.info("=" * 80)

            # Clean up large objects to prevent memory accumulation
            try:
                del demo
                demo = None  # Explicitly set to None
                gc.collect()
                torch.cuda.empty_cache()
                logger.debug("Deleted DepthCrafter demo object and forced garbage collection")
            except Exception as e:
                logger.warning(f"Failed to delete demo object: {e}")

            # CRITICAL: Clear stop_event after processing completes
            self.stop_event.clear()
            logger.debug("stop_event cleared after processing completion")

            return "Processing completed successfully!", 100

        except Exception as e:
            import traceback
            error_msg = f"Error: {str(e)}"
            traceback_str = traceback.format_exc()

            # Clean up large objects even on error
            try:
                if 'demo' in locals():
                    del demo
                    logger.debug("Deleted DepthCrafter demo object after error")
            except Exception as cleanup_e:
                logger.warning(f"Failed to delete demo object after error: {cleanup_e}")

            # Log to terminal
            logger.error("=" * 80)
            logger.error("ERROR during processing:")
            logger.error(error_msg)
            logger.error(traceback_str)
            logger.error("=" * 80)

            # CRITICAL: Clear stop_event after error
            self.stop_event.clear()
            logger.debug("stop_event cleared after processing error")

            # Return error to UI
            return f"{error_msg}\n\nSee terminal for full traceback.", 0

    def stop_processing(self):
        """Stop the current processing"""
        import logging
        logger = logging.getLogger(__name__)

        logger.warning("Cancel requested by user")
        self.stop_event.set()
        return "⚠️ Cancellation requested - will stop after current segment"

    def remerge_segments(self, output_dir, merge_output_format, merge_alignment_method,
                         merge_dither, merge_dither_strength, merge_gamma_correct, merge_gamma_value,
                         merge_percentile_norm, merge_norm_low_perc, merge_norm_high_perc, merge_output_suffix,
                         enable_dual_output_robust_norm, robust_norm_low_percentile, robust_norm_high_percentile,
                         robust_norm_output_min, robust_norm_output_max, robust_output_suffix, is_depth_far_black, progress=gr.Progress()):
        """Remerge segments using existing master metadata files"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info("Starting re-merge process...")
            progress(0, desc="Scanning for master metadata files...")
            
            # Find all master metadata files in the output directory
            import glob
            master_meta_files = glob.glob(os.path.join(output_dir, "**", "*_master_meta.json"), recursive=True)
            
            if not master_meta_files:
                logger.warning(f"No master metadata files found in {output_dir}")
                return "No master metadata files found for re-merging", 0
            
            logger.info(f"Found {len(master_meta_files)} master metadata files to re-merge")
            
            for idx, master_meta_path in enumerate(master_meta_files):
                progress(idx / len(master_meta_files), desc=f"Re-merging {idx+1}/{len(master_meta_files)}...")
                
                logger.info(f"Re-merging from metadata: {os.path.basename(master_meta_path)}")
                
                # Load the master metadata
                master_meta = load_json_file(master_meta_path)
                if not master_meta:
                    logger.error(f"Could not load master metadata: {master_meta_path}")
                    continue
                
                original_basename = master_meta.get("original_video_basename", "unknown")
                
                # Perform the merge using the existing metadata
                if merge_depth_segments:
                    try:
                        # Prepare merge parameters
                        out_fmt = merge_output_format
                        output_suffix = merge_output_suffix
                        merged_base_name = f"{original_basename}{output_suffix}"
                        
                        align_method = "linear_blend" if merge_alignment_method == "Linear Blend" else "shift_scale"
                        
                        # Call the merge function
                        primary_output_path = merge_depth_segments.merge_depth_segments(
                            master_meta_path=master_meta_path,
                            output_path_arg=output_dir,
                            do_dithering=merge_dither,
                            dither_strength_factor=merge_dither_strength,
                            apply_gamma_correction=merge_gamma_correct,
                            gamma_value=merge_gamma_value,
                            use_percentile_norm=merge_percentile_norm,
                            norm_low_percentile=merge_norm_low_perc,
                            norm_high_percentile=merge_norm_high_perc,
                            output_format=out_fmt,
                            merge_alignment_method=align_method,
                            output_filename_override_base=merged_base_name,
                            enable_dual_output_robust_norm=enable_dual_output_robust_norm,
                            robust_norm_low_percentile=robust_norm_low_percentile,
                            robust_norm_high_percentile=robust_norm_high_percentile,
                            robust_norm_output_min=robust_norm_output_min,
                            robust_norm_output_max=robust_norm_output_max,
                            robust_output_suffix=robust_output_suffix,
                            is_depth_far_black=is_depth_far_black
                        )
                        
                        if primary_output_path:
                            logger.info(f"Re-merging completed successfully. Output: {primary_output_path}")
                        else:
                            logger.warning(f"Re-merging completed but no output path was returned for {original_basename}")
                        
                    except Exception as e:
                        logger.error(f"Error during re-merging for {original_basename}: {e}", exc_info=True)
                        # Continue with other files
                else:
                    logger.warning(f"Merge module not available, skipping re-merge for {original_basename}")
            
            progress(1.0, desc="Re-merging completed!")
            logger.info("Re-merging completed for all found metadata files")
            
            # CRITICAL: Clear stop_event after re-merge completes
            self.stop_event.clear()
            logger.debug("stop_event cleared after re-merge completion")
            
            return "Re-merging completed successfully!", 10

        except Exception as e:
            import traceback
            error_msg = f"Error during re-merge: {str(e)}"
            traceback_str = traceback.format_exc()

            logger.error("=" * 80)
            logger.error("ERROR during re-merge:")
            logger.error(error_msg)
            logger.error(traceback_str)
            logger.error("=" * 80)
            
            # CRITICAL: Clear stop_event after re-merge error
            self.stop_event.clear()
            logger.debug("stop_event cleared after re-merge error")

            return f"{error_msg}\n\nSee terminal for full traceback.", 0

    def clear_vram_memory(self):
        """Clear VRAM cache and return status message"""
        import logging
        import gc
        import torch
        logger = logging.getLogger(__name__)

        try:
            if not torch.cuda.is_available():
                logger.warning("CUDA not available. No VRAM to clear.")
                return "CUDA not available - no VRAM to clear"

            # Get VRAM usage before clearing
            allocated_before = torch.cuda.memory_allocated(0) / (1024**3)
            reserved_before = torch.cuda.memory_reserved(0) / (1024**3)

            # Clear CUDA cache and run garbage collection
            torch.cuda.empty_cache()
            gc.collect()

            # Get VRAM usage after clearing
            allocated_after = torch.cuda.memory_allocated(0) / (1024**3)
            reserved_after = torch.cuda.memory_reserved(0) / (1024**3)

            freed_reserved = reserved_before - reserved_after
            freed_allocated = allocated_before - allocated_after

            logger.info(f"VRAM cleared: Freed {freed_reserved:.2f} GB reserved ({reserved_before:.2f} → {reserved_after:.2f} GB)")
            logger.info(f"  Allocated: {allocated_before:.2f} → {allocated_after:.2f} GB")

            return f"✅ VRAM cleared: Freed {freed_reserved:.2f} GB (Reserved: {reserved_before:.2f} → {reserved_after:.2f} GB)"

        except Exception as e:
            logger.error(f"Error clearing VRAM: {e}", exc_info=True)
            return f"Error clearing VRAM: {str(e)}"
