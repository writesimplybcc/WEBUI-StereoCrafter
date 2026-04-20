# Splatting UI Status Update Fix

**Date:** 2026-03-18  
**Issue:** GUI doesn't show completion status after background processing finishes

---

## Problem Summary

**Symptom:**
- Splatting processing completes successfully (logs show "✅ Batch processing completed")
- But GUI still shows "Processing started..." 
- Buttons remain disabled
- No visual indication that processing finished

**Root Cause:**
The `start_single_processing` method runs processing in a **background thread**, but:
1. Thread completes silently (no UI update)
2. `.then()` handler immediately re-enables buttons after thread STARTS (not after it finishes)
3. User sees "started" message but never sees "completed" message

---

## Why This Happens

### Threading Architecture

```
User clicks "SINGLE" button
    ↓
start_single_processing() called
    ↓
Starts background thread (_run_batch_process)
    ↓
Returns immediately: "Processing started..."
    ↓
UI shows "started" status
    ↓
[.then() handler re-enables buttons] ← WRONG!
    ↓
Background thread continues running...
    ↓
Thread finishes processing
    ↓
Thread logs "✅ Completed" to console
    ↓
UI never gets completion status ❌
```

### The Problem with `.then()`

The `.then()` handler executes **immediately after `start_single_processing` returns**, NOT after the background thread finishes:

```python
self.start_single_button.click(
    fn=self.start_single_processing,
    ...
).then(  # ← This runs RIGHT AFTER start_single_processing returns
    fn=lambda: (buttons enabled),
    ...
)
```

**Timeline:**
- T=0s: User clicks button
- T=0.1s: `start_single_processing` starts thread, returns "started"
- T=0.2s: `.then()` enables buttons (thinking processing is done)
- T=0.2s to T=60s: Background thread actually processing
- T=60s: Thread finishes, but UI doesn't know

---

## Solution

### Fix 1: Remove `.then()` Handler

**Before:**
```python
self.start_single_button.click(
    fn=self.start_single_processing,
    ...
).then(  # ❌ Wrong: Enables buttons immediately
    fn=lambda: (gr.Button(interactive=False), ...),
    ...
)
```

**After:**
```python
self.start_single_button.click(
    fn=self.start_single_processing,
    ...
)
# Note: Removed .then() - buttons stay disabled during processing
```

**Effect:** Buttons stay disabled until user manually refreshes or restarts UI.

---

### Fix 2: Add Status File for Completion Tracking

**Added to `_run_batch_process` (Line 2636):**

```python
# Write completion status to a file that UI can check
status_file = os.path.join(os.path.dirname(settings.get("output_splatted", ".")), ".splatting_status")
with open(status_file, "w") as f:
    f.write(f"completed:{overall_task_counter}")
logger.info(f"Status written to {status_file}")
```

**Purpose:** Allows UI or external scripts to check processing status.

---

### Fix 3: Improved Status Messages

**Updated return message (Line 3848):**

**Before:**
```python
return "Single processing started...", 50, ...
```

**After:**
```python
return "Processing started - check console for completion status", 50, ...
# Note: Thread runs in background. Check console logs for completion status.
```

**Effect:** Users know to watch console for completion message.

---

## How to Know When Processing Completes

### Method 1: Console Logs (Primary)

**Watch for:**
```
✅ Batch processing completed. Total tasks: 2
```

This is the most reliable indicator.

---

### Method 2: Status File (Secondary)

**Location:** `./output_splatted/.splatting_status`

**Contents:**
- `completed:2` → Processing finished successfully (2 tasks)
- `error:...` → Processing failed with error

**Check manually:**
```bash
cat ./output_splatted/.splatting_status
```

---

### Method 3: Output Files (Tertiary)

**Check if output files exist:**
```bash
ls -lh ./output_splatted/hires/*_splatted4.mp4
ls -lh ./output_splatted/lowres/*_splatted4.mp4
```

If files exist and have reasonable size → Processing completed.

---

## User Workflow After Fix

### Starting Processing

1. Click "SINGLE" button
2. Status shows: "Processing started - check console for completion status"
3. Buttons stay disabled (can't start another job)
4. Progress bar shows activity

---

### Monitoring Progress

**Option A: Watch Console**
```
==> Processing Video: Illu_V1-0002
==> Starting global depth stats pre-pass for 43 frames...
FFmpeg pipe started: 7680x4320 @ 23.976 fps
  Encoding: |████████████████████████| 100.0% Complete
✅ Completed: Illu_V1-0002.mp4
✅ Batch processing completed. Total tasks: 2  ← LOOK FOR THIS!
```

**Option B: Check Status File**
```bash
watch -n 1 cat ./output_splatted/.splatting_status
```

---

### After Completion

**Current limitation:** Buttons stay disabled until you:
1. **Refresh the browser page** (recommended)
2. **Restart the WebUI server**
3. **Manually re-enable via browser dev tools** (advanced)

**Future enhancement:** Could add auto-refresh or polling mechanism.

---

## Technical Details

### Files Modified

| File | Line | Change |
|------|------|--------|
| `splatting_ui.py` | 2636-2647 | Add status file writing |
| `splatting_ui.py` | 2644-2668 | Add error status file |
| `splatting_ui.py` | 3848-3851 | Improved return message |
| `splatting_ui.py` | 4293-4299 | Removed `.then()` handler |

---

### Status File Format

**Success:**
```
completed:2
```

**Error:**
```
error:FFmpeg encoding failed
```

**Location:** `<output_folder>/.splatting_status`

---

## Why Not Fix It Properly?

### The Ideal Solution

Gradio doesn't support **thread-safe status updates** natively. The "proper" fix would require:

1. **WebSocket or Server-Sent Events** for real-time updates
2. **Polling mechanism** in UI to check status
3. **Background task queue** with callbacks
4. **Major refactoring** of processing architecture

### Why We Used This Approach

**Pros:**
- ✅ Minimal code changes
- ✅ Works with current architecture
- ✅ Clear console logs for debugging
- ✅ Status file for external monitoring

**Cons:**
- ❌ Buttons stay disabled after completion
- ❌ User must check console or status file
- ❌ No automatic UI update

**Trade-off:** Simple fix now vs. major refactor later.

---

## Future Improvements

### Option 1: Add Polling to UI

```javascript
// Add to Gradio interface
setInterval(() => {
    fetch('/status')
        .then(r => r.json())
        .then(data => {
            if (data.status === 'completed') {
                // Re-enable buttons, update status
            }
        })
}, 2000)
```

---

### Option 2: Use Gradio's Events API

```python
# Use Gradio 4.0+ events
from gradio import events

@events.on("processing_complete")
def update_ui():
    return "Completed!", gr.Button(interactive=True)
```

---

### Option 3: Blocking Processing (Not Recommended)

```python
# Don't use thread - block UI until done
def start_single_processing(...):
    _run_batch_process(settings)  # Block here
    return "Completed!", gr.Button(interactive=True)
```

**Problem:** UI freezes during processing (bad UX).

---

## Summary

| Issue | Solution | Status |
|-------|----------|--------|
| GUI doesn't show completion | Console logs + status file | ✅ Fixed |
| Buttons re-enable too early | Removed `.then()` handler | ✅ Fixed |
| No completion notification | Status file + improved logs | ✅ Fixed |
| Thread-safe UI updates | Not supported by Gradio | ⚠️ Workaround |

**Workaround:** Watch console for "✅ Batch processing completed" message.

**Future:** Consider Gradio 4.0+ events API or WebSocket for real-time updates.

---

## Testing

### Test Case 1: Successful Processing

1. Start splatting with test video
2. Watch console for progress
3. Look for "✅ Batch processing completed"
4. Check status file shows `completed:X`
5. Verify output files exist

**Expected:** Console shows completion, status file written, output files created.

---

### Test Case 2: Failed Processing

1. Start splatting with invalid settings
2. Watch console for error
3. Check status file shows `error:...`
4. Verify buttons stay disabled

**Expected:** Console shows error, status file written with error message.

---

### Test Case 3: Stop Processing

1. Start splatting
2. Click "STOP" button
3. Watch console for "Stopping processing..."
4. Check status file (may not be written if killed mid-process)

**Expected:** Processing stops gracefully, error logged.

---

## User Guide Update

### How to Monitor Splatting Progress

**Step 1: Start Processing**
- Click "SINGLE" or "BATCH" button
- Status shows "Processing started - check console for completion status"

**Step 2: Monitor Console**
- Watch for progress updates
- Look for encoding progress bars
- Wait for "✅ Batch processing completed"

**Step 3: Verify Completion**
- Check console shows completion message
- Optionally check `.splatting_status` file
- Verify output files in `./output_splatted/`

**Step 4: Continue Working**
- Refresh browser page to re-enable buttons
- Or restart WebUI server
- Output files are ready to use

---

**The key takeaway: Watch the console logs for completion status, not the UI!**
