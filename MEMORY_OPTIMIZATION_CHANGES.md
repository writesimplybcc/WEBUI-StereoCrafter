# Memory Optimization Changes for DepthCrafter

## Problem
RTX 6000 Ada (48GB VRAM) was running out of memory when processing a 127-frame 1080p video, crashing with:
```
torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 9.81 GiB. GPU 0 has a total capacity of 47.38 GiB of which 6.25 GiB is free.
```

## Root Causes
1. **Static VRAM configuration**: Settings were based only on total VRAM capacity, not actual available memory
2. **Aggressive VRAM settings**: 48GB+ GPUs were configured with decode_chunk_size=24 and window_size=200, which is too aggressive for high-resolution long videos
3. **Memory fragmentation**: PyTorch's default CUDA allocator can fragment memory over time
4. **Insufficient cleanup**: Intermediate tensors weren't being cleared during processing
5. **No pre-inference checks**: No validation of available memory before starting heavy operations

## Changes Made

### 1. Dynamic VRAM Configuration (`dependency/stereocrafter_util.py`)

**NEW: Real-time memory checking**
- Now checks both total capacity AND currently allocated memory
- Uses `effective_vram_gb = min(total_vram_gb, free_vram_gb + memory_allocated * 0.5)`
- Automatically downgrades settings if memory is already in use
- Logs detailed memory stats: total, allocated, reserved, free

**Example**: If you have 48GB total but 41GB is already allocated, it will use 24GB tier settings instead of 48GB tier settings.

**Reduced memory-intensive parameters for 48GB+ GPUs:**
- `decode_chunk_size`: 24 → 8 (66% reduction)
- `window_size`: 200 → 110 (45% reduction)
- `overlap`: 40 → 25 (37% reduction)
- `frames_chunk`: 40 → 25 (37% reduction)
- `batch_chunk_size`: 32 → 16 (50% reduction)

Also reduced settings for 24GB GPUs to improve stability.

**NEW: Helper functions added:**
- `check_vram_availability(required_gb, operation_name)`: Validates sufficient free VRAM before operations
- `get_current_vram_usage()`: Returns detailed VRAM statistics dictionary

### 2. Pre-Inference VRAM Validation (`depthcrafter/depthcrafter_logic.py`)

**NEW: Proactive memory checking**
- Checks available VRAM before starting inference
- Estimates required VRAM based on:
  - Number of frames
  - Resolution (normalized to 1080p baseline)
  - Base memory requirement (8GB for 100 frames at 1080p)
- Logs warnings if insufficient memory detected
- Suggests reducing window_size, overlap, or resolution

**Example log output:**
```
Pre-inference VRAM status: 6.25 GB free / 47.38 GB total
Estimated VRAM needed: 10.16 GB (frames: 127, resolution factor: 1.0)
WARNING: Low VRAM detected. Consider reducing window_size, overlap, or resolution.
```

### 3. Pipeline Memory Management (`depthcrafter/depth_crafter_ppl.py`)
Added aggressive memory cleanup:
- Clear intermediate tensors (`noise_pred`, `latent_model_input`, `noise_pred_uncond`) after each denoising step
- Delete segment tensors (`video_latents_current`, `video_embeddings_current`, `latents`) before moving to next segment
- Run `torch.cuda.empty_cache()` and `gc.collect()` after processing each segment
- Fixed flush_frequency calculation to use `max(1, overlap + 1)` to prevent division by zero

### 4. PyTorch Memory Allocator (`depthcrafter/depthcrafter_logic.py`)
- Set `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` to reduce memory fragmentation
- Added pre-inference memory cleanup (empty cache + garbage collection)
- Added post-inference memory cleanup

## Expected Results
These changes should:
1. **Dynamically adapt** to current memory pressure, not just total capacity
2. Reduce peak memory usage by 40-50%
3. Prevent memory fragmentation during long video processing
4. Provide early warnings when memory is insufficient
5. Allow 127-frame 1080p videos to process successfully on RTX 6000 Ada
6. Improve stability for all GPU tiers (12GB, 24GB, 48GB+)
7. Automatically downgrade settings if GPU is already under memory pressure

## How Dynamic Adjustment Works

### Scenario 1: Fresh GPU (No memory pressure)
- Total VRAM: 48GB
- Allocated: 1GB
- Free: 47GB (97.9%)
- **Strategy**: GPU mostly idle, use total capacity tier
- **Effective VRAM**: 48GB → Uses 48GB tier settings

### Scenario 2: GPU with existing workload (Your case)
- Total VRAM: 48GB
- Allocated: 41GB
- Free: 6.25GB (13.2%)
- **Strategy**: GPU under load, use free memory with 20% safety margin
- **Effective VRAM**: 6.25 * 1.2 = 7.5GB → Uses 8-12GB tier settings (ultra-conservative)

### Scenario 3: Moderate memory pressure
- Total VRAM: 48GB
- Allocated: 20GB
- Free: 28GB (58.3%)
- **Strategy**: GPU under load, use free memory with 20% safety margin
- **Effective VRAM**: 28 * 1.2 = 33.6GB → Uses 24-48GB tier settings

## Trade-offs
- Processing will be slightly slower due to smaller batch sizes
- More frequent memory cleanup adds minor overhead
- Conservative settings prioritize stability over speed
- Dynamic checking adds small initialization overhead

## Testing Recommendations
1. Test with the same 127-frame 1080p video that previously failed
2. Monitor VRAM usage with `nvidia-smi -l 1` during processing
3. Check logs for VRAM status messages and warnings
4. If still experiencing OOM:
   - Further reduce `decode_chunk_size` to 6
   - Reduce `window_size` to 90
   - Consider processing in smaller segments
5. For shorter videos (<60 frames) on fresh GPU, settings will automatically be more aggressive

## Monitoring VRAM Usage

You can now call these functions to check memory status:
```python
from dependency.stereocrafter_util import get_current_vram_usage, check_vram_availability

# Get detailed stats
stats = get_current_vram_usage()
print(f"Free: {stats['free']} GB, Total: {stats['total']} GB")

# Check if operation is safe
if check_vram_availability(10.0, "my_operation"):
    # Proceed with operation
    pass
```
