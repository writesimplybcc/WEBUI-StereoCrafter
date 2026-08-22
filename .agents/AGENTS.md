# Hardware Notes

- **RTX Pro 6000**: This card has 96GB of VRAM (not 48GB) and 119 TFLOPS of compute performance. It is highly capable of handling extremely large temporal batches (e.g., 24+ frames) at 4K resolution in Stable Video Diffusion Inpainting without needing to rely on spatial tiling.
- **RTX 6000 Ada**: This card has 48GB of VRAM. For optimal performance without Out-Of-Memory (OOM) errors when processing **4K input videos** (using a 1920x1080 proxy grid where the AI processes a 960x540 quadrant), use the following limits:
  - **Inpainting Tab**: Max `Frames Chunk` = 20, `Decode Chunk Size` = 10, `CPU Offload Type` = model.
  - **Merging Tab**: Max `Batch Chunk Size` = 36 (48 will OOM). CPU decoding/encoding requires a high-end processor like Threadripper for optimal stitching speeds.
