VSTUI_MOD_DIR := $(USERMOD_DIR)
VSTUI_SOURCE_DIR := $(realpath $(VSTUI_MOD_DIR))
VSTUI_ROOT := $(abspath $(VSTUI_SOURCE_DIR)/../..)

CFLAGS_USERMOD += \
    -I$(VSTUI_MOD_DIR) \
    -I$(VSTUI_ROOT)/src/protocol/include

SRC_USERMOD_C += $(VSTUI_MOD_DIR)/modvstui.c
