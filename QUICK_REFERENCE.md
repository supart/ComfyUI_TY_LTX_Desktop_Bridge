# Quick Reference Card - ComfyUI TY LTX Desktop Bridge v1.1

## 快速开始

```
1. 安装: 复制到 ComfyUI/custom_nodes/
2. 重启: 重启 ComfyUI
3. 配置: 添加 TY LTX Desktop Config 节点
4. 生成: 连接生成节点开始创作
```

## 核心节点速查

### 配置节点
```
TY LTX Desktop Config
├─ base_url: http://127.0.0.1:3000
├─ launcher_root: D:\LTX2.3-1.0.3
├─ auto_start: true
└─ gpu_id: -1
```

### 视频生成节点
```
TY LTX Desktop Generate Video
├─ prompt: 提示词 (必填)
├─ resolution: 1080p/720p/540p
├─ aspect_ratio: 16:9/9:16
├─ duration: 5.0 秒
├─ fps: 24
├─ inference_steps: 8 (新)
├─ lora_path: "" (新)
├─ lora_strength: 1.0 (新)
└─ model_path: "" (新)

可选输入:
├─ image: 单张参考图
├─ start_frame + end_frame: 首尾帧
├─ keyframe_images: 多关键帧 (新)
└─ ref_audio: 音频输入
```

## 新功能速查

### LoRA 使用
```
1. List LoRAs → 获取 LoRA 列表
2. 复制路径 → lora_path
3. 设置强度 → lora_strength (0.8-1.2)
4. 生成视频
```

### 多关键帧
```
1. LoadImage × 3 → 加载 3 张图
2. ImageBatch → 组合图片
3. 连接到 keyframe_images
4. 自动插值生成
```

### 低显存模式
```
TY LTX Desktop Low VRAM Mode
├─ enabled: true
└─ apply_now: true

适用: <12GB 显存
效果: 减少 20-30% 显存使用
```

## 参数推荐值

### 快速预览
```
resolution: 540p
inference_steps: 4
duration: 3.0
fps: 24
```

### 标准质量
```
resolution: 720p
inference_steps: 8
duration: 5.0
fps: 24
```

### 高质量
```
resolution: 1080p
inference_steps: 12-16
duration: 5.0
fps: 24
lora_strength: 1.0
```

### 超高质量
```
resolution: 1080p
inference_steps: 20-30
duration: 10.0
fps: 24
+ 超分节点
```

## 显存使用参考

| 配置 | 显存需求 | 建议 |
|------|---------|------|
| 540p, 8步 | ~6GB | 入门级 |
| 720p, 8步 | ~8GB | 标准 |
| 1080p, 8步 | ~10GB | 推荐 |
| 1080p, 16步 | ~12GB | 高质量 |
| 1080p, 16步 + LoRA | ~14GB | 专业级 |

## 常见问题速查

### 连接失败
```
检查: LTX Desktop 是否运行
端口: 3000 是否被占用
路径: launcher_root 是否正确
```

### 显存不足
```
方案1: 启用低显存模式
方案2: 降低分辨率
方案3: 减少推理步数
方案4: 缩短视频时长
```

### LoRA 不生效
```
检查: 路径是否正确
格式: .safetensors/.ckpt/.pt/.bin
强度: 尝试 0.8-1.5 范围
```

### 多关键帧闪烁
```
原因: 图片差异过大
方案: 使用相似风格的图片
调整: 减少关键帧数量
```

## 工作流模板

### 基础文生视频
```
Config → Generate Video → Save Video
```

### LoRA 增强
```
Config → List LoRAs
      ↓
Set LoRA Path → Generate Video → Save Video
```

### 多关键帧
```
LoadImage × 3 → ImageBatch → Generate Video → Save Video
                              ↑
                           Config
```

### 完整流程
```
Config → Low VRAM Mode
      ↓
List LoRAs → Set LoRA Path
      ↓
LoadImage × 3 → ImageBatch → Generate Video → Upscale → Save
```

## 快捷键提示

```
Ctrl+Enter: 执行工作流
Ctrl+Shift+Enter: 执行选中节点
Ctrl+C/V: 复制粘贴节点
Delete: 删除节点
Ctrl+Z: 撤销
```

## 文档导航

```
README.md → 完整功能文档
README_CN.md → 中文说明
CHANGELOG.md → 更新日志
UPGRADE_GUIDE.md → 升级指南
FEATURES_COMPARISON.md → 功能对比
UPDATE_SUMMARY.md → 更新总结
examples workflows/ → 示例工作流
```

## 版本信息

```
当前版本: 1.1.0
发布日期: 2024-12
兼容性: LTX Desktop 2.3+
Python: 3.8+
ComfyUI: 最新版
```

## 技术支持

```
文档: 查看 README.md
示例: examples workflows/
错误: 检查 ComfyUI 控制台
后端: 确认 LTX Desktop 运行状态
```

---

**提示**: 将此文档保存为书签,随时查阅!
