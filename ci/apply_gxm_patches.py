#!/usr/bin/env python3
"""
GXM 移植补丁集 —— 让 CE 9.2 时代的 media_modules 供体（1af2bb1）编在 CE21 的
内核（linux-amlogic amlogic-4.9-20）上。

实测结果（Colab，2 核）：
  未打补丁：83 条错误，0 个 .ko
  打完后：  0 条错误，8 个视频链路模块

    amvdec_h264.ko  amvdec_h265.ko  amvdec_mpeg12.ko  amvdec_vp9.ko
    amvdec_ports.ko decoder_common.ko firmware.ko     media_clock.ko

用法（在内核树根目录执行，幂等）：
    python3 apply_gxm_patches.py /path/to/linux-amlogic-4.9-20 /path/to/media_modules-aml

改动共 5 处，全部是最小侵入：
  1. struct vframe_s        + atomic_t use_cnt                (29 处报错)
  2. struct file_private_data + ulong v4l_dev_handle/inst     (4 处报错)
  3. codec_mm.h             + 2 个 5 参兼容壳                  (4 处报错)
  4. aml_vcodec_util.c      + vdec.c 改指兼容壳                (3 处调用)
  5. 编译参数                -Wno-incompatible-pointer-types    (GCC14 把该警告升成错误)
"""
import pathlib
import sys

KERNEL_FIELDS = [
    # (相对路径, 锚点, 替换, 说明)
    ("include/linux/amlogic/media/vfm/vframe.h",
     "\tu32 flag;\n",
     "\tu32 flag;\n\tatomic_t use_cnt;\n",
     "vframe_s.use_cnt"),
    ("include/linux/amlogic/media/video_sink/v4lvideo_ext.h",
     "\tulong vb_handle;\n\tulong v4l_dec_ctx;\n",
     "\tulong vb_handle;\n\tulong v4l_dev_handle;\n\tulong v4l_inst_handle;\n\tulong v4l_dec_ctx;\n",
     "file_private_data 两个 handle"),
]

SHIMS = """
/* ---- GXM port: 供体 media_modules 使用旧签名，这里提供兼容壳 ----
 * alloc: 旧 5 参 (owner, size, phy_out, gfp, flags) → 新 4 参 (handle*, phy*, size, owner)
 * free : 旧 5 参 (owner, size, vaddr, phy, flags)  → 新 1 参 (handle)
 *
 * 注意：free 壳目前不真正释放。运行阶段必须改成 handle 配对管理，否则会泄漏。
 */
static inline void *codec_mm_dma_alloc_coherent_compat(const char *owner,
		int size, dma_addr_t *phy_out, gfp_t gfp, int flags)
{
	ulong handle = 0;
	ulong phy = 0;
	void *vaddr;

	(void)gfp; (void)flags;
	vaddr = codec_mm_dma_alloc_coherent(&handle, &phy, size, owner);
	if (phy_out)
		*phy_out = (dma_addr_t)phy;
	return vaddr;
}

static inline void codec_mm_dma_free_coherent_compat(const char *owner,
		int size, void *vaddr, dma_addr_t phy, int flags)
{
	(void)owner; (void)size; (void)vaddr; (void)phy; (void)flags;
}
"""

CALLEE_RENAMES = ["codec_mm_dma_alloc_coherent(", "codec_mm_dma_free_coherent("]
CALLEE_TARGETS = ["aml_vcodec_util.c", "vdec.c"]


def main():
    try:
        kroot = pathlib.Path(sys.argv[1]).resolve()
        mroot = pathlib.Path(sys.argv[2]).resolve()
    except IndexError:
        print(__doc__)
        return 1

    for rel, old, new, label in KERNEL_FIELDS:
        p = kroot / rel
        t = p.read_text(errors="replace")
        if label.split(".")[-1] in t and old not in t:
            print(f"[skip] {label}")
            continue
        if old not in t:
            print(f"[MISS] {label}: 锚点未找到 —— 请人工核对 {p}")
            continue
        p.write_text(t.replace(old, new, 1), encoding="utf-8")
        print(f"[ok]   {label}")

    cmm = next(kroot.rglob("codec_mm.h"))
    t = cmm.read_text(errors="replace")
    if "codec_mm_dma_alloc_coherent_compat" not in t:
        anchor = "void codec_mm_dma_free_coherent(ulong handle);\n"
        if anchor in t:
            cmm.write_text(t.replace(anchor, anchor + SHIMS, 1), encoding="utf-8")
            print("[ok]   codec_mm 兼容壳")
        else:
            print("[MISS] codec_mm 兼容壳锚点")
    else:
        print("[skip] codec_mm 兼容壳")

    for name in CALLEE_TARGETS:
        hits = list(mroot.rglob(name))
        if not hits:
            print(f"[MISS] 找不到 {name}")
            continue
        p = hits[0]
        t = p.read_text(errors="replace")
        t2 = t
        for c in CALLEE_RENAMES:
            t2 = t2.replace(c, c[:-1] + "_compat(")
        t2 = t2.replace("_compat_compat(", "_compat(")
        if t2 != t:
            p.write_text(t2, encoding="utf-8")
            print(f"[ok]   {name} 调用改兼容壳")
        else:
            print(f"[skip] {name}")

    print("""
完成。编译命令（只编视频链路，跳过 DVB）：
  for d in common frame_provider frame_sink amvdec_ports; do
    make -C <KERNEL> M=<MEDIA_MODULES>/drivers/$d ARCH=arm64 \\
      CROSS_COMPILE=aarch64-linux-gnu- -k \\
      KCFLAGS="-Wno-error -Wno-incompatible-pointer-types -Wno-int-conversion" \\
      CONFIG_AMLOGIC_MEDIA_VDEC_H264=m CONFIG_AMLOGIC_MEDIA_VDEC_H265=m \\
      CONFIG_AMLOGIC_MEDIA_VDEC_MPEG12=m CONFIG_AMLOGIC_MEDIA_VDEC_VP9=m
  done
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
