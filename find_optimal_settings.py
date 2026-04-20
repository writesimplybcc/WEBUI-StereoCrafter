#!/usr/bin/env python3
"""
Find optimal window_size and overlap for RTX 6000 Ada (48GB)
Tests different values to find maximum that doesn't OOM
"""

import torch
import sys
import os

# Test configurations to try (window_size, overlap)
# Start conservative and work up
TEST_CONFIGS = [
    (60, 10),
    (70, 12),
    (80, 15),
    (90, 18),
    (100, 20),
    (110, 22),
    (120, 24),
    (130, 26),
]

def check_memory():
    """Return current memory stats"""
    if not torch.cuda.is_available():
        return None
    
    allocated = torch.cuda.memory_allocated(0) / 1024**3
    reserved = torch.cuda.memory_reserved(0) / 1024**3
    total = torch.cuda.get_device_properties(0).total_memory / 1024**3
    free = total - allocated
    
    return {
        'allocated': allocated,
        'reserved': reserved,
        'total': total,
        'free': free
    }

def test_config(window_size, overlap, video_path="./input_source_clips/Incept_V2-0080.mp4"):
    """Test a specific window_size/overlap configuration"""
    print(f"\n{'='*60}")
    print(f"Testing: window_size={window_size}, overlap={overlap}")
    print(f"{'='*60}")
    
    # Clear memory before test
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    
    mem_before = check_memory()
    print(f"Memory before: {mem_before['allocated']:.2f} GB allocated, {mem_before['free']:.2f} GB free")
    
    try:
        # Import here to avoid loading model multiple times
        from depthcrafter.depthcrafter_logic import DepthCrafterDemo
        
        # Initialize model (this uses ~41GB)
        print("Loading model...")
        demo = DepthCrafterDemo(
            unet_path="tencent/DepthCrafter",
            pre_train_path="stabilityai/stable-video-diffusion-img2vid-xt",
            cpu_offload="model",
            use_cudnn_benchmark=False,
            local_files_only=True
        )
        
        mem_after_load = check_memory()
        print(f"Memory after model load: {mem_after_load['allocated']:.2f} GB allocated, {mem_after_load['free']:.2f} GB free")
        
        # Try processing with these settings
        print(f"Processing with window_size={window_size}, overlap={overlap}...")
        
        result = demo.run(
            input_path=video_path,
            output_path="./test_output",
            guidance_scale=1.2,
            num_inference_steps=5,
            seed=42,
            gui_window_size=window_size,
            gui_overlap=overlap,
            process_length_for_read_full_video=-1,
            target_fps=-1.0,
            save_npz=False,
            target_height=1080,
            target_width=1920
        )
        
        mem_peak = torch.cuda.max_memory_allocated(0) / 1024**3
        print(f"✅ SUCCESS! Peak memory: {mem_peak:.2f} GB")
        
        return True, mem_peak
        
    except torch.cuda.OutOfMemoryError as e:
        mem_peak = torch.cuda.max_memory_allocated(0) / 1024**3
        print(f"❌ OOM! Peak memory before crash: {mem_peak:.2f} GB")
        print(f"   Error: {str(e)[:200]}")
        return False, mem_peak
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False, 0
    
    finally:
        # Cleanup
        torch.cuda.empty_cache()

def main():
    print("="*60)
    print("RTX 6000 Ada Optimal Settings Finder")
    print("="*60)
    
    if not torch.cuda.is_available():
        print("❌ CUDA not available!")
        sys.exit(1)
    
    gpu_name = torch.cuda.get_device_name(0)
    total_vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
    
    print(f"GPU: {gpu_name}")
    print(f"Total VRAM: {total_vram:.2f} GB")
    print()
    
    # Check if test video exists
    test_video = "./input_source_clips/Incept_V2-0080.mp4"
    if not os.path.exists(test_video):
        print(f"❌ Test video not found: {test_video}")
        print("   Please provide a 126-frame 1080p video for testing")
        sys.exit(1)
    
    results = []
    max_working_config = None
    
    for window_size, overlap in TEST_CONFIGS:
        success, peak_mem = test_config(window_size, overlap, test_video)
        
        results.append({
            'window_size': window_size,
            'overlap': overlap,
            'success': success,
            'peak_memory': peak_mem
        })
        
        if success:
            max_working_config = (window_size, overlap, peak_mem)
        else:
            # If we hit OOM, no point testing higher values
            print(f"\n⚠️  Hit OOM at window_size={window_size}, stopping tests")
            break
    
    # Print summary
    print("\n" + "="*60)
    print("RESULTS SUMMARY")
    print("="*60)
    
    for r in results:
        status = "✅ OK" if r['success'] else "❌ OOM"
        print(f"window_size={r['window_size']:3d}, overlap={r['overlap']:2d} | {status} | Peak: {r['peak_memory']:.2f} GB")
    
    if max_working_config:
        ws, ov, mem = max_working_config
        print("\n" + "="*60)
        print("RECOMMENDED SETTINGS FOR RTX 6000 ADA")
        print("="*60)
        print(f"window_size: {ws}")
        print(f"overlap: {ov}")
        print(f"Peak memory: {mem:.2f} GB")
        print(f"Safety margin: {total_vram - mem:.2f} GB")
    else:
        print("\n❌ No working configuration found! Even the smallest settings caused OOM.")
        print("   This suggests the model itself is using too much memory.")
        print("   Try changing CPU Offload mode to 'sequential' instead of 'model'")

if __name__ == "__main__":
    main()
