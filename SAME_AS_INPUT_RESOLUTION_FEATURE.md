# Same as Input Resolution Feature

## Overview

Added a **"Same as Input"** checkbox to the Splatting UI's Process Resolution section that automatically detects and applies the source video resolution.

## Features

### What It Does

When checked, the system:
1. Scans the source folder for video files
2. Reads the resolution from the first video found
3. Automatically sets the Width/Height fields to match
4. Disables manual Width/Height input (read-only mode)
5. Shows a confirmation dialog with detected values

### User Interface

**Location:** Splatting tab → Process Resolution frame

**Layout:**
```
┌─ Process Resolution ─────────────────────────┐
│                                              │
│ ☑ Enable Full Res    [Batch Size] [Dual]    │
│ ☑ Enable Low Res     [Batch Size] [Test]    │
│                                              │
│ ☑ Same as Input                              │
│                                              │
│ Width: [1920]  Height: [1080]  [Map Test]   │
└──────────────────────────────────────────────┘
```

When "Same as Input" is checked:
- Width and Height fields become **disabled** (read-only)
- Values are automatically populated from source video
- Manual editing is prevented until unchecked

---

## How It Works

### Detection Process

1. **Get Source Folder**
   - Reads the currently selected source folder from file browser
   
2. **Find First Video**
   - Scans for files with extensions: `.mp4`, `.avi`, `.mov`, `.mkv`, `.webm`, `.flv`, `.wmv`
   - Uses the first video file found

3. **Read Resolution**
   - Opens video with OpenCV
   - Extracts width and height from video properties
   - Closes video file

4. **Apply Settings**
   - Sets `pre_res_width_var` to detected width
   - Sets `pre_res_height_var` to detected height
   - Shows confirmation dialog

---

## Usage

### Step-by-Step

1. **Select Source Folder**
   - Choose a folder containing your video files

2. **Enable Low Resolution**
   - Check "Enable Low Res" checkbox

3. **Check "Same as Input"**
   - System auto-detects resolution
   - Dialog shows detected values:
     ```
     Detected resolution from: video.mp4
     
     Width: 1920
     Height: 1080
     
     Applied to Process Resolution settings.
     ```

4. **Width/Height Fields**
   - Now show detected values
   - Are disabled (read-only)
   - Will be used for processing

5. **Uncheck to Manual Override**
   - Uncheck "Same as Input"
   - Width/Height fields become editable
   - Enter custom values

---

## Error Handling

### No Source Folder Selected
```
⚠️ Warning
No source folder selected. Please select a folder with video files first.
```
- Checkbox automatically unchecks
- User must select source folder first

---

### No Video Files Found
```
⚠️ Warning
No video files found in:
C:\path\to\folder
```
- Checkbox automatically unchecks
- User needs to add video files to source folder

---

### Failed to Read Video
```
❌ Error
Failed to read video:
video.mp4
```
- Checkbox automatically unchecks
- Video file may be corrupted or unsupported codec

---

### Invalid Resolution Detected
```
❌ Error
Invalid resolution detected:
0x0
```
- Checkbox automatically unchecks
- Video properties couldn't be read

---

## Technical Details

### Code Changes

**File:** `splatting_gui.py`

#### 1. Added Variable (Line ~683)
```python
self.same_as_input_var = tk.BooleanVar(value=False)
```

#### 2. Added Checkbox UI (Line ~2210)
```python
self.same_as_input_checkbox = ttk.Checkbutton(
    self.same_as_input_frame,
    text="Same as Input",
    variable=self.same_as_input_var,
    command=self.toggle_same_as_input_resolution,
)
```

#### 3. Added Toggle Function (Line ~8001)
```python
def toggle_same_as_input_resolution(self):
    """Handle 'Same as Input' checkbox toggle."""
    if self.same_as_input_var.get():
        self._auto_detect_and_apply_resolution()
    self.toggle_processing_settings_fields()
```

#### 4. Added Auto-Detect Function (Line ~8009)
```python
def _auto_detect_and_apply_resolution(self):
    """Auto-detect resolution from source folder files."""
    # 1. Get source folder
    # 2. Find first video file
    # 3. Read resolution with OpenCV
    # 4. Apply to width/height vars
    # 5. Show confirmation dialog
```

#### 5. Updated Field Toggle (Line ~7985)
```python
# If "Same as Input" is checked, disable width/height entries
if self.same_as_input_var.get():
    self.pre_res_width_entry.config(state="disabled")
    self.pre_res_height_entry.config(state="disabled")
```

---

### Dependencies

**OpenCV (cv2)**
```python
import cv2
cap = cv2.VideoCapture(video_file)
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
```

Used to read video file properties without loading frames.

---

## Benefits

### ✅ Convenience
- No need to manually check video properties
- One-click setup for matching resolution
- Especially useful for batch processing multiple videos

### ✅ Accuracy
- Reads actual video file properties
- No guesswork or manual measurement
- Prevents resolution mismatch errors

### ✅ Workflow Efficiency
- Faster setup time
- Reduces user error
- Consistent resolution across processing

---

## Use Cases

### Scenario 1: Batch Processing Multiple Videos
**Before:**
- Check each video's properties manually
- Enter resolution for each batch
- Risk of typos or wrong values

**After:**
- Check "Same as Input"
- System auto-detects
- Process entire batch with correct resolution

---

### Scenario 2: Unknown Video Resolution
**Before:**
- Open video in media player
- Check properties/details
- Note down resolution
- Enter manually

**After:**
- Check "Same as Input"
- Done! ✅

---

### Scenario 3: Mixed Resolution Batch
**Before:**
- Process each resolution separately
- Manual configuration for each group

**After:**
- Group videos by resolution
- Check "Same as Input" for each group
- System handles each correctly

---

## Limitations

### First Video Only
- Only reads the **first** video file found in source folder
- If folder contains videos with different resolutions, only the first one's resolution is used
- **Solution:** Group videos by resolution in separate folders

### Requires Video Files
- Must have at least one video file in source folder
- Won't work with image sequences only
- **Solution:** Manually enter resolution for image sequences

### Read-Only Mode
- When checked, Width/Height fields are disabled
- Cannot manually adjust while checkbox is active
- **Solution:** Uncheck to manually override

---

## Related Files

- `splatting_gui.py` - Main implementation
- `dependency/splatter_help.json` - Help tooltip text

---

## Future Enhancements

Potential improvements:

1. **Scan All Videos**
   - Detect resolution of all videos in folder
   - Warn if mixed resolutions found
   - Auto-group by resolution

2. **Image Sequence Support**
   - Read resolution from first image
   - Apply to processing settings

3. **Persistent Setting**
   - Remember last detected resolution
   - Skip re-detection for same folder

4. **Quick Override**
   - Allow manual adjustment while checked
   - Auto-uncheck on manual edit

---

**Date:** 2026-03-10  
**Status:** ✅ Implemented  
**Feature:** Auto-detect source video resolution  
**Location:** Splatting tab → Process Resolution → "Same as Input" checkbox
