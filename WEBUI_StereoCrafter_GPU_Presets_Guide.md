# WEBUI StereoCrafter GPU Presets Guide

This guide provides optimized presets for StereoCrafter processes based on GPU VRAM tiers. Settings are auto-detected where possible, but manual overrides can be applied in the UI. All recommendations prioritize speed, quality, and stability.

## GPU Categories
- **Low VRAM**: RTX 3060 12GB (balanced performance for mainstream users).
- **Mid VRAM**: RTX 6000 Ada 48GB (high-end workstation GPU).
- **High CUDA Mid VRAM**: RTX 5090 32GB (next-gen mid-range).
- **High CUDA High VRAM**: RTX 6000 Pro 96GB (ultra-high-end workstation).

## DepthCrafter (Depth Estimation)
Processes videos into depth maps.

### RTX 3060 12GB (Low VRAM)
- **CPU Offload**: "model" (balanced for 12GB).
- **Max Resolution**: 1024x1024.
- **xFormers**: Enabled.
- **cuDNN Benchmark**: Enabled.
- **Inference Steps**: 5-10.
- **Guidance Scale**: 1.0-2.0.
- **Segments**: Enabled for long videos.

### RTX 6000 Ada 48GB (Mid VRAM)
- **CPU Offload**: "none".
- **Max Resolution**: 1536x1536-2048x2048.
- **xFormers**: Enabled.
- **cuDNN Benchmark**: Enabled.
- **Inference Steps**: 5-15.
- **Guidance Scale**: 1.0-3.0.
- **Segments**: Disabled for short videos.

### RTX 5090 32GB (High CUDA Mid VRAM)
- **CPU Offload**: "none".
- **Max Resolution**: 1024x1024-1536x1536.
- **xFormers**: Enabled.
- **cuDNN Benchmark**: Enabled.
- **Inference Steps**: 5-10.
- **Guidance Scale**: 1.0-2.0.
- **Segments**: Optional.

### RTX 6000 Pro 96GB (High CUDA High VRAM)
- **CPU Offload**: "none".
- **Max Resolution**: 2048x2048-4096x4096.
- **xFormers**: Enabled.
- **cuDNN Benchmark**: Enabled.
- **Inference Steps**: 3-10.
- **Guidance Scale**: 0.5-2.0.
- **Segments**: Disabled.

## Splatting (3D Reconstruction)
Creates 3D splats from depth/video data.

### RTX 3060 12GB (Low VRAM)
- **Resolution**: Up to 2048x2048.
- **CPU Offload**: "model".
- **xFormers/cuDNN**: Enabled.
- **Other**: Standard quality; enable downscaling for large inputs.

### RTX 6000 Ada 48GB (Mid VRAM)
- **Resolution**: 7680x4320 (8K hires), 2560x1440 (4K lowres).
- **CPU Offload**: "none".
- **xFormers/cuDNN**: Enabled.
- **Other**: High quality; test limits.

### RTX 5090 32GB (High CUDA Mid VRAM)
- **Resolution**: 7680x4320 (8K hires), 2560x1440 (4K lowres).
- **CPU Offload**: "none".
- **xFormers/cuDNN**: Enabled.
- **Other**: Max quality settings.

### RTX 6000 Pro 96GB (High CUDA High VRAM)
- **Resolution**: Up to 8192x4608+ (test for higher).
- **CPU Offload**: "none".
- **xFormers/cuDNN**: Enabled.
- **Other**: Ultra-high quality; disable downscaling.

## Inpainting (Video Inpainting)
Fills in missing/masked areas in videos.

### RTX 3060 12GB (Low VRAM)
- **Resolution**: Up to 1024x1024.
- **CPU Offload**: "none".
- **xFormers/cuDNN**: Enabled.
- **Inference Steps**: 10-20.
- **Guidance Scale**: 7.5-12.5.

### RTX 6000 Ada 48GB (Mid VRAM)
- **Resolution**: 7680x2160.
- **CPU Offload**: "none".
- **xFormers/cuDNN**: Enabled.
- **Inference Steps**: 15-25.
- **Guidance Scale**: 10.0-15.0.

### RTX 5090 32GB (High CUDA Mid VRAM)
- **Resolution**: 7680x2160.
- **CPU Offload**: "none".
- **xFormers/cuDNN**: Enabled.
- **Inference Steps**: 15-25.
- **Guidance Scale**: 10.0-15.0.

### RTX 6000 Pro 96GB (High CUDA High VRAM)
- **Resolution**: Up to 8192x4320+.
- **CPU Offload**: "none".
- **xFormers/cuDNN**: Enabled.
- **Inference Steps**: 20-30.
- **Guidance Scale**: 12.5-20.0.

## Merging (Output Merging)
Combines processed segments into final outputs.

### RTX 3060 12GB (Low VRAM)
- **Resolution**: Unlimited (CPU-bound).
- **CPU Offload**: "none".
- **Other**: Default settings; enable gamma correction.

### RTX 6000 Ada 48GB (Mid VRAM)
- **Resolution**: Unlimited.
- **CPU Offload**: "none".
- **Other**: Enable percentile normalization.

### RTX 5090 32GB (High CUDA Mid VRAM)
- **Resolution**: Unlimited.
- **CPU Offload**: "none".
- **Other**: Enable dithering and gamma.

### RTX 6000 Pro 96GB (High CUDA High VRAM)
- **Resolution**: Unlimited; batch large merges.
- **CPU Offload**: "none".
- **Other**: All quality options enabled.

## General Tips
- **Auto-Detection**: The UI detects GPU VRAM and applies presets automatically.
- **Overrides**: Manually adjust in the WEBUI for custom needs.
- **Performance**: Enable xFormers and cuDNN for speed; monitor GPU usage.
- **Testing**: Start conservative and scale up based on your workload.
- **Updates**: Presets based on tested hardware; re-test for newer GPUs.

For issues or updates, refer to the codebase or contact support.