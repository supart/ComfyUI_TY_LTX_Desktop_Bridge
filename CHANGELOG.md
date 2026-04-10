# Changelog

All notable changes to `ComfyUI_TY_LTX_Desktop_Bridge` are documented here.

## [1.1.0] - 2026-04-10

### Added

- Public GitHub-ready example workflow pack
- Public input assets for the example workflows
- GitHub-safe workflow preview images with embedded ComfyUI metadata removed
- README homepage showcase for the maintained workflows

### Changed

- Plugin version normalized to `1.1.0` for the public release package
- Example workflow JSON files no longer contain hard-coded personal local paths
- Public examples now default to a safer `auto_start = false`
- Example file names are normalized to ASCII for easier GitHub linking and maintenance

### Kept

- Text-to-image, text-to-video, image-to-video, start/end frame, LoRA, VRAM control, history, and batch video features
- Compatibility with local `LTX2.3-1.0.3` and `LTX2.3-1.0.4` style desktop backends

## [1.0.0]

### Initial release

- Basic LTX Desktop bridge for ComfyUI
