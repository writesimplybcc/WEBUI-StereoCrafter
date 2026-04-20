# Same as Input Checkbox - Gradio UI Fix

## Problem

The "Same as Input" checkbox was added to the wrong file (`splatting_gui.py` - Tkinter) but the actual running UI is the **Gradio-based UI** (`stereocrafter_ui/splatting/splatting_ui.py`).

## Solution

Added the checkbox and auto-detect function to the correct Gradio UI file.

---

## Changes Made

### File: `stereocrafter_ui/splatting/splatting_ui.py`

#### 1. Added Checkbox UI (Line ~3822)

```python
# Same as Input Checkbox (NEW)
self.same_as_input_comp = gr.Checkbox(
    label="Same as Input (auto-detect from source folder)",
    value=False,
    info="When checked, automatically detects the resolution from the first video file in the source folder and applies it to the Width/Height settings."
)
```

**Location:** Between "Enable Low Res" row and "Width/Height" row in Process Resolution section.

---

#### 2. Added Event Handler (Line ~4242)

```python
# Auto-detect resolution when "Same as Input" is checked
self.same_as_input_comp.change(
    fn=self.auto_detect_resolution_from_source,
    inputs=[self.same_as_input_comp],
    outputs=[self.pre_res_width_comp, self.pre_res_height_comp, self.status_label]
)
```

---

#### 3. Added Auto-Detect Function (Line ~4250)

```python
def auto_detect_resolution_from_source(self, same_as_input_enabled: bool):
    """Auto-detect resolution from the first video in source folder."""
    if not same_as_input_enabled:
        return gr.update(), gr.update(), gr.update()
    
    try:
        # Get source folder
        source_folder = self.input_source_clips
        
        # Find first video file
        video_file = first video file found
        
        # Detect resolution using OpenCV
        cap = cv2.VideoCapture(video_file)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        return width, height, f"✅ Detected: {width}x{height}"
    except Exception as e:
        return gr.update(), gr.update(), f"❌ Error: {str(e)}"
```

---

## Expected Layout (Gradio UI)

```
┌─ Process Resolution ─────────────────────────────────┐
│                                                      │
│ ☑ Enable Full Res  [Batch Size]  [Dual Output Only] │
│                                                      │
│ ☑ Enable Low Res   [Batch Size]                     │
│                                                      │
│ ☑ Same as Input (auto-detect from source folder)    │ ← NEW!
│                                                      │
│ Width: [1280]      Height: [720]                     │
└──────────────────────────────────────────────────────┘
```

---

## Usage

1. **Navigate to Splatting tab**
2. **Set Source Folder** to folder containing video files
3. **Enable "Enable Low Res"** checkbox
4. **Check "Same as Input"** checkbox
5. **Expected result:**
   - Width and Height fields automatically update
   - Status shows: "✅ Detected: 1920x1080 from video.mp4"
   - Width/Height fields now contain detected resolution

---

## Error Messages

| Message | Cause | Solution |
|---------|-------|----------|
| ⚠️ No source folder selected | Source folder not set | Set source folder first |
| ⚠️ No video files found in: /path | No videos in folder | Add video files to folder |
| ❌ Failed to read: video.mp4 | Can't open video file | Check file permissions/corruption |
| ❌ Invalid resolution detected | Video properties unreadable | Try different video file |
| ❌ Error: [details] | Unexpected error | Check console log for details |

---

## Technical Details

### Detection Process

1. **Read source folder path** from `input_source_clips` variable
2. **Scan for video files** (.mp4, .avi, .mov, .mkv, .webm, .flv, .wmv)
3. **Open first video** with OpenCV
4. **Extract resolution** using `CAP_PROP_FRAME_WIDTH` and `CAP_PROP_FRAME_HEIGHT`
5. **Update Width/Height fields** with detected values
6. **Show status message** with detection result

---

### Gradio Component Flow

```
same_as_input_comp (Checkbox)
    ↓ change event
auto_detect_resolution_from_source (Function)
    ↓ returns
pre_res_width_comp (Number) ← Updated with width
pre_res_height_comp (Number) ← Updated with height
status_label (Text) ← Updated with status message
```

---

## Files Modified

- `stereocrafter_ui/splatting/splatting_ui.py` - Added checkbox, event handler, and auto-detect function
- `splatting_gui.py` - **NOT USED** (Tkinter version, can be ignored)

---

## Verification

After restarting the Gradio UI:

1. **Go to Splatting tab**
2. **Look for "Same as Input" checkbox** in Process Resolution section
3. **Check the checkbox**
4. **Status should show** detection result or error message
5. **Width/Height fields should update** with detected resolution

---

**Date:** 2026-03-10  
**Status:** ✅ Fixed (Correct File)  
**Issue:** Checkbox added to wrong UI file  
**Resolution:** Added to Gradio UI (`stereocrafter_ui/splatting/splatting_ui.py`)
