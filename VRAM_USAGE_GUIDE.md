# VRAM Usage Guide - DepthCrafter

## Quick Reference: What Settings Will Be Used?

The system now **dynamically** checks your GPU's available memory and adjusts settings automatically.

### How It Works

1. **Checks total VRAM capacity** (e.g., 48GB for RTX 6000 Ada)
2. **Checks currently allocated memory** (e.g., 41GB if other processes are running)
3. **Calculates free VRAM** (e.g., 6.25GB)
4. **Determines strategy**:
   - If GPU >80% free → Use total capacity tier (GPU is idle)
   - If GPU <80% free → Use free memory tier with 20% safety margin
5. **Selects appropriate tier** based on effective VRAM

### Settings by Tier

| Effective VRAM | decode_chunk | window_size | overlap | Typical Use Case |
|----------------|--------------|-------------|---------|------------------|
| **< 8GB**      | 2            | 50          | 8       | Very low memory / heavy GPU load |
| **8-12GB**     | 3            | 60          | 10      | Low memory / moderate GPU load |
| **12-24GB**    | 6            | 80          | 15      | RTX 3090, RTX 4080, or busy 48GB GPU |
| **24-48GB**    | 10           | 110         | 25      | RTX 4090, A5000 |
| **48GB+**      | 8            | 110         | 25      | RTX 6000 Ada (mostly idle) |

### Real-World Examples

#### Example 1: Fresh RTX 6000 Ada (48GB, mostly idle)
```
Total: 48GB, Allocated: 1GB, Free: 47GB
Free percentage: 97.9% (>80% threshold)
Strategy: Use total capacity tier
Effective VRAM: 48GB
→ Uses 48GB tier: decode_chunk=8, window_size=110
```

#### Example 2: RTX 6000 Ada with Background Tasks (Your Case)
```
Total: 48GB, Allocated: 41GB, Free: 6.25GB
Free percentage: 13.2% (<80% threshold)
Strategy: Use free memory with 20% safety margin
Effective VRAM: 6.25 * 1.2 = 7.5GB
→ Uses 8-12GB tier: decode_chunk=3, window_size=60
```

#### Example 3: RTX 6000 Ada with Moderate Load
```
Total: 48GB, Allocated: 20GB, Free: 28GB
Free percentage: 58.3% (<80% threshold)
Strategy: Use free memory with 20% safety margin
Effective VRAM: 28 * 1.2 = 33.6GB
→ Uses 24-48GB tier: decode_chunk=10, window_size=110
```

#### Example 4: RTX 4090 (24GB) Running Other Models
```
Total: 24GB, Allocated: 18GB, Free: 6GB
Free percentage: 25% (<80% threshold)
Strategy: Use free memory with 20% safety margin
Effective VRAM: 6 * 1.2 = 7.2GB
→ Uses 8-12GB tier: decode_chunk=3, window_size=60
```

## What You'll See in Logs

When processing starts, you'll see:
```
GPU: NVIDIA RTX 6000 Ada Generation
Total VRAM: 47.38 GB
Allocated: 41.12 GB
Reserved: 41.64 GB
Free: 6.26 GB
GPU under load (13.2% free), using free memory tier with safety margin
Effective VRAM for config selection: 7.51 GB
Using 8-12GB tier settings
```

Before inference:
```
Pre-inference VRAM status: 6.26 GB free / 47.38 GB total
Estimated VRAM needed: 10.16 GB (frames: 127, resolution factor: 1.0)
WARNING: Low VRAM detected. Consider reducing window_size, overlap, or resolution.
```

## Troubleshooting OOM Errors

### If you still get OOM errors:

1. **Close other GPU applications**
   - Check with `nvidia-smi` what else is using VRAM
   - Close unnecessary applications (browsers with hardware acceleration, other ML models, etc.)

2. **Reduce resolution**
   - Process at 720p instead of 1080p
   - Upscale later if needed

3. **Process in segments**
   - Split your video into smaller chunks
   - Process each chunk separately
   - Merge results afterward

4. **Manual override** (if needed)
   - Edit `dependency/stereocrafter_util.py`
   - Reduce values in the tier that matches your effective VRAM
   - Example: Change `decode_chunk_size` from 10 to 6

### Memory-Saving Tips

- **Restart Python/Jupyter** before processing to clear any lingering allocations
- **Use CPU offload** if available in settings (trades speed for memory)
- **Process shorter videos** - memory usage scales with frame count
- **Lower resolution** - memory usage scales with pixel count

## Monitoring During Processing

### Using nvidia-smi
```bash
# Watch VRAM usage in real-time (updates every 1 second)
nvidia-smi -l 1

# Or use the detailed monitoring mode
watch -n 1 nvidia-smi
```

### What to Watch For
- **Memory-Usage**: Should stay below 90% of total
- **Volatile GPU-Util**: Will spike during processing
- **Temperature**: Should stay under 85°C

### Healthy Processing Pattern
```
Initial:  6GB allocated
Loading:  15GB allocated (loading models)
Encoding: 25GB allocated (encoding frames)
Inference: 35-40GB allocated (peak usage)
Decoding: 30GB allocated (decoding results)
Cleanup:  6GB allocated (back to baseline)
```

## Performance vs Memory Trade-offs

| Setting | Memory Impact | Speed Impact | When to Use |
|---------|---------------|--------------|-------------|
| **decode_chunk_size** | High | Medium | Reduce first if OOM |
| **window_size** | Very High | High | Reduce if still OOM |
| **overlap** | Medium | Low | Affects quality, reduce carefully |
| **resolution** | Very High | Medium | Last resort, affects output quality |

## Best Practices

1. **Let the system auto-configure** - It will choose appropriate settings
2. **Monitor first run** - Watch VRAM usage to understand your baseline
3. **Keep GPU clean** - Close unnecessary applications before processing
4. **Process during off-hours** - If sharing GPU with others
5. **Check logs** - They tell you exactly what settings are being used

## Getting Help

If you continue to experience OOM errors after these optimizations:

1. Share your log output showing:
   - GPU model and total VRAM
   - Allocated/Free VRAM at start
   - Effective VRAM tier selected
   - Video specs (frames, resolution)

2. Try the most conservative settings manually:
   ```python
   # In your processing script
   decode_chunk_size = 2
   window_size = 60
   overlap = 10
   ```

3. Consider processing in smaller segments or at lower resolution
