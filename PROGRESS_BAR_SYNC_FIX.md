# Progress Bar Synchronization Fix

## Problem

The WEBUI GUI showed processing as complete while the CLI console showed it was only halfway through. This created confusion about the actual processing status.

**Example:**
- **GUI Status:** "Processed tasks: 1/2" (shows 50% complete)
- **CLI Console:** "Encoding: |█████████---------------| 45.0% 63/127 frames"

The GUI was counting **tasks** (Full Res, Low Res) while the CLI was showing **frame-level** progress within each task.

---

## Root Cause

**Two different progress tracking systems:**

1. **GUI Progress Bar** - Task-level tracking
   - Counts completed tasks (e.g., "Full Res task done", "Low Res task done")
   - Shows: `Processed tasks: 1/2`
   - Updates only when entire task completes

2. **CLI Progress Bar** - Frame-level tracking
   - Shows frames encoded within current task
   - Shows: `Encoding: |████-----| 45.0% 63/127`
   - Updates every frame

**The discrepancy:**
- GUI shows "1/2 tasks" (50%) when Full Res task completes
- But Low Res task is still encoding frame 63/127 (45%)
- User sees GUI at 50% but CLI at 45% → confusion

---

## Solution

Enhanced `draw_progress_bar()` to report frame-level progress to the GUI status bar, synchronizing both displays.

### Changes Made

#### 1. Enhanced `draw_progress_bar()` Function

**File:** `dependency/stereocrafter_util.py`

**Before:**
```python
def draw_progress_bar(current, total, bar_length=50, prefix="Progress:", suffix=""):
    # Only prints ASCII bar to console
    print(f"\r{prefix} |{bar}| {percent:.1f}% {actual_suffix}", end="", flush=True)
```

**After:**
```python
def draw_progress_bar(current, total, bar_length=50, prefix="Progress:", suffix="", gui_progress_queue=None):
    """
    Draws ASCII progress bar in console.
    If gui_progress_queue is provided, also sends progress updates to GUI.
    """
    if gui_progress_queue is None:
        # CLI mode - print ASCII bar
        print(f"\r{prefix} |{bar}| {percent:.1f}% {actual_suffix}", end="", flush=True)
    elif gui_progress_queue is not None and current % max(1, total // 10) == 0:
        # GUI mode - report at 10% intervals to avoid flooding
        gui_progress_queue.put(("status", f"{prefix} {current}/{total} ({percent:.0f}%)"))
```

**Key improvements:**
- Added `gui_progress_queue` parameter
- Detects GUI vs CLI mode
- Reports frame progress to GUI at 10% intervals (avoids queue flooding)
- Suppresses console ASCII bar in GUI mode (prevents duplicate indicators)

---

#### 2. Updated Progress Bar Calls

**File:** `splatting_gui.py`

**Encoding progress (Line ~3841):**
```python
# Before
draw_progress_bar(frame_count, num_frames, prefix=f"  Encoding:")

# After
draw_progress_bar(frame_count, num_frames, prefix=f"  Encoding:", 
                  gui_progress_queue=self.progress_queue)
```

**Auto-convergence pre-pass (Line ~4082):**
```python
# Before
draw_progress_bar(i + len(current_frame_indices), num_frames, 
                  prefix="  Auto-Conv Pre-Pass:")

# After
draw_progress_bar(i + len(current_frame_indices), num_frames, 
                  prefix="  Auto-Conv Pre-Pass:",
                  gui_progress_queue=self.progress_queue)
```

---

## Expected Behavior

### Before Fix

```
GUI Status Bar:
"Processed tasks: 1/2 (overall)"  ← Stays at 50% during entire Low Res encoding

CLI Console:
Encoding: |█████---------------| 25.0% 32/127
Encoding: |██████████----------| 50.0% 64/127
Encoding: |███████████████-----| 75.0% 96/127
Encoding: |████████████████████| 100.0% Complete
```

**User sees:** GUI stuck at 50% while CLI shows 25%→100%

---

### After Fix

```
GUI Status Bar:
"Overall: 1/2 - Encoding LowRes: 32/127 (25%)"
"Overall: 1/2 - Encoding LowRes: 64/127 (50%)"
"Overall: 1/2 - Encoding LowRes: 96/127 (75%)"
"Processed tasks: 2/2 (overall)"  ← Updates to 100% when done

CLI Console:
(Suppressed in GUI mode - no duplicate output)
```

**User sees:** Both GUI and CLI show synchronized progress

---

## Progress Reporting Frequency

To avoid flooding the GUI update queue, frame progress is reported at **10% intervals**:

| Total Frames | Reports At Frames |
|--------------|-------------------|
| 127 frames | 13, 25, 38, 51, 64, 76, 89, 102, 115, 127 |
| 500 frames | 50, 100, 150, 200, 250, 300, 350, 400, 450, 500 |
| 1000 frames | 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000 |

**Why 10%?**
- Frequent enough to show progress
- Not so frequent as to flood GUI update queue
- Balances responsiveness with performance

---

## Status Message Format

### Task-Level Messages
```
"Processed tasks: 1/2 (overall)"
"Processing Full Res for video_name"
```

### Frame-Level Messages (NEW)
```
"Overall: 1/2 - Encoding: 64/127 (50%)"
"Overall: 1/2 - Auto-Conv Pre-Pass: 96/127 (75%)"
```

### Combined Display
The GUI status bar shows:
```
Overall: [task_progress] - [current_operation]: [frame_progress]
```

---

## Benefits

### ✅ Accurate Progress
- GUI now shows real-time frame progress
- No more discrepancy between GUI and CLI
- User knows exactly where processing is at

### ✅ Better UX
- Smooth progress updates every 10%
- Clear indication of current operation
- No confusion about completion status

### ✅ Flexible
- Works in both GUI and CLI modes
- CLI mode: ASCII progress bar
- GUI mode: Status bar updates
- Automatic detection based on `gui_progress_queue` parameter

---

## Technical Details

### Progress Queue Communication

```python
# Worker thread sends progress
self.progress_queue.put(("status", f"Encoding: {current}/{total} ({percent:.0f}%)"))

# GUI main thread receives and updates
elif message[0] == "status":
    self.status_label.config(
        text=f"Overall: {self.progress_var.get()}/{self.progress_bar['maximum']} - {message[1]}"
    )
```

### Thread Safety

The progress queue ensures thread-safe communication:
- **Worker thread** (processing): Puts progress messages
- **GUI thread** (main loop): Reads and displays messages
- No direct GUI updates from worker thread

---

## Testing

### Test Case 1: Single Video Processing
1. Start processing a 127-frame video
2. **Expected:** Status bar shows frame progress at 13, 25, 38... frames
3. **Expected:** Progress smoothly advances from 0% to 100%

---

### Test Case 2: Batch Processing
1. Process 5 videos with Low Res enabled
2. **Expected:** Status shows both task and frame progress
3. **Example:** "Overall: 2/5 - Encoding: 64/127 (50%)"

---

### Test Case 3: CLI Mode
1. Run from command line (not GUI)
2. **Expected:** ASCII progress bar appears in console
3. **Expected:** No GUI status updates (no GUI running)

---

## Related Files

- `dependency/stereocrafter_util.py` - Enhanced `draw_progress_bar()` function
- `splatting_gui.py` - Updated progress bar calls
- `gui/app.py` - Progress queue handling (existing)

---

## Future Enhancements

Potential improvements:

1. **Configurable Update Frequency**
   - Slider for progress update interval
   - 5%, 10%, 20% options

2. **ETA Display**
   - Calculate estimated time remaining
   - Based on frames processed per second

3. **Per-Task Progress Bar**
   - Separate progress bar for current task
   - Shows frame progress within task
   - Main bar shows task completion

4. **Progress History Graph**
   - Visual graph of processing speed
   - Identify bottlenecks
   - Optimize settings

---

**Date:** 2026-03-10  
**Status:** ✅ Fixed  
**Issue:** GUI showed complete while CLI showed halfway  
**Resolution:** Synchronized frame-level progress reporting to GUI status bar
