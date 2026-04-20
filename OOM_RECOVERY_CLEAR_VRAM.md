# OOM Error Recovery: Clear VRAM Button

## Overview

Enhanced memory management with **automatic OOM (Out-Of-Memory) error detection** and **one-click recovery** options.

## Features

### 1. Clear VRAM Button (Always Available)

**Location:** Control panel, between "Cancel" and "Re-Merge Segments"

**What it does:**
- Clears PyTorch CUDA cache
- Runs Python garbage collection
- Shows how much VRAM was freed
- Displays before/after memory statistics

**Usage:** Click anytime to free VRAM without restarting the GUI

---

### 2. Automatic OOM Error Detection

When a CUDA Out-Of-Memory error occurs:

1. **Error is caught immediately**
2. **VRAM is automatically cleared**
3. **Recovery dialog appears** with options
4. **Processing pauses** until user decides

---

### 3. OOM Recovery Dialog

When OOM is detected, you'll see:

```
🔴 Out-Of-Memory (OOM) Error

Failed to process: my_video.mp4

✅ Emergency VRAM cleared: 12.45 GB
📊 Current free VRAM: 18.32 GB

💡 Recommended Actions:
  • Current: window_size=110, overlap=25
  • Suggested: window_size=77, overlap=17

Choose an option:

[⚡ Auto-Adjust & Continue] [✋ Manual Adjustment] [❌ Stop Processing]
```

#### Option 1: ⚡ Auto-Adjust & Continue

**What it does:**
- Reduces `window_size` by 30%
- Reduces `overlap` by 30%
- Updates GUI sliders automatically
- Ready to retry with one click

**Example:**
```
Before: window_size=110, overlap=25
After:  window_size=77, overlap=17
```

**Next step:** Click "Start" to retry with new settings

---

#### Option 2: ✋ Manual Adjustment

**What it does:**
- Clears VRAM (already done)
- Shows recommendations
- Lets you choose custom values

**When to use:**
- You want fine-grained control
- Auto-adjust is too aggressive
- You want to reduce resolution instead

**Recommendations shown:**
- Suggested window_size/overlap values
- Alternative: reduce resolution
- Alternative: process in segments

---

#### Option 3: ❌ Stop Processing

**What it does:**
- Stops all processing
- Clears VRAM
- Returns to idle state

**When to use:**
- Need to close other GPU applications
- Want to reconsider approach
- Multiple OOM errors occurred

---

## How It Works

### OOM Detection Flow

```
Processing video...
  ↓
CUDA Out-Of-Memory error
  ↓
Error caught by exception handler
  ↓
VRAM automatically cleared
  ↓
Status shows: "🔴 OOM Error: video_name"
  ↓
Recovery dialog appears (100ms delay)
  ↓
User chooses recovery option
  ↓
Processing continues or stops
```

### Code Flow

**File:** `depthcrafter_gui_seg.py`

```python
# 1. OOM Detection (line ~1011)
except torch.cuda.OutOfMemoryError as e:
    returned_job_specific_metadata["status"] = "oom_error"
    self.status_message_var.set(f"🔴 OOM Error: {original_basename}")
    
    # Show OOM recovery dialog
    self.root.after(100, lambda: self._handle_oom_error(...))

# 2. OOM Handler (line ~1029)
def _handle_oom_error(self, original_basename, log_msg_prefix):
    # Clear VRAM immediately
    freed_amount = self.clear_vram_memory(show_dialog=False)
    
    # Calculate suggested settings (30% reduction)
    suggested_win = max(30, int(current_win * 0.7))
    suggested_ov = max(5, int(current_ov * 0.7))
    
    # Show recovery dialog with 3 options
    ...
```

---

## Memory Management Strategies

### Preventive Measures

**Before processing:**
1. Click "Clear VRAM" if GUI has been running long
2. Check free VRAM (shown in dialog)
3. Close other GPU applications

**Settings adjustments:**
- Reduce `window_size` (biggest impact)
- Reduce `overlap` (medium impact)
- Reduce resolution (last resort)

---

### Reactive Measures

**After OOM error:**

1. **Auto-Adjust (Recommended)**
   - 30% reduction usually sufficient
   - Preserves quality reasonably
   - Quick recovery

2. **Manual Adjustment**
   - Reduce `window_size` to 50-70
   - Reduce `overlap` to 10-15
   - Or reduce resolution to 720p

3. **Alternative Approaches**
   - Process in segments mode
   - Split video into smaller clips
   - Use different GPU tier settings

---

## VRAM Usage by Setting

| Setting | VRAM Impact | Reduction Priority |
|---------|-------------|-------------------|
| **window_size** | ⬆️⬆️⬆️ High | Reduce first |
| **overlap** | ⬆️⬆️ Medium | Reduce second |
| **resolution** | ⬆️⬆️⬆️ High | Last resort |
| **decode_chunk** | ⬆️ Medium | Auto-adjusted |

---

## Examples

### Example 1: Single OOM Error

**Scenario:** Processing 4K video, first OOM

**What happens:**
```
1. OOM error at frame 45
2. VRAM cleared: 8.2 GB freed
3. Dialog suggests: window_size 110→77
4. User clicks "Auto-Adjust & Continue"
5. Processing resumes successfully
```

**Result:** ✅ Video completes with adjusted settings

---

### Example 2: Repeated OOM Errors

**Scenario:** Very long 4K video, multiple OOMs

**What happens:**
```
1. First OOM: window_size 110→77 (auto)
2. Second OOM: window_size 77→54 (manual)
3. Third OOM: User switches to segment mode
```

**Result:** ⚠️ Needed more aggressive approach

---

### Example 3: Preventive Clear VRAM

**Scenario:** Processing batch of videos

**Workflow:**
```
1. Process video 1 (uses 38 GB VRAM)
2. Video 1 completes
3. Click "Clear VRAM" (frees 12 GB)
4. Process video 2 (starts with 26 GB used)
5. No OOM errors
```

**Result:** ✅ Batch completes without errors

---

## Technical Details

### Memory Clearing Process

```python
# 1. Python garbage collection
gc.collect()

# 2. PyTorch CUDA cache clear
torch.cuda.empty_cache()

# 3. Measure results
allocated_before = torch.cuda.memory_allocated()
reserved_before = torch.cuda.memory_reserved()

# ... clear ...

freed = reserved_before - reserved_after
```

### What Gets Cleared

**Cleared:**
- PyTorch CUDA cache (unused cached memory)
- Python unreferenced objects
- Temporary tensors

**NOT Cleared:**
- Active model weights
- Currently used tensors
- Model pipeline itself

### Why Clear VRAM Helps

**PyTorch caching behavior:**
- PyTorch caches CUDA memory for performance
- Cache grows during processing
- Cache not always released automatically
- Manual clear forces release

**Analogy:**
```
VRAM = Desk space
Cache = Papers spread out
Clear VRAM = Filing away unused papers
```

---

## Troubleshooting

### Problem: OOM Despite Clear VRAM

**Solutions:**
1. **More aggressive reduction**
   - Try 50% instead of 30%
   - window_size: 110 → 55

2. **Reduce resolution**
   - 4K → 1440p → 1080p
   - Biggest VRAM savings

3. **Segment mode**
   - Process in chunks
   - Merge afterward

---

### Problem: Auto-Adjust Too Aggressive

**Solution:** Use manual adjustment instead

**Example:**
```
Current: window_size=110, overlap=25
Auto would give: 77, 17 (too low)
Manual: Try 90, 20 (moderate reduction)
```

---

### Problem: OOM on Every Video

**Likely causes:**
1. **GPU VRAM too small** (< 12GB)
2. **Other GPU applications running**
3. **Resolution too high for hardware**

**Solutions:**
1. Close other GPU apps
2. Use conservative tier settings
3. Process in segments
4. Consider cloud GPU (Runpod, etc.)

---

## Best Practices

### Before Processing

1. ✅ Check free VRAM (click Clear VRAM to see)
2. ✅ Close unnecessary GPU applications
3. ✅ Choose appropriate settings for your GPU tier
4. ✅ For long videos, use segment mode

---

### During Processing

1. ✅ Monitor VRAM usage (nvidia-smi)
2. ✅ Watch for OOM warnings in log
3. ✅ If OOM occurs, use auto-adjust first
4. ✅ Between videos, clear VRAM proactively

---

### After OOM

1. ✅ Let auto-adjust work (30% reduction)
2. ✅ If repeated OOM, try manual (50% reduction)
3. ✅ Consider segment mode for very long videos
4. ✅ Check if other apps using GPU

---

## Log Messages

### Normal Clear VRAM

```
INFO - VRAM cleared: Freed 12.45 GB (38.50 GB → 26.05 GB reserved)
INFO -   Allocated: 35.20 GB → 23.15 GB
```

---

### OOM Error

```
ERROR - CUDA Out-Of-Memory error for my_video.mp4 (Full video (1/1))
WARNING - OOM error occurred during processing of my_video.mp4
INFO - Cleared 8.20 GB VRAM after OOM error
INFO - Auto-adjusted settings after OOM: window_size=77, overlap=17
```

---

## Related Files

- `depthcrafter_gui_seg.py` - OOM detection and recovery
- `depthcrafter/depth_crafter_ppl.py` - Pipeline memory management
- `dependency/stereocrafter_util.py` - VRAM configuration
- `depthcrafter/help_content.json` - Button tooltips

---

## Quick Reference

| Action | Button/Dialog | Effect |
|--------|--------------|--------|
| **Preventive clear** | "Clear VRAM" button | Frees cached memory |
| **OOM detected** | Auto dialog appears | Clear + suggest settings |
| **Auto-adjust** | "⚡ Auto-Adjust & Continue" | -30% window/overlap |
| **Manual adjust** | "✋ Manual Adjustment" | You choose values |
| **Stop processing** | "❌ Stop Processing" | Cancel job |

---

**Date:** 2026-03-10  
**Status:** ✅ Implemented  
**Version:** depthcrafter_gui_seg.py enhanced
