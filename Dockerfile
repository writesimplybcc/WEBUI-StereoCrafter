# Dockerfile for StereoCrafter WEBUI (Runpod - Downloads weights on startup)
# This creates a lightweight image that downloads weights fresh on each container start

FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04
FROM johnsdoes/stereocrafter-webui:base

# ============================================================
# Set working directory
# ============================================================
WORKDIR /workspace/WEBUI-StereoCrafter

# Copy ALL your code (this replaces/adds to the base StereoCrafter files)
# Core files
COPY webui.py .
COPY requirements-docker.txt .


# Your WEBUI folders
COPY gui/ ./gui/
COPY stereocrafter_ui/ ./stereocrafter_ui/
COPY dependency/ ./dependency/

#for development. to quick test run
COPY completed_output/ ./completed_output/
COPY final_videos/ ./final_videos/
COPY input_source_clips/ ./input_source_clips/
COPY output_depthmaps/ ./output_depthmaps/
COPY output_splatted/ ./output_splatted/
# Startup scripts
COPY runpod-docker-startup.sh .

# Set executable permission for startup scripts
RUN chmod +x runpod-docker-startup.sh

# Default command - run startup script which downloads weights then starts app
CMD ["bash", "runpod-docker-startup.sh"]