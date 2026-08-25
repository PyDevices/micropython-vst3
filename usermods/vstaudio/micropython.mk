VSTAUDIO_MOD_DIR := $(USERMOD_DIR)
VSTAUDIO_SOURCE_DIR := $(realpath $(VSTAUDIO_MOD_DIR))
VSTAUDIO_ROOT := $(abspath $(VSTAUDIO_SOURCE_DIR)/../..)

CFLAGS_USERMOD += \
    -Wno-error=double-promotion \
    -I$(VSTAUDIO_MOD_DIR) \
    -I$(VSTAUDIO_ROOT)/protocol/include

SRC_USERMOD_C += $(VSTAUDIO_MOD_DIR)/modvstaudio.c
SRC_USERMOD_C += $(VSTAUDIO_MOD_DIR)/vstaudio_dsp.c
