#
# Product definition — TB375FC
#
DEVICE_PATH := device/lenovo/tb375fc

$(call inherit-product, $(DEVICE_PATH)/device.mk)

## Device identifier
PRODUCT_DEVICE  := tb375fc
PRODUCT_NAME    := twrp_tb375fc
PRODUCT_BRAND   := Lenovo
PRODUCT_MODEL   := TB375FC
PRODUCT_MANUFACTURER := Lenovo
PRODUCT_RELEASE_NAME := TB375FC

# Theme
TW_STATUS_ICONS_ALIGN := center

# init finds init.recovery.<ro.hardware>.rc; this tablet reports mt8792
PRODUCT_DEFAULT_PROPERTY_OVERRIDES += \
    ro.hardware=mt8792 \
    ro.board.platform=mt6897
