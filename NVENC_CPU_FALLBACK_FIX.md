# NVENC to CPU Automatic Fallback Fix

## Problem
When GPU encoding (NVENC) failed during video merging, the entire encoding process would stop, requiring manual intervention and resulting in no output files being written.

## Solution
Implemented an automatic retry mechanism that:
1. **Detects NVENC failures** during chunk processing
2. **Automatically restarts** with CPU encoding (libx264) from frame 0
3. **Preserves the workflow** without requiring user intervention
4. **Limits retries** to prevent infinite loops (max 1 CPU retry)

## How It Works

### Encoding Flow
```
Start Video Processing
    ↓
Attempt 1: NVENC encoding (if available)
    ↓
[If NVENC succeeds] → Finalize → Success
    ↓
[If NVENC fails] → Cleanup → Retry Attempt
    ↓
Attempt 2: CPU encoding (libx264)
    ↓
[If CPU succeeds] → Finalize → Success
    ↓
[If CPU fails] → Error → Next video
```

### Key Features

#### 1. **Retry Loop Structure**
```python
# Wrap video processing in a retry loop
max_cpu_retries = 1
cpu_retry_attempt = 0
processing_completed = False

while not processing_completed and cpu_retry_attempt <= max_cpu_retries:
    # Process all chunks
    for frame_start in range(0, num_frames, chunk_size):
        # Check FFmpeg health
        if ffmpeg_process.poll() is not None:
            # NVENC failed? Set flag and break
            if 'nvenc' in current_codec and not nvenc_failed:
                nvenc_failed_this_attempt = True
                break
    
    # After chunk loop, check if retry needed
    if nvenc_failed_this_attempt:
        cpu_retry_attempt += 1
        continue  # Retry with CPU
    else:
        processing_completed = True
```

#### 2. **Automatic CPU Fallback**
When NVENC fails:
- Clean up failed NVENC FFmpeg process
- Delete incomplete temp file
- Force CPU encoding: `sc_util.CUDA_AVAILABLE = False`
- Restart FFmpeg with libx264 codec
- Re-process all frames from beginning
- Log: "NVENC failed, retrying with CPU encoding (attempt 1/1)..."

#### 3. **State Management**
- `nvenc_failed_this_attempt`: Tracks if NVENC failed in current attempt
- `cpu_retry_attempt`: Counts retry attempts (prevents infinite loops)
- `processing_completed`: Indicates successful completion
- `frame_count`: Reset to 0 for each retry attempt

#### 4. **Proper Cleanup**
Each retry properly cleans up:
- Closes FFmpeg stdin with error handling
- Kills FFmpeg process
- Waits for process termination
- Deletes incomplete temp files
- Clears error buffers
- Resets frame counter

## Code Changes

### File: `stereocrafter_ui/merging/merging_ui.py`

#### Changes Made:

1. **Added retry loop variables** (around line 1317):
```python
# NVENC fallback: track if we need to retry with CPU
nvenc_failed = False
nvenc_failed_at_frame = 0  # Track where NVENC failed
max_cpu_retries = 1  # Only retry once with CPU to avoid infinite loops
cpu_retry_attempt = 0

# Wrap video processing in a retry loop for NVENC->CPU fallback
processing_completed = False
while not processing_completed and cpu_retry_attempt <= max_cpu_retries:
```

2. **Restructured FFmpeg initialization** (inside while loop):
```python
# Re-initialize FFmpeg process for each attempt
if cpu_retry_attempt > 0:
    sc_util.CUDA_AVAILABLE = False  # Force CPU
    logger.info(f"Forcing CPU encoding for retry attempt...")

ffmpeg_process = start_ffmpeg_pipe_process(...)

if cpu_retry_attempt == 0:
    sc_util.CUDA_AVAILABLE = original_cuda  # Restore after first attempt
```

3. **Simplified NVENC failure detection** (in chunk loop):
```python
if 'nvenc' in current_codec and not nvenc_failed:
    nvenc_failed = True
    nvenc_failed_this_attempt = True
    nvenc_failed_at_frame = frame_count
    logger.warning(f"NVENC ({current_codec}) failed at frame {frame_count}. Will retry with CPU...")
    
    # Clean up failed process
    # ...cleanup code...
    
    break  # Exit chunk loop, while loop will handle retry
```

4. **Added retry logic after chunk loop** (around line 1620):
```python
# Check if we need to retry with CPU encoding
if nvenc_failed_this_attempt and not self.stop_event.is_set():
    cpu_retry_attempt += 1
    logger.warning(f"NVENC failed, retrying with CPU encoding (attempt {cpu_retry_attempt}/{max_cpu_retries})...")
    
    # Clean up before retry
    # ...cleanup code...
    
    continue  # Continue the while loop to retry with CPU
else:
    processing_completed = True
```

5. **Added completion verification** (end of while loop):
```python
# Only proceed if processing was successful
if processing_completed and frame_count == num_frames:
    yield f"Completed: {base_name}", ((i+1)/total_videos*100)
elif not processing_completed:
    logger.warning(f"Video {base_name} processing did not complete successfully")
else:
    logger.warning(f"Video {base_name} incomplete: {frame_count}/{num_frames} frames")
```

## Benefits

### 1. **Automatic Recovery**
- No manual intervention required
- Users don't need to restart the process
- Seamless fallback from GPU to CPU

### 2. **Reliability**
- CPU encoding (libx264) is more stable for high-resolution videos
- Handles NVENC driver issues, memory problems, codec incompatibilities
- Proper cleanup prevents resource leaks

### 3. **User Experience**
- Clear logging: "NVENC failed, retrying with CPU encoding..."
- Progress continues without interruption
- Final output is successfully encoded video

### 4. **Safety**
- Limited to 1 retry attempt (prevents infinite loops)
- Proper cleanup of failed attempts
- Maintains stop_event support for user cancellation

## When Fallback Triggers

NVENC fallback activates when:
- FFmpeg process exits unexpectedly during NVENC encoding
- NVENC driver errors
- GPU memory issues
- Codec incompatibility with specific video parameters
- Any error where `ffmpeg_process.poll() is not None` AND codec contains "nvenc"

## Performance Impact

- **NVENC Success**: No performance impact, uses fast GPU encoding
- **NVENC Failure**: 
  - Re-encodes entire video with CPU (slower)
  - Adds ~10-30 seconds for cleanup and restart
  - Still completes the job instead of failing

## Testing

To verify the fix works:

1. **Normal NVENC Success**:
   - Log shows: "NVENC GPU encoding enabled"
   - Completes normally with GPU encoding
   - No retry messages

2. **NVENC Failure → CPU Success**:
   - Log shows: "NVENC (hevc_nvenc) failed at frame X/Y. Will retry with CPU..."
   - Log shows: "NVENC failed, retrying with CPU encoding (attempt 1/1)..."
   - Log shows: "Restarting FFmpeg with CPU encoding (libx264)..."
   - Video completes successfully with CPU encoding

3. **Both NVENC and CPU Fail**:
   - Log shows NVENC failure
   - Log shows CPU retry failure
   - Error: "FFmpeg crashed at frame X"
   - Moves to next video

## Limitations

1. **Single Retry**: Only retries once with CPU to avoid infinite loops
2. **Full Re-encode**: Must restart from frame 0 (can't resume mid-video)
3. **Time Cost**: CPU encoding is significantly slower than NVENC for 4K/8K videos

## Future Enhancements

Potential improvements:
1. **Checkpoint resume**: Save encoded frames to temp file and resume from checkpoint
2. **Multiple retry strategies**: Try different NVENC parameters before falling back to CPU
3. **Partial chunk saving**: Only re-encode failed chunks instead of full video
4. **Adaptive retry**: Detect failure type and choose best recovery strategy
