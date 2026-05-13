"""
StereoCrafter Combined WebUI
A unified interface for depth estimation, splatting, inpainting, and merging operations.

This is the main entry point that orchestrates all UI components.
"""

import sys
import os
import argparse
sys.path.insert(0, os.path.dirname(__file__))

import gradio as gr
import torch
import dependency.stereocrafter_util as sc_util
from dependency.stereocrafter_util import check_cuda_availability

# Import UI components from the modular structure
from stereocrafter_ui.depthcrafter import DepthCrafterWebUI
from stereocrafter_ui.splatting import SplatterWebUI
from stereocrafter_ui.inpainting import InpaintingWebUI
from stereocrafter_ui.merging import MergingWebUI
from stereocrafter_ui.file_manager import FileManagerUI

def get_gpu_info():
    """Get GPU and VRAM information"""
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        vram_total = torch.cuda.get_device_properties(0).total_memory / (1024**3)  # Convert to GB
        vram_used = torch.cuda.memory_reserved(0) / (1024**3)  # Currently reserved in GB
        return f"GPU: {gpu_name} | Total VRAM: {vram_total:.1f} GB | Reserved VRAM: {vram_used:.1f} GB"
    else:
        return "GPU: Not available (using CPU) | VRAM: N/A"


class CombinedWebUI:
    """
    Main orchestrator for the StereoCrafter WebUI.
    Combines all UI components into a single tabbed interface.
    """

    def __init__(self):
        # Initialize all components
        self.depthcrafter_gui = DepthCrafterWebUI()
        self.splatting_gui = SplatterWebUI()
        self.inpainting_gui = InpaintingWebUI()
        self.merging_gui = MergingWebUI()
        self.file_manager_gui = FileManagerUI()
        
    def create_interface(self):
        """Creates the combined Gradio interface with all tabs"""
        with gr.Blocks(title="StereoCrafter Combined WebUI") as interface:

            gr.Markdown("# StereoCrafter Combined WebUI")
            gr.Markdown("A unified interface for depth estimation, splatting, inpainting, and merging operations.")
            # Display GPU and VRAM info below the title
            gpu_info = get_gpu_info()
            gr.Markdown(f"## {gpu_info}")

            # Global Hugging Face Authentication
            with gr.Group():
                gr.Markdown("### Hugging Face Authentication")
                hf_token = gr.Textbox(
                    label="Hugging Face Token",
                    value=os.environ.get("HF_TOKEN", ""),
                    info="Enter your Hugging Face access token for downloading gated models like Stable Video Diffusion."
                )

            with gr.Tab("DepthCrafter"):
                self.depthcrafter_gui.create_interface()

            with gr.Tab("Splatting"):
                self.splatting_gui.create_interface()

            with gr.Tab("Inpainting"):
                self.inpainting_gui.create_interface(hf_token)

            with gr.Tab("Merging"):
                self.merging_gui.create_interface()

            with gr.Tab("📂 File Manager"):
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### Current File Manager")
                        self.file_manager_gui.create_interface()
                    with gr.Column():
                         gr.Markdown("### File Browser (External)")
                         gr.Markdown("File Browser runs on a separate port. Click below to access:")
                         filebrowser_url = "http://localhost:8080"  # Adjust port as needed
                         gr.Markdown(f"[Open File Browser]({filebrowser_url})")
                         gr.Button("🔗 Launch File Browser", link=filebrowser_url)

        return interface


def launch(share=False, server_name="0.0.0.0", server_port=7860):
    """Launch the combined WebUI"""
    import os
    os.environ['GRADIO_ANALYTICS_ENABLED'] = 'False'
    app = CombinedWebUI()
    interface = app.create_interface()
    interface.launch(share=share, server_name=server_name, server_port=server_port)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Launch StereoCrafter WebUI")
    parser.add_argument("--share", action="store_true", help="Create a public link")
    parser.add_argument("--server-name", default="0.0.0.0", help="Server name")
    parser.add_argument("--server-port", type=int, default=7860, help="Server port")
    args = parser.parse_args()

    # Set the module-level CUDA_AVAILABLE flag
    sc_util.CUDA_AVAILABLE = check_cuda_availability()
    print(f"[DEBUG] CUDA_AVAILABLE set to: {sc_util.CUDA_AVAILABLE}")
    
    # Initialize CUDA and clear cache before UI initialization
    # This ensures get_vram_config() gets accurate memory readings
    if torch.cuda.is_available():
        try:
            print("[DEBUG] Initializing CUDA...")
            torch.cuda.init()
            torch.cuda.empty_cache()
            print(f"[DEBUG] CUDA initialized. GPU: {torch.cuda.get_device_name(0)}")
            print(f"[DEBUG] Total VRAM: {torch.cuda.get_device_properties(0).total_memory / (1024**3):.2f} GB")
        except Exception as e:
            print(f"[ERROR] CUDA initialization failed: {e}")
    else:
        print("[DEBUG] CUDA not available.")
    
    launch(share=args.share, server_name=args.server_name, server_port=args.server_port)
