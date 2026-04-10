# ComfyUI TY LTX Desktop Bridge v1.1.0 - Release Notes

## 发布信息

- **版本号**: 1.1.0
- **发布日期**: 2024-12
- **兼容性**: LTX Desktop 2.3+, ComfyUI 最新版
- **升级类型**: 功能增强版本 (向后兼容)

## 版本说明

v1.1.0 是一个重要的功能增强版本,完全适配 LTX Desktop 2.3+ 前端的新功能。本次更新保持了与 v1.0 的完全向后兼容性,所有旧版工作流无需修改即可运行。

## 新增功能

### 1. LoRA 支持 ✨
- 新增 `TY LTX Desktop List LoRAs` 节点
- 新增 `TY LTX Desktop Set LoRA Path` 节点
- 视频生成节点支持 `lora_path` 和 `lora_strength` 参数
- 支持 .safetensors, .ckpt, .pt, .bin 格式

### 2. 多关键帧控制 🎬
- 视频生成节点新增 `keyframe_images` 可选输入
- 支持 2-5 张参考图片
- 自动计算帧位置和强度
- 智能插值减少闪烁

### 3. 自定义推理步数 ⚙️
- 新增 `inference_steps` 参数 (1-50 步)
- 默认 8 步快速生成
- 灵活控制质量和速度

### 4. 自定义模型路径 📁
- 新增 `model_path` 参数
- 新增 `TY LTX Desktop List Models` 节点
- 支持自定义 checkpoint

### 5. 低显存模式 💾
- 新增 `TY LTX Desktop Low VRAM Mode` 节点
- 减少 20-30% 峰值显存使用
- 适用于 <12GB 显存的 GPU

## 技术改进

### API 集成
- `/api/loras` - LoRA 文件列表
- `/api/lora-dir` - LoRA 目录管理
- `/api/models` - 模型文件列表
- `/api/system/low-vram-mode` - 低显存模式控制
- `/api/system/reset-state` - 状态重置
- 增强的 `/api/generate` 支持所有新参数

### 代码质量
- 完整的类型注解
- 改进的错误处理
- 优化的内存管理
- 更好的日志记录

## 文档更新

### 新增文档
- `CHANGELOG.md` - 详细更新日志
- `UPGRADE_GUIDE.md` - 升级指南
- `FEATURES_COMPARISON.md` - 功能对比表
- `UPDATE_SUMMARY.md` - 更新总结
- `QUICK_REFERENCE.md` - 快速参考卡片
- `README_CN.md` - 完整中文文档
- `VERSION_1.1.0_RELEASE_NOTES.md` - 本文档

### 更新文档
- `README.md` - 完整功能文档
- `examples workflows/README.md` - 示例说明

## 示例工作流

### 新增示例
- `lora_video_generation.json` - LoRA 增强视频生成
- `multi_keyframe_video.json` - 多关键帧控制视频生成

### 保留示例
- `text_to_image.json`
- `text_to_video.json`
- `image_to_video.json`
- `upscale_video.json`
- `qwen3_tts_to_ltx_video.json`

## 兼容性

### 向后兼容 ✅
- 所有 v1.0 工作流无需修改
- 新参数都有合理默认值
- 不使用新功能时行为与 v1.0 完全一致

### 系统要求
- **最低**: LTX Desktop 2.3
- **推荐**: LTX Desktop 2.3.1+
- **Python**: 3.8+
- **ComfyUI**: 最新版

### 显存要求
| 配置 | 最低显存 | 推荐显存 |
|------|---------|---------|
| 540p, 8步 | 6GB | 8GB |
| 720p, 8步 | 8GB | 10GB |
| 1080p, 8步 | 10GB | 12GB |
| 1080p, 16步 + LoRA | 12GB | 16GB |

## 安装和升级

### 全新安装
1. 下载 v1.1.0 插件包
2. 解压到 `ComfyUI/custom_nodes/ComfyUI_TY_LTX_Desktop_Bridge`
3. 重启 ComfyUI
4. 导入示例工作流测试

### 从 v1.0 升级
1. 备份现有工作流 (可选)
2. 删除旧版插件文件夹
3. 复制新版插件文件夹
4. 重启 ComfyUI
5. 现有工作流自动兼容

详细升级指南请参考 [UPGRADE_GUIDE.md](UPGRADE_GUIDE.md)

## 使用建议

### 快速开始
1. 使用 `TY LTX Desktop Config` 配置连接
2. 尝试基础的文生视频工作流
3. 逐步探索新功能

### LoRA 使用
1. 使用 `TY LTX Desktop List LoRAs` 浏览可用 LoRA
2. 复制路径到 `lora_path` 参数
3. 调整 `lora_strength` (推荐 0.8-1.2)
4. 生成并观察效果

### 多关键帧使用
1. 准备 2-5 张风格相似的参考图
2. 使用 `ImageBatch` 节点组合
3. 连接到 `keyframe_images` 输入
4. 自动插值生成平滑过渡

### 性能优化
- **显存充足** (>12GB): 使用默认设置
- **显存有限** (8-12GB): 启用低显存模式
- **显存紧张** (<8GB): 低显存模式 + 降低分辨率 + 减少步数

## 已知问题

### 当前限制
1. 多关键帧最多支持 5 张图片
2. LoRA 强度范围 0.0-2.0
3. 推理步数范围 1-50
4. 低显存模式可能略微增加生成时间

### 解决方案
- 所有限制都有技术原因,未来版本可能会改进
- 如遇问题请查看文档或提交反馈

## 测试建议

### 基础测试
1. ✅ 运行所有旧版示例工作流
2. ✅ 测试文本生成图片
3. ✅ 测试文本生成视频
4. ✅ 测试图片生成视频

### 新功能测试
1. ✅ 测试 LoRA 加载和应用
2. ✅ 测试多关键帧视频生成
3. ✅ 测试不同推理步数
4. ✅ 测试低显存模式

### 压力测试
1. 高分辨率 + 高步数
2. 多关键帧 + LoRA 组合
3. 长时长视频生成
4. 连续多次生成

## 反馈和支持

### 文档资源
- [README.md](README.md) - 完整功能文档
- [README_CN.md](README_CN.md) - 中文说明
- [UPGRADE_GUIDE.md](UPGRADE_GUIDE.md) - 升级指南
- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - 快速参考

### 问题排查
1. 查看 ComfyUI 控制台错误信息
2. 确认 LTX Desktop 2.3+ 正常运行
3. 检查端口 3000 是否可访问
4. 验证文件路径是否正确

## 未来计划

### 可能的功能
- 实时生成进度显示
- 批量处理支持
- 更多相机运动预设
- 负面提示词模板
- 工作流模板库

### 持续改进
- 性能优化
- 更好的错误提示
- 更多示例工作流
- 社区反馈集成

## 致谢

感谢所有测试和反馈的用户,你们的建议让这个插件变得更好!

---

**版本**: 1.1.0  
**发布日期**: 2024-12  
**状态**: 稳定版  
**兼容性**: LTX Desktop 2.3+, ComfyUI 最新版
