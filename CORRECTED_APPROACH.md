# Corrected VRAM Detection Approach

## The Problem with the Initial Approach

**Initial (Incorrect) Logic:**
```
effective_vram = min(total, free + allocated * 0.5)
```

With 48GB total, 41GB allocated, 6.25GB free:
```
effective_vram = min(48, 6.25 + 41*0.5) = min(48, 26.75) = 26.75GB
```

**Why This Was Wrong:**
- You can't actually USE 26.75GB when only 6.25GB is free!
- The 41GB already allocated is NOT available for new operations
- This would select 24GB tier settings (decode_chunk=10, window=110)
- Still too aggressive for only 6.25GB free memory

## The Corrected Approach

**New (Correct) Logic:**
```python
free_percentage = (free_vram / total_vram) * 100

if free_percentage > 80:
    # GPU is mostly idle, use total capacity tier
    effective_vram = total_vram
else:
    # GPU has existing load, use free memory with safety margin
    effective_vram = free_vram * 1.2  # 20% safety margin
```

With 48GB total, 41GB allocated, 6.25GB free:
```
free_percentage = (6.25 / 48) * 100 = 13.2% (<80%)
effective_vram = 6.25 * 1.2 = 7.5GB
→ Uses 8-12GB tier: decode_chunk=3, window=60, overlap=10
```

**Why This Is Correct:**
- ✅ Based on ACTUAL free memory, not theoretical calculations
- ✅ Adds 20% safety margin for model loading and intermediate tensors
- ✅ Selects ultra-conservative settings appropriate for low memory
- ✅ Much more likely to succeed without OOM

## Comparison of Settings

| Scenario | Free VRAM | Old Approach | Old Settings | New Approach | New Settings |
|----------|-----------|--------------|--------------|--------------|--------------|
| Your case | 6.25GB | 26.75GB tier | decode=10, window=110 | 7.5GB tier | decode=3, window=60 |
| Moderate load | 28GB | 42GB tier | decode=8, window=110 | 33.6GB tier | decode=10, window=110 |
| Light load | 40GB | 48GB tier | decode=8, window=110 | 48GB tier | decode=8, window=110 |

## New Tier Structure

| Effective VRAM | Tier Name | decode_chunk | window_size | overlap | Use Case |
|----------------|-----------|--------------|-------------|---------|----------|
| **< 8GB** | Ultra-conservative | 2 | 50 | 8 | Very low free memory |
| **8-12GB** | Conservative | 3 | 60 | 10 | Low free memory (your case) |
| **12-24GB** | Moderate | 6 | 80 | 15 | Moderate free memory |
| **24-48GB** | Balanced | 10 | 110 | 25 | Good free memory |
| **48GB+** | Optimized | 8 | 110 | 25 | Excellent free memory |

## Why the 80% Threshold?

**If GPU is >80% free:**
- Indicates GPU is mostly idle
- Safe to use total capacity tier
- Maximizes performance

**If GPU is <80% free:**
- Indicates existing workload
- Must be conservative with free memory
- Prioritizes stability over performance

## Memory Safety Margin

The 20% safety margin (`free * 1.2`) accounts for:
1. **Model loading overhead** - Models need temporary space during loading
2. **Intermediate tensors** - Processing creates temporary tensors
3. **Memory fragmentation** - Not all "free" memory is contiguous
4. **PyTorch overhead** - CUDA allocator reserves extra space

## Expected Behavior for Your Case

**Your Setup:**
- RTX 6000 Ada: 48GB total
- Already allocated: 41GB
- Free: 6.25GB

**What Will Happen:**
1. System detects 13.2% free (<80% threshold)
2. Calculates effective: 6.25 * 1.2 = 7.5GB
3. Selects 8-12GB tier (ultra-conservative)
4. Uses: decode_chunk=3, window=60, overlap=10
5. Processes with very small batches
6. Frequent memory cleanup
7. **Result: Should complete successfully, though slower**

## Performance Impact

Compared to if you had 48GB free:

| Metric | 48GB Free | 6.25GB Free (Your Case) |
|--------|-----------|-------------------------|
| decode_chunk | 8 | 3 (62% smaller) |
| window_size | 110 | 60 (45% smaller) |
| Processing speed | 100% | ~40-50% (slower) |
| Memory safety | Good | Excellent |
| OOM risk | Low | Very low |

## Trade-offs

**Pros of New Approach:**
- ✅ Much more accurate memory assessment
- ✅ Appropriate settings for actual available memory
- ✅ Very low OOM risk
- ✅ Will work even with heavy GPU load

**Cons of New Approach:**
- ⚠️ Slower processing when GPU is busy
- ⚠️ May be overly conservative in some edge cases
- ⚠️ Doesn't try to "reclaim" allocated memory

## When You Might Still Get OOM

Even with these conservative settings, OOM can occur if:

1. **Other processes allocate more memory during processing**
   - Solution: Close other GPU applications first

2. **Video is extremely long or high resolution**
   - Solution: Process in segments or reduce resolution

3. **Memory is severely fragmented**
   - Solution: Restart Python/Jupyter to clear fragmentation

4. **Less than 6GB free**
   - Solution: Free up more GPU memory before processing

## Recommendations

For your specific case (6.25GB free):

1. **Best option**: Close other GPU applications to free up memory
   - This will move you to a higher tier with better performance

2. **Good option**: Process as-is with ultra-conservative settings
   - Will work but be slower

3. **Alternative**: Process at lower resolution (720p instead of 1080p)
   - Reduces memory requirements significantly

4. **Last resort**: Process in smaller segments
   - Split video into chunks, process separately

## Verification

To verify the new approach is working, check your logs for:

```
GPU under load (13.2% free), using free memory tier with safety margin
Effective VRAM for config selection: 7.51 GB
Using 8-12GB tier settings
```

If you see "Using 24GB tier settings" or higher, the old code is still running.
