# gxm-ce-port

在 GitHub Actions 上编译 **Amlogic S912 / GXM（章鱼星球 Octopus-Planet）** 在
CoreELEC 21 内核（`linux-amlogic amlogic-4.9-20`）上的构建物。

## 产出什么

| 产物 | 说明 |
|---|---|
| `gxm_q201_2g_buildroot.dtb` | 章鱼星球机型设备树（2G 内存 / 千兆网口） |
| `amvdec_h264.ko` `amvdec_h265.ko` `amvdec_mpeg12.ko` `amvdec_vp9.ko` | GX 单路解码器 |
| `amvdec_ports.ko` `decoder_common.ko` `firmware.ko` `media_clock.ko` | 解码框架与固件加载 |
| `stream_input.ko` | **本次要验证的**：提供 `/dev/amstream_*`，libamcodec 依赖它 |

## 怎么跑

- 手动：`Actions` → `gxm-build` → `Run workflow`
- 自动：推 `gxm-v*` 标签（会同时发 Release）

产物在 job 的 Artifacts，构建摘要（各目录错误数 + 产物清单）在 Job Summary。

## 依赖与来源

| 项 | 值 |
|---|---|
| 内核 | `CoreELEC/linux-amlogic` 分支 `amlogic-4.9-20` |
| 媒体模块 | `CoreELEC/media_modules-aml` commit `1af2bb1`（CE 9.2 时代，含 GX 单路解码器与通用 `video_ucode.bin`） |

## 补丁（`ci/apply_gxm_patches.py`，5 处，幂等）

| # | 位置 | 改动 | 解决的报错 |
|---|---|---|---|
| 1 | `vframe.h` | `struct vframe_s` 加 `atomic_t use_cnt` | 29 条 |
| 2 | `v4lvideo_ext.h` | `struct file_private_data` 加两个 `ulong` 句柄 | 4 条 |
| 3 | `codec_mm.h` | 两个 5 参兼容壳（旧 alloc/free 签名 → 新 handle 式） | 4 条 |
| 4 | `aml_vcodec_util.c` / `vdec.c` | 3 处调用改指兼容壳 | — |
| 5 | 编译参数 | `-Wno-incompatible-pointer-types -Wno-int-conversion`（GCC13+ 把警告升为错误） | 4 条 |

另外两个必须的编译参数：

- `HOSTCFLAGS="-fcommon -Wno-error"`：老内核(4.9)配新 bison，`dtc` 会报 `yylloc` 多重定义
- 不传 `CONFIG_AMLOGIC_DVB`：DVB 子目录自动跳过；章鱼星球无 tuner/demod 硬件

## 已验证 / 未验证

| 项 | 状态 |
|---|---|
| dtb 编译 | ✅ 已实测（59886 字节） |
| 解码器 8 个 .ko | ✅ 已实测（错误数 0） |
| `stream_input.ko` | ⏳ **本次目标**：此前 Colab 跑到这一步时实例断连 |
| 上机运行 | ❌ 未开始 |

## 已知技术债

`codec_mm_dma_free_coherent_compat` 当前是**空实现**（只为过编译）。上机前必须改成
`alloc` 返回 handle、`free` 用同一 handle 的配对管理，否则每播一次泄漏一块显存。
