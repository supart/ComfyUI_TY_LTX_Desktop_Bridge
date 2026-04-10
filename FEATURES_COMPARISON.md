# Features Comparison: v1.0 vs v1.1

## Quick Overview

| Feature | v1.0 | v1.1 | Notes |
|---------|------|------|-------|
| Text-to-Image | ✅ | ✅ | No changes |
| Text-to-Video | ✅ | ✅ | Enhanced with new parameters |
| Image-to-Video | ✅ | ✅ | Enhanced with new parameters |
| Audio-to-Video | ✅ | ✅ | No changes |
| Start/End Frame Control | ✅ | ✅ | No changes |
| Seed Control | ✅ | ✅ | No changes |
| GPU Switching | ✅ | ✅ | No changes |
| Output Directory Control | ✅ | ✅ | No changes |
| History Loading | ✅ | ✅ | No changes |
| **LoRA Support** | ❌ | ✅ | **NEW** |
| **Optional Keyframe Image Input** | ❌ | ✅ | In `Generate Video` |
| **Custom Inference Steps** | ❌ | ✅ | **NEW** |
| **Custom Model Path** | ❌ | ✅ | **NEW** |
| **Low VRAM Mode** | ❌ | ✅ | **NEW** |
| **LoRA Listing** | ❌ | ✅ | **NEW** |
| **Model Listing** | ❌ | ✅ | **NEW** |

## Detailed Feature Breakdown

### Core Generation Features

#### Text-to-Image Generation
- **v1.0**: Basic text-to-image with preset sizes and custom dimensions
- **v1.1**: Same as v1.0 (no changes)

#### Text-to-Video Generation
- **v1.0**: 
  - Basic text-to-video
  - Resolution control (540p, 720p, 1080p)
  - Aspect ratio (16:9, 9:16)
  - Duration and FPS control
  - Camera motion presets
  - Seed control
  
- **v1.1**: 
  - All v1.0 features PLUS:
  - Custom inference steps (1-50)
  - LoRA path and strength
  - Custom model path
  - Optional keyframe image input

#### Image-to-Video Generation
- **v1.0**: 
  - Single reference image
  - Start/end frame interpolation
  
- **v1.1**: 
  - All v1.0 features PLUS:
  - Multiple keyframe reference images (2-5 images)
  - Automatic keyframe strength calculation
  - LoRA support
  - Custom inference steps

#### Audio-to-Video Generation
- **v1.0**: 
  - ComfyUI AUDIO input
  - Local audio file path
  
- **v1.1**: Same as v1.0 (no changes)

### System Control Features

#### GPU Management
- **v1.0**: 
  - GPU switching
  - GPU memory clearing
  
- **v1.1**: 
  - All v1.0 features PLUS:
  - Low VRAM mode toggle
  - Better memory optimization

#### Output Management
- **v1.0**: 
  - Output directory control
  - Video saving with preview
  
- **v1.1**: Same as v1.0 (no changes)

### Asset Management Features

#### History Management
- **v1.0**: 
  - History listing
  - History item retrieval
  - Load history images
  
- **v1.1**: Same as v1.0 (no changes)

#### Model Management
- **v1.0**: No model management features
  
- **v1.1**: 
  - List available LoRA files
  - List available checkpoint models
  - Browse model directories

### New Nodes in v1.1

| Node Name | Category | Purpose |
|-----------|----------|---------|
| TY LTX Desktop List LoRAs | LoRA | Browse available LoRA files |
| TY LTX Desktop Set LoRA Path | LoRA | Configure LoRA settings |
| TY LTX Desktop Low VRAM Mode | System | Toggle low VRAM optimization |
| TY LTX Desktop List Models | Models | Browse available checkpoints |

### Enhanced Nodes in v1.1

| Node Name | New Parameters | Description |
|-----------|----------------|-------------|
| TY LTX Desktop Generate Video | `inference_steps` | Control generation quality (1-50 steps) |
| | `lora_path` | Path to LoRA file |
| | `lora_strength` | LoRA application strength (0.0-2.0) |
| | `model_path` | Path to custom checkpoint |
| | `keyframe_images` (input) | Multiple reference images |

## API Compatibility

### v1.0 API Endpoints Used
- `/health`
- `/api/generate` (basic parameters)
- `/api/generate-image`
- `/api/system/set-dir`
- `/api/system/switch-gpu`
- `/api/system/clear-gpu`
- `/api/system/upscale-video`
- `/api/system/history`
- `/api/system/file`

### v1.1 Additional API Endpoints
- `/api/system/reset-state` (state management)
- `/api/system/low-vram-mode` (memory optimization)
- `/api/loras` (LoRA listing)
- `/api/lora-dir` (LoRA directory management)
- `/api/models` (model listing)
- `/api/generate` (enhanced with new parameters)

## Backend Requirements

| Version | Minimum LTX Desktop Version | Recommended |
|---------|----------------------------|-------------|
| v1.0 | LTX Desktop 2.0+ | LTX Desktop 2.2 |
| v1.1 | LTX Desktop 2.3+ | LTX Desktop 2.3.1 |

## Performance Comparison

### Memory Usage
- **v1.0**: Standard memory usage
- **v1.1**: 
  - Standard mode: Same as v1.0
  - Low VRAM mode: 20-30% reduction in peak memory usage

### Generation Speed
- **v1.0**: Fixed 8 inference steps
- **v1.1**: 
  - Configurable steps (1-50)
  - Lower steps = faster generation
  - Higher steps = better quality

### Quality Options
- **v1.0**: Fixed quality settings
- **v1.1**: 
  - Adjustable via inference steps
  - LoRA styling options
  - Optional multi-image reference control

## Workflow Compatibility

### v1.0 Workflows in v1.1
- ✅ Fully compatible
- ✅ No modifications needed
- ✅ New parameters use sensible defaults

### v1.1 Workflows in v1.0
- ❌ Not compatible if using new features
- ⚠️ Basic workflows without new features may work
- ⚠️ Recommended to use v1.1 plugin for v1.1 workflows

## Migration Path

### From v1.0 to v1.1
1. Replace plugin folder
2. Restart ComfyUI
3. Existing workflows work immediately
4. Optionally add new features to workflows

### From v1.1 to v1.0 (Rollback)
1. Backup v1.1 workflows using new features
2. Replace plugin folder with v1.0
3. Restart ComfyUI
4. v1.0 workflows work, v1.1-specific features unavailable

## Recommended Use Cases

### When to Use v1.0
- Using LTX Desktop 2.0-2.2
- Don't need LoRA support
- Don't need optional keyframe-image inputs
- Simple workflows only

### When to Use v1.1
- Using LTX Desktop 2.3+
- Need LoRA support
- Need multiple reference images in `Generate Video`
- Need quality control via inference steps
- Limited GPU memory (use low VRAM mode)
- Want to browse available models/LoRAs

## Future Roadmap

Potential features for future versions:
- Real-time generation progress
- Batch processing support
- Advanced camera motion control
- Custom negative prompt presets
- Workflow templates
- Integration with more ComfyUI plugins

---

**Note**: This comparison is based on the official releases. Beta features and experimental functionality may vary.
