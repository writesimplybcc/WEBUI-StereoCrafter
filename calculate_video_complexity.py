#!/usr/bin/env python3
"""
Video Complexity Calculator for DepthCrafter
Estimates processing time, memory requirements, and optimal settings
"""

def calculate_complexity(width, height, frames):
    """Calculate video complexity score"""
    resolution_factor = (width * height) / (1920 * 1080)
    frame_factor = frames / 127
    complexity = resolution_factor * frame_factor
    return resolution_factor, frame_factor, complexity


def get_scale_factor(complexity):
    """Determine scale factor based on complexity"""
    if complexity > 40:
        return 0.25, "EXTREME"
    elif complexity > 20:
        return 0.35, "Very High"
    elif complexity > 10:
        return 0.50, "High"
    elif complexity > 5:
        return 0.70, "Moderate"
    else:
        return 1.00, "Normal"


def estimate_processing_time(complexity, gpu_type="RTX 6000 Ada"):
    """Estimate processing time in minutes"""
    # Base time for 127 frames @ 1080p on RTX 6000 Ada: 10 minutes
    base_time = 10
    
    # GPU speed factors relative to RTX 6000 Ada
    gpu_factors = {
        "RTX 6000 Ada": 1.0,
        "A100 80GB": 0.7,
        "RTX 4090": 1.1,
        "RTX 3090": 1.5,
        "A5000": 1.6,
    }
    
    gpu_factor = gpu_factors.get(gpu_type, 1.0)
    
    # Time scales roughly linearly with complexity
    # But adaptive scaling adds overhead
    if complexity > 40:
        overhead_factor = 1.3  # 30% overhead for extreme scaling
    elif complexity > 20:
        overhead_factor = 1.2
    elif complexity > 10:
        overhead_factor = 1.1
    else:
        overhead_factor = 1.0
    
    estimated_time = base_time * complexity * gpu_factor * overhead_factor
    return estimated_time


def estimate_vram(resolution_factor, frame_factor):
    """Estimate VRAM requirements in GB"""
    base_vram = 8.0  # GB for 127 frames @ 1080p
    return base_vram * resolution_factor * frame_factor


def get_settings(scale_factor):
    """Get expected settings after scaling"""
    # Base settings for RTX 6000 Ada on Runpod
    base = {
        'decode_chunk_size': 14,
        'window_size': 140,
        'overlap': 30
    }
    
    scaled = {
        'decode_chunk_size': max(2, int(base['decode_chunk_size'] * scale_factor)),
        'window_size': max(30, int(base['window_size'] * scale_factor)),
        'overlap': max(5, int(base['overlap'] * scale_factor))
    }
    
    return base, scaled


def print_analysis(width, height, frames, gpu_type="RTX 6000 Ada"):
    """Print complete analysis"""
    print("=" * 80)
    print("VIDEO COMPLEXITY ANALYSIS")
    print("=" * 80)
    print(f"\nVideo Specifications:")
    print(f"  Resolution: {width}×{height}")
    print(f"  Frames: {frames}")
    print(f"  GPU: {gpu_type}")
    
    res_factor, frame_factor, complexity = calculate_complexity(width, height, frames)
    
    print(f"\nComplexity Factors:")
    print(f"  Resolution factor: {res_factor:.2f}x (vs 1080p)")
    print(f"  Frame factor: {frame_factor:.2f}x (vs 127 frames)")
    print(f"  Combined complexity: {complexity:.2f}x")
    
    scale_factor, complexity_level = get_scale_factor(complexity)
    
    print(f"\nComplexity Level: {complexity_level}")
    print(f"  Adaptive scaling: {int(scale_factor * 100)}% of base settings")
    
    base_settings, scaled_settings = get_settings(scale_factor)
    
    print(f"\nSettings Adjustment:")
    print(f"  decode_chunk_size: {base_settings['decode_chunk_size']} → {scaled_settings['decode_chunk_size']}")
    print(f"  window_size: {base_settings['window_size']} → {scaled_settings['window_size']}")
    print(f"  overlap: {base_settings['overlap']} → {scaled_settings['overlap']}")
    
    vram_needed = estimate_vram(res_factor, frame_factor)
    print(f"\nMemory Requirements:")
    print(f"  Estimated VRAM needed: {vram_needed:.1f} GB")
    print(f"  With adaptive scaling: Feasible on 48GB GPU")
    
    time_minutes = estimate_processing_time(complexity, gpu_type)
    time_hours = time_minutes / 60
    
    print(f"\nProcessing Time Estimate:")
    if time_minutes < 60:
        print(f"  Estimated time: {time_minutes:.0f} minutes")
    else:
        print(f"  Estimated time: {time_hours:.1f} hours ({time_minutes:.0f} minutes)")
    
    # Cost estimation (assuming $1/hour for RTX 6000 Ada)
    cost_per_hour = {
        "RTX 6000 Ada": 1.0,
        "A100 80GB": 3.0,
        "RTX 4090": 0.6,
        "RTX 3090": 0.3,
        "A5000": 0.5,
    }
    
    cost = (time_hours) * cost_per_hour.get(gpu_type, 1.0)
    
    print(f"\nCost Estimate:")
    print(f"  Estimated cost: ${cost:.2f} per video")
    
    # Recommendations
    print(f"\nRecommendations:")
    if complexity > 40:
        print(f"  ⚠️  EXTREME complexity - processing will take {time_hours:.1f} hours")
        print(f"  💡 Consider processing in segments for faster results")
        print(f"  💡 Or reduce resolution to 1440p or 1080p")
    elif complexity > 20:
        print(f"  ⚠️  Very high complexity - processing will take {time_hours:.1f} hours")
        print(f"  💡 Consider processing in segments")
    elif complexity > 10:
        print(f"  ℹ️  High complexity - adaptive scaling will be applied")
    else:
        print(f"  ✅ Normal complexity - will process efficiently")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 4:
        print("Usage: python calculate_video_complexity.py <width> <height> <frames> [gpu_type]")
        print("\nExamples:")
        print("  python calculate_video_complexity.py 1920 1080 127")
        print("  python calculate_video_complexity.py 3840 2160 1440 'RTX 6000 Ada'")
        print("\nSupported GPUs:")
        print("  - RTX 6000 Ada (default)")
        print("  - A100 80GB")
        print("  - RTX 4090")
        print("  - RTX 3090")
        print("  - A5000")
        sys.exit(1)
    
    width = int(sys.argv[1])
    height = int(sys.argv[2])
    frames = int(sys.argv[3])
    gpu_type = sys.argv[4] if len(sys.argv) > 4 else "RTX 6000 Ada"
    
    print_analysis(width, height, frames, gpu_type)
    
    # Common presets
    print("\n" + "=" * 80)
    print("COMMON VIDEO PRESETS")
    print("=" * 80)
    
    presets = [
        ("1080p Short", 1920, 1080, 127),
        ("1080p Medium", 1920, 1080, 500),
        ("1440p Medium", 2560, 1440, 500),
        ("4K Short", 3840, 2160, 360),
        ("4K Medium", 3840, 2160, 720),
        ("4K Long (Your case)", 3840, 2160, 1440),
    ]
    
    print(f"\n{'Preset':<25} {'Complexity':<12} {'Scale':<8} {'Time':<15} {'Cost':<10}")
    print("-" * 80)
    
    for name, w, h, f in presets:
        _, _, comp = calculate_complexity(w, h, f)
        scale, _ = get_scale_factor(comp)
        time_min = estimate_processing_time(comp, gpu_type)
        time_hours = time_min / 60
        cost = time_hours * 1.0  # Assuming $1/hour
        
        if time_min < 60:
            time_str = f"{time_min:.0f} min"
        else:
            time_str = f"{time_hours:.1f} hrs"
        
        print(f"{name:<25} {comp:>6.1f}x      {int(scale*100):>3}%     {time_str:<15} ${cost:.2f}")
