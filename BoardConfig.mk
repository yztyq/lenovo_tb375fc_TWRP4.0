#
# TB375FC (Lenovo Xiaoxin Pad Pro 12.7 2025) — TWRP 4.0 / twrp-16.0
# Layout and build style follow the ZTE SM88XX (RedMagic 11 Pro+) tree, but
# this device is MediaTek MT6897: no libinit, no QCOM bits, and there is no
# standalone recovery partition — the recovery rides in vendor_boot.
#
# Every geometry number below was measured from the stock image
# F:\YX\TB375FC_ZUX_1.1.04.287_Tool\image\vendor_boot.img
# (67,108,864 B, MD5 E60D9F853E08CDE9D099EA1143D760F8, header v4).
#
DEVICE_PATH := device/lenovo/tb375fc

# For building with minimal manifest
ALLOW_MISSING_DEPENDENCIES := true
BUILD_BROKEN_DUP_RULES := true
BUILD_BROKEN_ELF_PREBUILT_PRODUCT_COPY_FILES := true
BUILD_BROKEN_PLUGIN_VALIDATION := soong-libaosprecovery_defaults soong-libguitwrp_defaults soong-libminuitwrp_defaults soong-vold_defaults

# Architecture
TARGET_ARCH := arm64
TARGET_ARCH_VARIANT := armv8-2a
TARGET_CPU_ABI := arm64-v8a
TARGET_CPU_VARIANT := generic
TARGET_CPU_VARIANT_RUNTIME := cortex-a715
TARGET_2ND_ARCH := arm
TARGET_2ND_ARCH_VARIANT := armv8-2a
TARGET_2ND_CPU_ABI := armeabi-v7a
TARGET_2ND_CPU_VARIANT := generic

# Power
ENABLE_CPUSETS := true
ENABLE_SCHEDBOOST := true

# Bootloader / platform
TARGET_NO_BOOTLOADER := true
TARGET_BOARD_PLATFORM := mt6897
TARGET_BOOTLOADER_BOARD_NAME := mt8792

# Kernel: the stock vendor_boot carries NO kernel segment - the v4 vendor_boot
# header has no kernel_size field at all, and KernelAddr 0x40000000 is just the
# load address the bootloader uses for the kernel shipped in the stock boot.img
# (ANDROID! header v4, kernel_size 16,543,287). So the tree must neither
# rebuild nor package a kernel, and must not point at the manifest prebuilts
# (kernel/prebuilts/6.1/arm64 is not synced by twrp-16.0 and does not exist).
TARGET_NO_KERNEL := true
BOARD_KERNEL_IMAGE_NAME := Image
BOARD_BOOT_HEADER_VERSION := 4
BOARD_KERNEL_PAGESIZE := 4096
BOARD_KERNEL_BASE := 0x3fff8000
BOARD_KERNEL_OFFSET := 0x00008000
BOARD_RAMDISK_OFFSET := 0x26f08000
BOARD_TAGS_OFFSET := 0x07c88000
BOARD_DTB_OFFSET := 0x07c88000
BOARD_MKBOOTIMG_ARGS += --header_version $(BOARD_BOOT_HEADER_VERSION)
BOARD_MKBOOTIMG_ARGS += --pagesize $(BOARD_KERNEL_PAGESIZE)
BOARD_MKBOOTIMG_ARGS += --base $(BOARD_KERNEL_BASE)
BOARD_MKBOOTIMG_ARGS += --kernel_offset $(BOARD_KERNEL_OFFSET)
BOARD_MKBOOTIMG_ARGS += --ramdisk_offset $(BOARD_RAMDISK_OFFSET)
BOARD_MKBOOTIMG_ARGS += --tags_offset $(BOARD_TAGS_OFFSET)
BOARD_MKBOOTIMG_ARGS += --dtb_offset $(BOARD_DTB_OFFSET)
BOARD_RAMDISK_USE_LZ4 := true

# DTB verified from the stock image (411,876 B)
# AOSP16 only knows BOARD_PREBUILT_DTBIMAGE_DIR when BOARD_INCLUDE_DTB_IN_BOOTIMG
# is true: build/make/core/Makefile runs `cat $(BOARD_PREBUILT_DTBIMAGE_DIR)/*.dtb`
# into $(PRODUCT_OUT)/dtb.img (board_config.mk:985 requires the flag to be true).
# TARGET_PREBUILT_DTB is not an AOSP variable, so dtb.img had no generating rule
# and ninja died with: "'dtb.img', needed by 'vendor_boot.img', missing and no
# known rule to make it". The single .dtb below is the stock dtb segment,
# 411,876 B, MD5 c04d985375c5ed4196d3df00a28d370d.
BOARD_PREBUILT_DTBIMAGE_DIR := $(DEVICE_PATH)/prebuilt/dtb_dir
BOARD_INCLUDE_DTB_IN_BOOTIMG := true

# vendor_boot as recovery (no recovery partition on this tablet)
BOARD_USES_GENERIC_KERNEL_IMAGE := true
BOARD_MOVE_RECOVERY_RESOURCES_TO_VENDOR_BOOT := true
BOARD_INCLUDE_RECOVERY_RAMDISK_IN_VENDOR_BOOT := true
TARGET_NO_RECOVERY := true
BOARD_VENDOR_BOOTIMAGE_PARTITION_SIZE := 67108864
BOARD_VENDOR_CMDLINE := bootopt=64S3,32N2,64N2

# A/B
AB_OTA_UPDATER := true
AB_OTA_PARTITIONS := boot init_boot vendor_boot dtbo vbmeta vbmeta_system vbmeta_vendor

# Verified boot — we only replace vendor_boot, never vbmeta
BOARD_AVB_ENABLE := true

# Partitions
BOARD_PROPERTY_OVERRIDES_SPLIT_ENABLED := true
BOARD_SUPER_PARTITION_SIZE := 9126805504
BOARD_SUPER_PARTITION_GROUPS := main
BOARD_MAIN_SIZE := 9122611200
BOARD_MAIN_PARTITION_LIST := odm odm_dlkm product system system_ext vendor vendor_dlkm
BOARD_USES_METADATA_PARTITION := true
BOARD_USERDATAIMAGE_FILE_SYSTEM_TYPE := f2fs
BOARD_SYSTEMIMAGE_FILE_SYSTEM_TYPE := erofs
BOARD_VENDORIMAGE_FILE_SYSTEM_TYPE := erofs
BOARD_PRODUCTIMAGE_FILE_SYSTEM_TYPE := erofs
BOARD_SYSTEM_EXTIMAGE_FILE_SYSTEM_TYPE := erofs
BOARD_ODMIMAGE_FILE_SYSTEM_TYPE := erofs
# board_config.mk:803 aborts lunch when TARGET_COPY_OUT_VENDOR_DLKM is
# 'vendor_dlkm' but neither BOARD_PREBUILT_VENDOR_DLKMIMAGE nor
# BOARD_VENDOR_DLKMIMAGE_FILE_SYSTEM_TYPE is set; odm_dlkm is checked the same
# way. Recovery never builds these images, so any valid type satisfies the
# check; ext4 avoids needing erofs build tools.
BOARD_VENDOR_DLKMIMAGE_FILE_SYSTEM_TYPE := ext4
BOARD_ODM_DLKMIMAGE_FILE_SYSTEM_TYPE := ext4
# No BOARD_SYSTEM_DLKMIMAGE_* on purpose: this tablet has no system_dlkm
# partition (absent from BOARD_MAIN_PARTITION_LIST above and from the stock
# fstab). Setting it aborts lunch at board_config.mk:906 with
# "TARGET_COPY_OUT_SYSTEM_DLKM must be set to 'system_dlkm' to use a
# system_dlkm image", because that variable defaults to
# $(TARGET_COPY_OUT_SYSTEM)/dlkm.
TARGET_USERIMAGES_USE_F2FS := true
TARGET_USES_EROFS := true

# File systems / tools
RECOVERY_SDCARD_ON_DATA := true
TARGET_USES_MKE2FS := true
TW_ENABLE_FS_COMPRESSION := true
TW_INCLUDE_FUSE_EXFAT := true
TW_INCLUDE_FUSE_NTFS := true
TW_INCLUDE_NTFS_3G := true
TW_INCLUDE_EROFS := true
TW_INCLUDE_7ZA := true
TW_INCLUDE_REPACKTOOLS := true
TW_INCLUDE_RESETPROP := true
TW_INCLUDE_LIBRESETPROP := true
TW_ENABLE_ALL_PARTITION_TOOLS := true

# Crypto — FBE v2 + metadata encryption (confirmed on device:
# ro.crypto.state=encrypted, ro.crypto.type=file)
TW_INCLUDE_CRYPTO := true
TW_INCLUDE_CRYPTO_FBE := true
TW_INCLUDE_FBE_METADATA_DECRYPT := true
TW_USE_FSCRYPT_POLICY := 2
TW_INCLUDE_CRYPTO_FBE_ICE := true

# Recovery
BOARD_EXCLUDE_KERNEL_FROM_RECOVERY_IMAGE := true
TARGET_RECOVERY_PIXEL_FORMAT := RGBX_8888
TW_INCLUDE_FASTBOOTD := true
TW_NO_NETWORK := false
TW_SKIP_ADDITIONAL_FSTAB := true
TARGET_RECOVERY_FSTAB := $(DEVICE_PATH)/recovery/root/system/etc/recovery.fstab

# Display: 2944 x 1840 landscape panel
TW_THEME := portrait_hdpi
TW_SCREEN_W := 2944
TW_SCREEN_H := 1840
TARGET_SCREEN_WIDTH := 2944
TARGET_SCREEN_HEIGHT := 1840
TW_MAX_BRIGHTNESS := 2047
TW_DEFAULT_BRIGHTNESS := 600
TW_NO_SCREEN_BLANK := true
TW_SCREEN_BLANK_ON_BOOT := false
TW_FRAMERATE := 120
TW_NO_HAPTICS := true
TW_BRIGHTNESS_PATH := "/sys/class/leds/lcd-backlight/brightness"
TW_CUSTOM_CPU_TEMP_PATH := "/sys/class/thermal/thermal_zone8/temp"
TW_INPUT_BLACKLIST := "gpio-keys"

# Debug
TARGET_USES_LOGD := true
TWRP_INCLUDE_LOGCAT := true
TARGET_RECOVERY_DEVICE_MODULES += debuggerd
TARGET_RECOVERY_DEVICE_MODULES += strace

# Version — real values from the installed ZUXOS 1.1.04.287, never 2099-xx.
# (KeyMint binds blobs to the ROM's own values; the recovery must not lie.)
PLATFORM_VERSION := 16
PLATFORM_VERSION_LAST_STABLE := 16
PLATFORM_SECURITY_PATCH := 2025-09-05
VENDOR_SECURITY_PATCH := 2024-10-05
BOOT_SECURITY_PATCH := 2025-09-05
TW_DEVICE_VERSION := TB375FC

# Other
TW_EXCLUDE_APEX := true
TW_EXCLUDE_DEFAULT_USB_INIT := true
TW_DEFAULT_LANGUAGE := zh_CN
TW_EXTRA_LANGUAGES := true
TW_USE_TOOLBOX := true
TW_USE_SERIALNO_PROPERTY_FOR_DEVICE_ID := true
# Modules: the recovery ramdisk ships 222 .ko plus modules.load.recovery
# (212 entries, including nt36532.ko and the panel-alpha-* drivers), so init
# loads them from the list. Do NOT name individual modules here — earlier a
# nonexistent mtk_tinysys_scp.ko was referenced and init logged "service not
# found" on every boot.

# COPY
TARGET_COPY_OUT_VENDOR := vendor
TARGET_COPY_OUT_PRODUCT := product
TARGET_COPY_OUT_SYSTEM_EXT := system_ext
TARGET_COPY_OUT_ODM := odm
TARGET_COPY_OUT_VENDOR_DLKM := vendor_dlkm
TARGET_COPY_OUT_ODM_DLKM := odm_dlkm
