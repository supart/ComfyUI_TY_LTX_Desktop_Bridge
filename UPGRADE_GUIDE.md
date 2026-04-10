# Upgrade Guide: v1.0 to v1.1

This guide helps you upgrade from ComfyUI TY LTX Desktop Bridge v1.0 to v1.1.

## What's New in v1.1

Version 1.1 adds support for LTX Desktop 2.3+ features:
- LoRA model support
- Optional keyframe-image inputs on `TY LTX Desktop Generate Video`
- Custom inference steps
- Custom model paths
- Low VRAM mode
- Model and LoRA listing

## Compatibility

- **LTX Desktop Version**: Requires LTX Desktop 2.3 or later
- **ComfyUI**: Compatible with latest ComfyUI versions
- **Backward Compatibility**: All v1.0 workflows will continue to work

## Installation

### Fresh Install

1. Delete the old plugin folder:
   ```
   ComfyUI/custom_nodes/ComfyUI_TY_LTX_Desktop_Bridge
   ```

2. Copy the new v1.1 folder to the same location

3. Restart ComfyUI

### Upgrade Existing Installation

1. Backup your existing workflows (optional but recommended)

2. Replace the plugin folder with the new version

3. Restart ComfyUI

4. Re-import your workflows if you see any node errors

## Breaking Changes

**None!** Version 1.1 is fully backward compatible with v1.0 workflows.

All existing workflows will continue to work without modification. The new parameters are optional and have sensible defaults.

## New Node Parameters

### TY LTX Desktop Generate Video

New optional parameters (all have defaults):

- `inference_steps` (default: 8)
  - Controls generation quality
  - Range: 1-50 steps
  - Higher = better quality but slower

- `lora_path` (default: "")
  - Path to LoRA file
  - Leave empty to not use LoRA
  - Supports .safetensors, .ckpt, .pt, .bin

- `lora_strength` (default: 1.0)
  - LoRA application strength
  - Range: 0.0-2.0
  - Only used if lora_path is set

- `model_path` (default: "")
  - Path to custom checkpoint
  - Leave empty to use default model

New optional input:

- `keyframe_images` (IMAGE)
  - Connect multiple images as optional keyframe references
  - Automatically calculates frame positions and strengths
  - Use ImageBatch nodes to combine images

## New Nodes

### LoRA Management

- `TY LTX Desktop List LoRAs`
  - Lists available LoRA files
  - Input: config, lora_dir (optional)
  - Output: loras_json

- `TY LTX Desktop Set LoRA Path`
  - Helper node to set LoRA parameters
  - Input: config, lora_path, lora_strength
  - Output: lora_path, lora_strength

### Model Management

- `TY LTX Desktop List Models`
  - Lists available checkpoint models
  - Input: config, models_dir (optional)
  - Output: models_json

### System Control

- `TY LTX Desktop Low VRAM Mode`
  - Toggle low VRAM optimization
  - Input: config, enabled, apply_now
  - Output: config, status_json

## Migrating Workflows

### Basic Workflows (No Changes Needed)

If your workflow only uses basic features, no changes are needed:
- Text-to-image
- Text-to-video
- Image-to-video
- Audio-to-video

Simply re-import the workflow and it will work with the new plugin.

### Adding LoRA Support

To add LoRA to an existing video generation workflow:

1. Add `TY LTX Desktop List LoRAs` node (optional, for browsing)
2. Add `TY LTX Desktop Set LoRA Path` node
3. Connect to the video generation node's new inputs
4. Set your LoRA path and strength

See `examples workflows/T2V_加LORA_桌面桥接插件.json` for the maintained LoRA example.

### Optional Keyframe Inputs

If you want to pass multiple reference images into the video-generation node:

1. Load multiple images with `LoadImage` nodes
2. Combine them with `ImageBatch` nodes
3. Connect to the `keyframe_images` input
4. The plugin handles frame timing automatically

## Troubleshooting

### "Node not found" errors after upgrade

**Solution**: Restart ComfyUI completely (close and reopen)

### Old workflows show missing parameters

**Solution**: Re-import the workflow JSON file

### LoRA not loading

**Possible causes**:
- LoRA file path is incorrect
- LoRA file format not supported
- LTX Desktop backend not running

**Solution**: 
- Use `TY LTX Desktop List LoRAs` to verify the path
- Check that the file exists and is readable
- Ensure LTX Desktop 2.3+ is running

### Keyframe image input not working

**Possible causes**:
- Images not properly batched
- Less than 2 images provided

**Solution**:
- Use `ImageBatch` nodes to combine images
- Provide at least 2 images when using `keyframe_images`

### Low VRAM mode not helping

**Note**: Low VRAM mode is most effective on GPUs with 8-12GB VRAM. If you have less than 8GB, you may still encounter memory issues with high-resolution generation.

**Solution**:
- Try lower resolution settings
- Reduce inference steps
- Use shorter video durations

## Getting Help

If you encounter issues:

1. Check the [README.md](README.md) for detailed feature documentation
2. Review the [CHANGELOG.md](CHANGELOG.md) for all changes
3. Try the example workflows in `examples workflows/`
4. Check ComfyUI console for error messages
5. Ensure LTX Desktop 2.3+ is properly installed and running

## Rollback

If you need to rollback to v1.0:

1. Delete the v1.1 plugin folder
2. Restore your v1.0 backup
3. Restart ComfyUI

Note: v1.1 workflows using new features will not work in v1.0.
