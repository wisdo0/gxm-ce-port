# gxm-ce-port

在 GitHub Actions 上编译 **Amlogic S912 / GXM（章鱼星球 Octopus-Planet）** 在
CoreELEC 21 内核（`linux-amlogic amlogic-4.9-20`）上的构建物。

## 当前状态：run #3 全绿

5 个构建目录（`common` / `frame_provider` / `frame_sink` / `amvdec_ports` / `stream_input`）
**全部 0 错误**，产出 **9 个 `.ko` + 1 个 dtb**。

## 产出什么

| 产物 | 大小 | 说明 |
|---|---|---|
| `gxm_q201_2g_buildroot.dtb` | 59886 B | 章鱼星球机型设备树（2G 内存 / 千兆网口） |
| `amvdec_h264.ko` `amvdec_h265.ko` `amvdec_mpeg12.ko` `amvdec_vp9.ko` | 512K/970K/360K/868K | GX 单路解码器 |
| `amvdec_ports.ko` `decoder_common.ko` | 5.0M / 2.4M | 解码框架 |
| `firmware.ko` `media_clock.ko` | 310K / 588K | 固件加载与时钟 |
| `stream_input.ko` | 2.7M | 提供 `/dev/amstream_*`，libamcodec 依赖它 |

全部 `.ko` 均为 ELF64 / AArch64（已本地校验魔数与 `e_machine`）。

> `amvideo` / `vfm` 不在模块包里——它们编进内核镜像。
> `meson64_defconfig` 已开 `CONFIG_AMLOGIC_MEDIA_VIDEO=y` / `VFM=y` / `CODEC_MM=y` / `CANVAS=y`。

## 怎么跑

- 手动：`Actions` → `gxm-build` → `Run workflow`
- 自动：推 `gxm-v*` 标签（会同时发 Release）

产物在 job 的 Artifacts，构建摘要（各目录错误数 + 产物清单）在 Job Summary。

## 依赖与来源

| 项 | 值 |
|---|---|
| 内核 | `CoreELEC/linux-amlogic` 分支 `amlogic-4.9-20` |
| 媒体模块 | `CoreELEC/media_modules-aml` commit `1af2bb1`（CE 9.2 时代，含 GX 单路解码器与通用 `video_ucode.bin`） |

## 补丁（`ci/apply_gxm_patches.py`，6 处，幂等）

| # | 位置 | 改动 | 解决的报错 |
|---|---|---|---|
| 1 | `vframe.h` | `struct vframe_s` 加 `atomic_t use_cnt` | 29 条 |
| 2 | `v4lvideo_ext.h` | `struct file_private_data` 加两个 `ulong` 句柄 | 4 条 |
| 3 | `codec_mm.h` | 两个 5 参兼容壳（旧 alloc/free 签名 → 新 handle 式） | 4 条 |
| 4 | `aml_vcodec_util.c` / `vdec.c` | 3 处调用改指兼容壳 | — |
| 5 | `aml_demod_common.h` | `aml_tuner` 加 `i2c_adp`；枚举补 `AM_DTV_DEMOD_AML`/`SI2168_1` | 5 条（DVB） |
| 6 | 编译参数 | `-Wno-incompatible-pointer-types -Wno-int-conversion`（GCC13+ 把警告升为错误） | 4 条 |

## 两个必须的编译参数（坑，别踩）

**1. `CONFIG_AMLOGIC_DVB=n` 必须显式传**

`drivers/stream_input/Makefile`：

```makefile
stream_input-objs += parser/dvb_common.o          # 无条件编入
obj-$(CONFIG_AMLOGIC_DVB) += parser/hw_demux/     # 门控
obj-$(CONFIG_AMLOGIC_DVB) += parser/demux/
obj-$(CONFIG_AMLOGIC_DVB) += parser/dvb_ci/
```

外部模块构建时该宏未定义，`obj-$(...)` 展开成 **`obj-`**，而 kbuild 把 `obj-`
视同 **`obj-y`**（不是 `obj-n`）。结果三个 DVB 目录照样被编，报 36 条错误。

**注意**：不能"整个跳过 `stream_input`"——它是 `/dev/amstream_*` 的提供者，
libamcodec 靠它连设备。正确做法是编它，但关掉 DVB 子目录。

**2. `HOSTCFLAGS="-fcommon -Wno-error"`**

老内核(4.9)配新 bison，`dtc` 链接会报 `yylloc` 多重定义（GCC10+ 默认 `-fno-common`）。

## 已验证 / 未验证

| 项 | 状态 |
|---|---|
| dtb 编译 | ✅ 59886 B，magic `d00dfeed`，`gxl_p212_2g` 残留 0 处 |
| 9 个 .ko | ✅ 错误数 0，全部 ELF64/AArch64 |
| `stream_input.ko` 含 amstream | ✅ 已校验 |
| 模块符号对内核解析 | ⏳ 需全量编 vmlinux 生成 `Module.symvers` 才能验证 |
| 上机运行 | ❌ 未开始 |

## 已知技术债

`codec_mm_dma_free_coherent_compat` 当前是**空实现**（只为过编译）。上机前必须改成
`alloc` 返回 handle、`free` 用同一 handle 的配对管理，否则每播一次泄漏一块显存。
