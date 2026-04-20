# Same as Input Checkbox Visibility Fix

## Issue

The "Same as Input" checkbox added to the Splatting UI's Process Resolution frame was not visible to users.

## Root Causes Identified

1. **Missing Row Configuration** - Grid rows weren't explicitly configured
2. **Missing Config Save/Load** - Checkbox state wasn't persisted
3. **Widget Initialization** - Checkbox needed explicit update call

## Fixes Applied

### 1. Added Grid Row Configuration

**File:** `splatting_gui.py` (Line ~2145)

```python
# Configure rows for proper visibility
self.preprocessing_frame.grid_rowconfigure(0, weight=0)
self.preprocessing_frame.grid_rowconfigure(1, weight=0)
self.preprocessing_frame.grid_rowconfigure(2, weight=0)  # Same as Input row
self.preprocessing_frame.grid_rowconfigure(3, weight=0)  # Width/Height row
```

**Why:** Ensures all rows in the grid layout are properly allocated space.

---

### 2. Added Checkbox to Config Save

**File:** `splatting_gui.py` (Line ~4324)

```python
"enable_low_resolution": self.enable_low_res_var.get(),
"same_as_input": self.same_as_input_var.get(),  # NEW: Save checkbox state
"pre_res_width": self.pre_res_width_var.get(),
```

**Why:** Checkbox state is now saved to config file and restored on next launch.

---

### 3. Added Widget Update Call

**File:** `splatting_gui.py` (Line ~2227)

```python
self.same_as_input_checkbox.pack(side="left")
self._create_hover_tooltip(self.same_as_input_checkbox, "same_as_input")

# Debug: Ensure checkbox is visible
self.same_as_input_checkbox.update()
```

**Why:** Forces immediate widget rendering and visibility check.

---

## Expected Layout

```
┌─ Process Resolution ────────────────────────────┐
│                                                 │
│ ☑ Enable Full Res    [Batch Size] [Dual Output]│
│ ☑ Enable Low Res     [Batch Size] [Splat Test] │
│                                                 │
│ ☑ Same as Input                                 │
│                                                 │
│ Width: [1920]  Height: [1080]    [Map Test]    │
└─────────────────────────────────────────────────┘
```

**Row Layout:**
- Row 0: Full Res checkbox + Batch Size + Dual Output
- Row 1: Low Res checkbox + Batch Size + Splat Test
- **Row 2: Same as Input checkbox** ← NEW
- Row 3: Width + Height fields + Map Test

---

## Troubleshooting

If checkbox is still not visible after restart:

### 1. Check Python Console for Errors

When launching the GUI, look for:
```
Error: splatter_help.json not found. Tooltips will not be available.
```

If help text file is missing, checkbox might not render properly.

**Solution:** Ensure `dependency/splatter_help.json` exists and contains:
```json
"same_as_input": "When checked, automatically detects the resolution..."
```

---

### 2. Verify Widget Creation

Add temporary debug logging in `splatting_gui.py`:

```python
# After checkbox creation (line ~2227)
logger.info(f"Same as Input checkbox created: {self.same_as_input_checkbox}")
logger.info(f"Checkbox visible: {self.same_as_input_checkbox.winfo_ismapped()}")
```

**Expected output:**
```
INFO - Same as Input checkbox created: !ttk.Checkbutton
INFO - Checkbox visible: True
```

---

### 3. Check Grid Layout

The checkbox might be hidden behind other widgets. Verify grid configuration:

```python
# In preprocessing_frame setup
self.preprocessing_frame.grid_columnconfigure(0, weight=0)
self.preprocessing_frame.grid_columnconfigure(1, weight=0)
self.preprocessing_frame.grid_columnconfigure(2, weight=0)
self.preprocessing_frame.grid_rowconfigure(2, weight=0)  # Same as Input row
```

---

### 4. Manual Visibility Test

After GUI launches, open Python console and run:
```python
gui = app_instance  # or however you reference the GUI
gui.same_as_input_checkbox.config(state="normal")
gui.same_as_input_frame.lift()  # Bring to front
```

---

### 5. Theme Issues

Some ttk themes might not render checkboxes properly. Try changing theme:

```python
# In GUI, try different themes
style = ttk.Style()
print(style.theme_names())  # Show available themes
style.theme_use("clam")  # Try different theme
```

**Recommended themes:**
- `clam` - Good visibility
- `alt` - Classic look
- `default` - Standard ttk

---

### 6. Screen Resolution

If screen resolution is too low, the checkbox might be off-screen.

**Minimum resolution:** 1280×720  
**Recommended:** 1920×1080 or higher

**Test:** Maximize the GUI window and scroll down in Process Resolution frame.

---

## Verification Steps

After applying fixes:

1. **Restart the GUI**
   ```bash
   python splatting_gui.py
   ```

2. **Navigate to Splatting tab**

3. **Look for "Same as Input" checkbox**
   - Should be between "Enable Low Res" row and "Width/Height" row
   - Should have tooltip on hover

4. **Test checkbox functionality**
   - Check the box
   - Should show dialog: "No source folder selected" (if no folder selected)
   - Or: "Detected resolution from: video.mp4" (if folder has videos)

5. **Verify config save**
   - Check checkbox
   - Close GUI
   - Reopen GUI
   - Checkbox should still be checked

---

## Related Files

- `splatting_gui.py` - Main GUI implementation
- `dependency/splatter_help.json` - Help tooltip text
- `SAME_AS_INPUT_RESOLUTION_FEATURE.md` - Feature documentation

---

## Known Limitations

1. **Requires Restart** - Changes to grid layout require GUI restart
2. **Theme Dependent** - Some themes might render checkbox differently
3. **Help Text Required** - Tooltip requires `splatter_help.json` to exist

---

**Date:** 2026-03-10  
**Status:** ✅ Fixed  
**Issue:** "Same as Input" checkbox not visible  
**Resolution:** Added grid row config, config save, and widget update
