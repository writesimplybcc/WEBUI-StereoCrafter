# Contributing to StereoCrafter WEBUI

## 🎯 About This Project

This is a **web-based UI fork** of the original [StereoCrafter](https://github.com/TencentARC/StereoCrafter) project by Tencent ARC Lab and by [Enoky](https://github.com/enoky/StereoCrafter) for the GUI implementation. 

### Why a Web UI?

The original StereoCrafter uses CLI and Enoky tkinter-based desktop GUIs, which work great locally but have limitations:

- **Limited to local hardware** - You're stuck with the GPU you bought. You cannot increase the VRAM.
- **No remote access** - You can't process videos from anywhere.
- **Resource intensive** - High-end GPUs are expensive to own. Yet they output results faster.
- **OS, Batch and UI** - StereoCrafter is command-line usage only and can't do batch video file processing. Enoky is GUI-based and batch-processing enabled, but the python code is optimized for Windows 10/11 and might generate errors running on Linux/MacOS.

### Our Solution: Cloud-Ready Web Interface

By converting to a **Gradio-based web UI**, we enabled:

✅ **RunPod Integration** - Access high-end GPUs (RTX 4090, A6000) for pennies per hour  
✅ **Remote Processing** - Process videos from any device with a browser  
✅ **Cost Effective** - Pay only for GPU time you use, not ownership  
✅ **Scalability** - Spin up multiple instances for batch processing  
✅ **Accessibility** - Share processing power with team members  

**Example Cost Savings:**
- RTX 4090 ownership: ~$1,600 upfront
- RunPod RTX 4090: ~$0.50/hour (only when processing)
- Process 10 hours/month: $5 vs $1,600 investment

### Honorable Mention

All credit for the core StereoCrafter technology goes to the original authors at **Tencent ARC Lab**. This project simply wraps their excellent work in a web interface for cloud deployment.

Original Paper: [StereoCrafter: Diffusion-based Generation of Long and High-fidelity Stereoscopic 3D from Monocular Videos](https://arxiv.org/abs/2409.07447)

## 📁 File Browser Integration

This project now includes **File Browser** (https://filebrowser.org) for enhanced file management capabilities:

### Features Added:
- **Modern Web File Manager** - Drag-and-drop file operations, directory navigation
- **Advanced File Operations** - Upload, download, create, rename, move, delete files
- **User Authentication** - Secure access control with configurable permissions
- **Multiple File Formats** - Support for images, videos, documents, archives
- **Responsive Interface** - Works on desktop and mobile devices

### Integration Options:

#### Option 1: Docker Compose (Recommended)
```bash
# 1. Copy and edit environment variables
cp .env.example .env
# Edit .env file with your credentials

# 2. Pre-initialize File Browser (optional, for cloud deployment)
./preinit-filebrowser.sh

# 3. Start both services
docker-compose up -d

# Access:
# - StereoCrafter: http://localhost:7860
# - File Browser: http://localhost:8080
```

#### Option 1.5: Cloud Deployment (RunPod/Vast.AI)
```bash
# 1. Set environment variables before pod launch
export FB_USERNAME="your_username"
export FB_PASSWORD="your_secure_password"

# 2. Or create .env file and upload to pod
cp .env.example .env
# Edit with your credentials, then upload to pod

# 3. Launch pod with docker-compose
docker-compose up -d
```

#### Option 2: Standalone Installation
```bash
# Download latest File Browser binary
curl -fsSL https://filebrowser.org/get.sh | bash

# Configure and run
filebrowser config init
filebrowser config set --address 0.0.0.0 --port 8080 --root /path/to/stereocrafter/data
filebrowser users add admin admin --perm.admin
filebrowser
```

#### Option 3: Side-by-Side with Existing File Manager
The File Manager tab now shows both the original StereoCrafter file manager and a link to the external File Browser instance.

### Configuration
- **Default Credentials**: admin / stereocrafter2026 (change in production!)
- **Shared Volumes**: File Browser mounts the same directories as StereoCrafter
- **Security**: Configured with appropriate permissions for file management

### Project Status

⚠️ **This is a passion project built in free time!**

This codebase is:
- **Functional but not optimized** - It works, but there's room for improvement
- **Built with enthusiasm** - Created out of love for the technology, not commercial purposes
- **Community-driven** - Your contributions can help make it better!

We welcome optimizations, bug fixes, and feature improvements. This is a learning project for everyone involved!

Change Log:
1) GPU and VRAM size will be automatically identified at startup. This will help with code optimization.
2) Code is optimized for low ( 12GB ), mid ( 32 GB ) and high (48 GB ) VRAM setups. After identifying GPU VRAM, these values will be automatically channged for optimization: Chunk size, window size, frame overlap, frame chunk, bathc chunk size, and processing chunk size.
3) 4K video can now be processed. But it will take a long time even with an RTX 5090 32GB VRAM. Only use with GPUs with 48 VRAM or higher.


----
## 🚀 Runpod Setup Guide

### 1. Select Pod Template
*   Navigate to **Pod Template**
*   Select **All**
*   Choose **Runpod Pytorch 2.8.0**

### 2. Configure Hardware
*   Click **Configure Pod**
*   Select GPU: **RTX 6000 Ada**
NOTE: Do not select a GPU that is below 48GB VRAM or GPUs that are not using Lovelace architecture. RTX 6000 Ada is the minimum GPU you should run this version of StereoCrafter.

### 3. Edit Container Settings
Under **Pod Template**, click **Edit** and enter the following:

| Setting | Value |
| :--- | :--- |
| **Container Name** | `johnsdoes/stereocrafter-webui:latest` |
| **Container Disk** | `300 GB` *(Cost: ~$0.042/hr)* |
| **Volume Disk** | `0 GB` |
| **Expose HTTP Ports** | `7860` |

### 4. Environment Variables
*   **Key:** `HF_TOKEN`
*   **Value:** `PASTE your huggingface read token HERE`

### 5. Deploy
*   Click **Set Overrides**
*   Select **Deploy On-Demand**

---

Thank you for your interest in contributing! This guide will help you set up the project locally, make changes, and submit your contributions.

## 🚀 Local Setup
Note: This StereoCrafter fork is meant to be run on cloud-based GPUs. Scroll down near the end of the document on for how to run it.

### 📋 Prerequisites

Before you begin, ensure you have:

- **Git**: [Download here](https://git-scm.com/downloads)
- **Python 3.12**: [Download here](https://www.python.org/downloads)
- **CUDA 12.8**: [Download here](https://developer.nvidia.com/cuda-12-8-0-download-archive) (for GPU support)
- **FFmpeg**: [Installation guide](https://techtactician.com/how-to-install-ffmpeg-and-add-it-to-path-on-windows/)
- **HuggingFace Account**: [Sign up here](https://huggingface.co/join) (HF_TOKEN needed for model downloads)

Verify installations:
```bash
git --version
python --version
ffmpeg -version
```

### Step 1: Clone the Original StereoCrafter Repository

```bash
# Clone the original repository
git clone https://github.com/enoky/StereoCrafter.git
cd StereoCrafter

# Checkout the specific commit we're based on
git checkout 2a1d473
```

**Why this specific commit?**

This WEBUI was developed and tested against commit `2a1d473` of enoky's StereoCrafter fork. This commit is known to be stable and compatible with our web interface.

**Can I use a newer commit?**

Yes, you can try! As long as the core pipeline structure remains the same, newer commits should work. To use the latest:

```bash
# Skip this step
git checkout 2a1d473
# if you already did, simply. to fetch latest pull
git pull
```

**UPDATE** : Latest commit tested successfully. No errors found `1026d0d` 26 FEB 2026

However, if you encounter issues with newer commits:
- The pipeline API might have changed
- New dependencies might be required
- File paths or function signatures might differ

If you want to help test compatibility with newer commits, that's a great contribution! Just note which commit you're using when reporting issues.

### Step 2: Clone the WEBUI Patch Repository

```bash
# Clone the WEBUI repository (in a separate location)
cd ..
git clone https://github.com/keemzin/WEBUI-StereoCrafter.git
```

### Step 3: Merge/Replaced all WEBUI Files into StereoCrafter

```bash
# Copy WEBUI files into the StereoCrafter folder
# This preserves the original StereoCrafter files and adds WEBUI components
cd StereoCrafter
cp -r ../WEBUI-StereoCrafter/gui ./
cp -r ../WEBUI-StereoCrafter/stereocrafter_ui ./
cp ../WEBUI-StereoCrafter/webui.py ./
cp ../WEBUI-StereoCrafter/requirements.txt ./
```

**Windows users:** Use `xcopy` or File Explorer to copy the folders:
```cmd
xcopy /E /I ..\WEBUI-StereoCrafter\gui .\gui
xcopy /E /I ..\WEBUI-StereoCrafter\stereocrafter_ui .\stereocrafter_ui
copy ..\WEBUI-StereoCrafter\webui.py .
copy ..\WEBUI-StereoCrafter\requirements.txt .
```

### Step 4: Download Model Weights

Create a `weights` folder and download the required models:

```bash
# Create weights folder
mkdir weights
cd weights

# Download models using git
git clone https://huggingface.co/TencentARC/StereoCrafter
git clone https://huggingface.co/tencent/DepthCrafter
git clone https://huggingface.co/stabilityai/stable-video-diffusion-img2vid-xt-1-1

cd ..
```

### Step 5: Set Up Python Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Upgrade pip
python -m pip install --upgrade pip
```

### Step 6: Install Dependencies

```bash
# Install Python packages
pip install -r requirements.txt
```

### Step 7: Run the WEBUI

```bash
# Start the web interface
python webui.py
```

The WEBUI will open in your browser at `http://localhost:7860`

## 🔧 Making Changes

### Project Structure

Only modify files in these locations (per `global-rules.md`):
- `webui.py` - Main application entry point
- `gui/` - GUI components (legacy, being phased out)
- `stereocrafter_ui/` - New WEBUI components (Gradio-based)

**Do NOT modify:**
- `pipelines/` - Core processing pipelines
- `core/` - Core functionality
- `dependency/` - External dependencies
- Other original enoky/StereoCrafter files

### Development Workflow

1. **Create a new branch for your feature:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** in the allowed folders:
   - `webui.py`
   - `gui/`
   - `stereocrafter_ui/`

3. **Test your changes:**
   ```bash
   python webui.py
   ```

4. **Check for errors:**
   - Test all affected features
   - Verify no console errors
   - Test on different video resolutions if applicable

## 📤 Submitting Your Contribution

### Step 1: Commit Your Changes

```bash
# Check what files you've modified
git status

# Add your changes
git add webui.py
git add stereocrafter_ui/
git add gui/

# Commit with a descriptive message
git commit -m "Add feature: Brief description of your changes"
```

**Commit Message Guidelines:**
- Use present tense ("Add feature" not "Added feature")
- Be descriptive but concise
- Reference issue numbers if applicable

Examples:
```
Add manual preview selector to splatting UI
Fix inpainting pipeline loading for local weights
Update file manager with pipeline folder shortcuts
```

### Step 2: Push to Your Fork

First, fork the repository on GitHub, then:

```bash
# Push your branch to your fork
git push myfork feature/your-feature-name
```

### Step 3: Create a Pull Request

1. Go to https://github.com/keemzin/WEBUI-StereoCrafter
2. Click "New Pull Request"
3. Select your branch from your fork
4. Fill in the PR template:

```markdown
## Description
Brief description of what this PR does

## Changes Made
- List of specific changes
- Another change
- etc.

## Testing
How you tested these changes

## Screenshots (if applicable)
Add screenshots showing the changes

## Checklist
- [ ] Code follows project structure (only modified webui.py, gui/, stereocrafter_ui/)
- [ ] Tested locally and works as expected
- [ ] No console errors
- [ ] Updated documentation if needed
```

5. Click "Create Pull Request"

## 🐛 Reporting Issues

If you find a bug but don't know how to fix it:

1. Go to the Issues page
2. Click "New Issue"
3. Provide:
   - Clear description of the problem
   - Steps to reproduce
   - Expected vs actual behavior
   - Screenshots/logs if applicable
   - Your system info (OS, Python version, GPU)

## 💡 Tips for Contributors

### Code Style
- Follow existing code style in the project
- Use meaningful variable names
- Add comments for complex logic
- Keep functions focused and small

### Testing
- Test with different video resolutions
- Test with different parameter combinations
- Check memory usage for large videos
- Verify UI responsiveness

### Documentation
- Update docstrings for new functions
- Add inline comments for complex code
- Update README if adding new features
- Include usage examples

### Common Issues

**Import errors:**
```bash
# Make sure you're in the virtual environment
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Reinstall requirements
pip install -r requirements.txt
```

**CUDA errors:**
- Verify CUDA 12.8 is installed
- Check GPU drivers are up to date
- Ensure PyTorch detects your GPU: `python -c "import torch; print(torch.cuda.is_available())"`

**Model download fails:**
- Check your HuggingFace token is valid
- Ensure you have accepted the model licenses on HuggingFace
- Try using Python download method instead of `uv`

## 📞 Getting Help

- **Questions:** Open a discussion on the repository
- **Bugs:** Open an issue with details
- **Feature requests:** Open an issue with the "enhancement" label

## 🙏 Thank You!

Your contributions help make StereoCrafter WEBUI better for everyone. We appreciate your time and effort!

If you’d like to support this project, please consider registering for RunPod using my referral link:
https://runpod.io?ref=5r6ik1wp ( keemzin )
https://runpod.io?ref=seyfcia9 ( writesimply.bcc )

Your support helps me troubleshoot issues, test new features, and continue developing the project. Currently, I’m relying mostly on free credits for testing, so every bit of support helps keep the project alive. 🚀

