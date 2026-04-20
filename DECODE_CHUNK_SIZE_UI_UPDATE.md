# Decode Chunk Size UI Update

## Summary

Added a user-controllable **Decode Chunk Size** slider to the DepthCrafter WebUI, allowing manual override of the automatic VRAM-based detection.

## Changes Made

### 1. WebUI Component (`stereocrafter_ui/depthcrafter/depthcrafter_ui.py`)

**Added Slider Definition** (Line ~135):
```python
self.decode_chunk_size = gr.Slider(
    2, 32, value=vram_config['decode_chunk_size'], step=1,
    label="Decode Chunk Size",
    info="Number of frames to decode at once during VAE decoding. Higher values = faster processing but more VRAM usage. Auto-detected based on your GPU (RTX 6000 Ada = 16). Reduce if you encounter OOM errors."
)
```

**Added to UI Layout** (Line ~327):
```python
self.decode_chunk_size.render()
```

**Added to Event Handlers**:
- Added to `start_btn.click()` inputs list
- Added to function return list
- Extracted in `start_processing()` method
- Passed to both segment and full-video `demo.run()` calls

### 2. Logic Component (`depthcrafter/depthcrafter_logic.py`)

**Updated `run()` Method** (Line 667):
```python
def run(self,
        video_path_or_frames_or_info: Union[str, np.ndarray, dict],
        num_denoising_steps: int, guidance_scale: float,
        base_output_folder: str, gui_window_size: int, gui_overlap: int,
        gui_decode_chunk_size: int,  # ← NEW PARAMETER
        process_length_for_read_full_video: int, target_height: int, target_width: int,
        ...
```

**Updated `_internal_infer()` Method** (Line 546):
```python
def _internal_infer(self,
                    ...
                    pipe_call_window_size: int, pipe_call_overlap: int,
                    pipe_call_decode_chunk_size: int,  # ← NEW PARAMETER
                    segment_job_info: Optional[dict] = None,
                    ...
```

**Updated `_perform_inference()` Method** (Line 354):
```python
def _perform_inference(self, actual_frames_to_process: np.ndarray,
                       guidance_scale: float, num_denoising_steps: int,
                       pipe_call_window_size: int, pipe_call_overlap: int,
                       pipe_call_decode_chunk_size: int,  # ← NEW PARAMETER
                       segment_job_info: Optional[dict],
                       actual_processed_height: int, actual_processed_width: int
```

**Updated Pipeline Call** (Line 391):
```python
res = self.pipe(
    actual_frames_to_process,
    height=actual_processed_height,
    width=actual_processed_width,
    output_type="np",
    guidance_scale=guidance_scale,
    num_inference_steps=num_denoising_steps,
    window_size=current_pipe_window_for_call,
    overlap=current_pipe_overlap_for_call,
    decode_chunk_size=current_decode_chunk_size,  # ← PASSED TO PIPELINE
)
```

## Default Values by GPU

The slider auto-detects and sets the optimal value based on your GPU:

| GPU Tier | GPU Examples | Default `decode_chunk_size` |
|----------|--------------|----------------------------|
| **48GB+** | RTX 6000 Ada | **16** |
| 24GB | RTX 3090, RTX 4090 | 14 |
| 12GB | RTX 3060 12GB | 14 |
| 8-12GB | GTX 1080 Ti, RTX 2060 | 10 |
| < 8GB | GTX 1060, GTX 1650 | 8 |
| Minimal | Integrated GPUs | 4 |

## Recommended Settings for 1440p Video

| Video Length | Complexity | Recommended `decode_chunk_size` |
|--------------|------------|--------------------------------|
| < 300 frames | Normal | 16 (default) |
| 300-600 frames | Moderate | 11-14 |
| 600-1000 frames | High | 8-11 |
| 1000+ frames | Very High | 6-8 |

## When to Adjust

**Increase `decode_chunk_size` if:**
- You have plenty of free VRAM (> 30GB on RTX 6000 Ada)
- Processing short videos (< 300 frames)
- Want maximum processing speed

**Decrease `decode_chunk_size` if:**
- Encountering OOM (Out of Memory) errors
- Processing very long videos (1000+ frames)
- Processing 4K or higher resolution
- System has other GPU workloads running

## Location in WebUI

The new slider appears in the **Frame & Segment Control** section, below the Overlap slider:

```
Frame & Segment Control
├── Window Size
├── Overlap
├── Decode Chunk Size ← NEW
├── Target FPS
├── Process Max Frames
├── Save Sidecar JSON
└── Process as Segments
```

## Technical Notes

1. The value is passed directly to the Diffusers pipeline's `decode_chunk_size` parameter
2. Controls VAE decoding batch size (how many frames are decoded at once)
3. Higher values = faster but more VRAM
4. Works alongside the existing adaptive scaling system
5. User-provided value overrides automatic detection

## Testing

After starting the WebUI, verify the slider appears and:
1. Shows the correct default value for your GPU (16 for RTX 6000 Ada)
2. Can be adjusted between 2-32
3. The value is logged when processing starts
4. Processing completes successfully with custom values

## Files Modified

1. `stereocrafter_ui/depthcrafter/depthcrafter_ui.py` - WebUI component
2. `depthcrafter/depthcrafter_logic.py` - Processing logic

## Backward Compatibility

✅ Fully backward compatible - existing configurations continue to work with auto-detected values.
