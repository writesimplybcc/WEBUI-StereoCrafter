# Dockerfile for StereoCrafter WEBUI (Runpod - Downloads weights on startup)
# This creates a lightweight image that downloads weights fresh on each container start

FROM writesimplybcc/stereocrafter-webui:base

# ============================================================
# Set working directory
# ============================================================
WORKDIR /workspace/WEBUI-StereoCrafter

# Copy ALL your code (this replaces/adds to the base StereoCrafter files)
# Core files
COPY webui.py .
COPY requirements-docker.txt .
COPY WEBUI_StereoCrafter_GPU_Presets_Guide.md .
# Startup scripts
COPY download_weights.sh .
COPY start-with-filebrowser.sh .
COPY runpod-docker-startup.sh .

# Your WEBUI folders
COPY gui/ ./gui/
COPY stereocrafter_ui/ ./stereocrafter_ui/

# Dependencies
COPY pipelines/ ./pipelines/
COPY core/ ./core/
COPY depthcrafter/ ./depthcrafter/
COPY dependency/ ./dependency/


#for development. to quick test run
COPY output_inpainted/ ./output_inpainted/
COPY final_videos/ ./final_videos/
COPY input_source_clips/ ./input_source_clips/
COPY output_depthmaps/ ./output_depthmaps/
COPY output_splatted/ ./output_splatted/

# Install FileBrowser
RUN curl -fsSL https://raw.githubusercontent.com/filebrowser/get/master/get.sh | bash

# Copy startup script and fix line endings (Windows CRLF -> Linux LF)
COPY start-with-filebrowser.sh /workspace/start-with-filebrowser.sh
RUN sed -i 's/\r//' /workspace/start-with-filebrowser.sh \
        /workspace/WEBUI-StereoCrafter/runpod-docker-startup.sh && \
    chmod +x /workspace/start-with-filebrowser.sh \
             /workspace/WEBUI-StereoCrafter/runpod-docker-startup.sh

# Copy entrypoint script for RSA key injection
COPY entrypoint.sh /workspace/entrypoint.sh
RUN chmod +x /workspace/entrypoint.sh

# Expose ports
EXPOSE 7860 7878

# Use entrypoint to inject RSA key, then run the startup script
ENTRYPOINT ["/workspace/entrypoint.sh"]
CMD ["/workspace/start-with-filebrowser.sh"]