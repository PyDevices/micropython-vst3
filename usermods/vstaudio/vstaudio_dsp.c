// DSP nodes the effects library needs that audioif does not provide:
//
//   vstaudio.Dynamics  - envelope-follower gain computer: compressor,
//                        limiter, downward expander, gate, and transient
//                        shaper, with an optional high-passed detector for
//                        de-essing. Sits in an audiosample chain like any
//                        audioif effect: construct, play(source), output.
//
//   vstaudio.Splitter  - fans one audiosample out to several taps with
//                        independent read cursors over a shared ring, so a
//                        single host input can feed parallel branches
//                        (exciter, Haas widener, multiband splits) that a
//                        Mixer then sums.
//
// Both process signed 16-bit stereo, the engine chain's native format.

#include "audiocore/__init__.h"
#include "py/obj.h"
#include "py/runtime.h"

#include <math.h>
#include <stdint.h>
#include <string.h>

// ---------------------------------------------------------------- Dynamics

enum {
    VSTAUDIO_DYN_COMPRESS = 0,
    VSTAUDIO_DYN_LIMIT = 1,
    VSTAUDIO_DYN_EXPAND = 2,
    VSTAUDIO_DYN_GATE = 3,
    VSTAUDIO_DYN_TRANSIENT = 4,
};

#define DYN_FRAMES 256u

typedef struct vstaudio_dynamics_obj {
    audiosample_base_t base;
    mp_obj_t source;
    int mode;
    float threshold_db;
    float ratio;
    float knee_db;
    float makeup_gain;      // linear
    float attack_coef;
    float release_coef;
    float attack_gain_db;   // transient mode
    float sustain_gain_db;
    float sidechain_coef;   // one-pole low-pass state coef; 0 = full band
    float sidechain_lp[2];
    float envelope;         // main detector, linear 0..1
    float fast_env;         // transient mode detectors
    float slow_env;
    float gain_reduction_db;
    int16_t buffer[DYN_FRAMES * 2];
    // leftover source data between output chunks
    const int16_t *pending;
    uint32_t pending_frames;
} vstaudio_dynamics_obj_t;

static float ms_to_coef(float ms, float sample_rate) {
    if (ms <= 0.0f) {
        return 1.0f;
    }
    return 1.0f - expf(-1000.0f / (ms * sample_rate));
}

static float db_to_gain(float db) {
    return expf(db * 0.115129254649702f);
}

static float gain_to_db(float gain) {
    return logf(gain < 1e-6f ? 1e-6f : gain) * 8.68588963806504f;
}

static void dynamics_apply_kwargs(vstaudio_dynamics_obj_t *self,
    const mp_map_t *kw) {
    // sample_rate first: the millisecond-to-coefficient conversions below
    // depend on it, and keyword order must not matter.
    for (size_t i = 0; i < kw->alloc; ++i) {
        if (mp_map_slot_is_filled(kw, i) &&
            mp_obj_str_get_qstr(kw->table[i].key) == MP_QSTR_sample_rate) {
            self->base.sample_rate =
                (uint32_t)mp_obj_get_int(kw->table[i].value);
        }
    }
    for (size_t i = 0; i < kw->alloc; ++i) {
        if (!mp_map_slot_is_filled(kw, i)) {
            continue;
        }
        qstr name = mp_obj_str_get_qstr(kw->table[i].key);
        if (name == MP_QSTR_sample_rate) {
            continue;
        }
        float value = (float)mp_obj_get_float(kw->table[i].value);
        if (name == MP_QSTR_threshold_db) {
            self->threshold_db = value;
        } else if (name == MP_QSTR_ratio) {
            self->ratio = value < 1.0f ? 1.0f : value;
        } else if (name == MP_QSTR_knee_db) {
            self->knee_db = value < 0.0f ? 0.0f : value;
        } else if (name == MP_QSTR_makeup_db) {
            self->makeup_gain = db_to_gain(value);
        } else if (name == MP_QSTR_attack_ms) {
            self->attack_coef = ms_to_coef(value, (float)self->base.sample_rate);
        } else if (name == MP_QSTR_release_ms) {
            self->release_coef = ms_to_coef(value, (float)self->base.sample_rate);
        } else if (name == MP_QSTR_attack_gain_db) {
            self->attack_gain_db = value;
        } else if (name == MP_QSTR_sustain_gain_db) {
            self->sustain_gain_db = value;
        } else if (name == MP_QSTR_sidechain_hz) {
            self->sidechain_coef = value <= 0.0f ? 0.0f
                : 1.0f - expf(-6.283185307f * value /
                              (float)self->base.sample_rate);
        } else {
            mp_raise_msg_varg(&mp_type_TypeError,
                MP_ERROR_TEXT("unknown Dynamics option '%q'"), name);
        }
    }
}

static mp_obj_t vstaudio_dynamics_make_new(const mp_obj_type_t *type,
    size_t n_args, size_t n_kw, const mp_obj_t *all_args) {
    mp_arg_check_num(n_args, n_kw, 0, 1, true);
    vstaudio_dynamics_obj_t *self = mp_obj_malloc(vstaudio_dynamics_obj_t, type);
    self->base.sample_rate = 48000;
    self->base.max_buffer_length = sizeof(self->buffer);
    self->base.bits_per_sample = 16;
    self->base.channel_count = 2;
    self->base.samples_signed = 1;
    self->base.single_buffer = false;
    self->source = MP_OBJ_NULL;
    self->mode = n_args >= 1 ? (int)mp_obj_get_int(all_args[0])
                             : VSTAUDIO_DYN_COMPRESS;
    self->threshold_db = -24.0f;
    self->ratio = 4.0f;
    self->knee_db = 6.0f;
    self->makeup_gain = 1.0f;
    self->attack_gain_db = 0.0f;
    self->sustain_gain_db = 0.0f;
    self->sidechain_coef = 0.0f;
    self->sidechain_lp[0] = 0.0f;
    self->sidechain_lp[1] = 0.0f;
    self->envelope = 0.0f;
    self->fast_env = 0.0f;
    self->slow_env = 0.0f;
    self->gain_reduction_db = 0.0f;
    self->pending = NULL;
    self->pending_frames = 0;

    mp_map_t kw_map;
    mp_map_init_fixed_table(&kw_map, n_kw, all_args + n_args);
    self->attack_coef = 0.0f;
    self->release_coef = 0.0f;
    dynamics_apply_kwargs(self, &kw_map);
    if (self->attack_coef == 0.0f) {
        self->attack_coef = ms_to_coef(10.0f, (float)self->base.sample_rate);
    }
    if (self->release_coef == 0.0f) {
        self->release_coef = ms_to_coef(120.0f, (float)self->base.sample_rate);
    }
    return MP_OBJ_FROM_PTR(self);
}

static mp_obj_t vstaudio_dynamics_play(mp_obj_t self_in, mp_obj_t sample) {
    vstaudio_dynamics_obj_t *self = MP_OBJ_TO_PTR(self_in);
    (void)audiosample_check(sample);
    self->source = sample;
    self->pending = NULL;
    self->pending_frames = 0;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(vstaudio_dynamics_play_obj,
    vstaudio_dynamics_play);

static mp_obj_t vstaudio_dynamics_set(size_t n_args, const mp_obj_t *args,
    mp_map_t *kw_args) {
    vstaudio_dynamics_obj_t *self = MP_OBJ_TO_PTR(args[0]);
    (void)n_args;
    dynamics_apply_kwargs(self, kw_args);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(vstaudio_dynamics_set_obj, 1,
    vstaudio_dynamics_set);

static mp_obj_t vstaudio_dynamics_gain_reduction_db(mp_obj_t self_in) {
    vstaudio_dynamics_obj_t *self = MP_OBJ_TO_PTR(self_in);
    return mp_obj_new_float((mp_float_t)self->gain_reduction_db);
}
static MP_DEFINE_CONST_FUN_OBJ_1(vstaudio_dynamics_gain_reduction_db_obj,
    vstaudio_dynamics_gain_reduction_db);

static float dynamics_gain_db(vstaudio_dynamics_obj_t *self, float env_db) {
    const float over = env_db - self->threshold_db;
    switch (self->mode) {
        case VSTAUDIO_DYN_LIMIT:
            return over > 0.0f ? -over : 0.0f;
        case VSTAUDIO_DYN_EXPAND: {
            if (over >= 0.0f) {
                return 0.0f;
            }
            float cut = over * (self->ratio - 1.0f);
            return cut < -60.0f ? -60.0f : cut;
        }
        case VSTAUDIO_DYN_GATE: {
            if (over >= 0.0f) {
                return 0.0f;
            }
            float cut = over * 8.0f;
            return cut < -80.0f ? -80.0f : cut;
        }
        case VSTAUDIO_DYN_COMPRESS:
        default: {
            const float half_knee = self->knee_db * 0.5f;
            const float slope = 1.0f - 1.0f / self->ratio;
            if (over <= -half_knee) {
                return 0.0f;
            }
            if (over < half_knee && self->knee_db > 0.0f) {
                const float x = over + half_knee;
                return -slope * x * x / (2.0f * self->knee_db);
            }
            return -slope * over;
        }
    }
}

static audioio_get_buffer_result_t vstaudio_dynamics_get_buffer(
    mp_obj_t self_in, bool single_channel_output, uint8_t channel,
    uint8_t **buffer, uint32_t *buffer_length) {
    (void)single_channel_output;
    (void)channel;
    vstaudio_dynamics_obj_t *self = MP_OBJ_TO_PTR(self_in);
    uint32_t produced = 0;
    while (produced < DYN_FRAMES) {
        if (self->pending_frames == 0) {
            if (self->source == MP_OBJ_NULL) {
                break;
            }
            uint8_t *raw = NULL;
            uint32_t raw_bytes = 0;
            audioio_get_buffer_result_t result = audiosample_get_buffer(
                self->source, false, 0, &raw, &raw_bytes);
            if (result == GET_BUFFER_ERROR || raw == NULL || raw_bytes < 4) {
                break;
            }
            self->pending = (const int16_t *)raw;
            self->pending_frames = raw_bytes / 4u;
        }
        // fast/slow coefficients for the transient detectors are fixed
        const float fast_att = ms_to_coef(1.0f, (float)self->base.sample_rate);
        const float fast_rel = ms_to_coef(50.0f, (float)self->base.sample_rate);
        const float slow_att = ms_to_coef(25.0f, (float)self->base.sample_rate);
        const float slow_rel = ms_to_coef(300.0f, (float)self->base.sample_rate);
        while (self->pending_frames != 0 && produced < DYN_FRAMES) {
            const float left = (float)self->pending[0] / 32768.0f;
            const float right = (float)self->pending[1] / 32768.0f;
            float det_l = left;
            float det_r = right;
            if (self->sidechain_coef > 0.0f) {
                self->sidechain_lp[0] += self->sidechain_coef *
                    (left - self->sidechain_lp[0]);
                self->sidechain_lp[1] += self->sidechain_coef *
                    (right - self->sidechain_lp[1]);
                det_l = left - self->sidechain_lp[0];
                det_r = right - self->sidechain_lp[1];
            }
            float level = fabsf(det_l);
            const float level_r = fabsf(det_r);
            if (level_r > level) {
                level = level_r;
            }
            float gain_db;
            if (self->mode == VSTAUDIO_DYN_TRANSIENT) {
                self->fast_env += (level > self->fast_env ? fast_att : fast_rel)
                    * (level - self->fast_env);
                self->slow_env += (level > self->slow_env ? slow_att : slow_rel)
                    * (level - self->slow_env);
                const float diff = gain_to_db(self->fast_env + 1e-5f) -
                                   gain_to_db(self->slow_env + 1e-5f);
                float norm = diff / 6.0f;
                if (norm > 1.0f) {
                    norm = 1.0f;
                } else if (norm < -1.0f) {
                    norm = -1.0f;
                }
                gain_db = norm > 0.0f ? self->attack_gain_db * norm
                                      : self->sustain_gain_db * -norm;
            } else {
                const bool rising = level > self->envelope;
                self->envelope += (rising ? self->attack_coef
                                          : self->release_coef)
                    * (level - self->envelope);
                gain_db = dynamics_gain_db(self,
                    gain_to_db(self->envelope + 1e-6f));
            }
            self->gain_reduction_db = gain_db;
            const float gain = db_to_gain(gain_db) * self->makeup_gain;
            float out_l = left * gain * 32768.0f;
            float out_r = right * gain * 32768.0f;
            if (out_l > 32767.0f) {
                out_l = 32767.0f;
            } else if (out_l < -32768.0f) {
                out_l = -32768.0f;
            }
            if (out_r > 32767.0f) {
                out_r = 32767.0f;
            } else if (out_r < -32768.0f) {
                out_r = -32768.0f;
            }
            self->buffer[produced * 2] = (int16_t)out_l;
            self->buffer[produced * 2 + 1] = (int16_t)out_r;
            self->pending += 2;
            --self->pending_frames;
            ++produced;
        }
    }
    if (produced == 0) {
        memset(self->buffer, 0, sizeof(self->buffer));
        produced = DYN_FRAMES;
    }
    *buffer = (uint8_t *)self->buffer;
    *buffer_length = produced * 4u;
    return GET_BUFFER_MORE_DATA;
}

static void vstaudio_dynamics_reset_buffer(mp_obj_t self_in,
    bool single_channel_output, uint8_t channel) {
    (void)single_channel_output;
    (void)channel;
    vstaudio_dynamics_obj_t *self = MP_OBJ_TO_PTR(self_in);
    self->pending = NULL;
    self->pending_frames = 0;
    self->envelope = 0.0f;
    self->fast_env = 0.0f;
    self->slow_env = 0.0f;
}

static const mp_rom_map_elem_t vstaudio_dynamics_locals_table[] = {
    { MP_ROM_QSTR(MP_QSTR_play), MP_ROM_PTR(&vstaudio_dynamics_play_obj) },
    { MP_ROM_QSTR(MP_QSTR_set), MP_ROM_PTR(&vstaudio_dynamics_set_obj) },
    { MP_ROM_QSTR(MP_QSTR_gain_reduction_db),
      MP_ROM_PTR(&vstaudio_dynamics_gain_reduction_db_obj) },
};
static MP_DEFINE_CONST_DICT(vstaudio_dynamics_locals,
    vstaudio_dynamics_locals_table);

static const audiosample_p_t vstaudio_dynamics_proto = {
    MP_PROTO_IMPLEMENT(MP_QSTR_protocol_audiosample)
    .reset_buffer = vstaudio_dynamics_reset_buffer,
    .get_buffer = vstaudio_dynamics_get_buffer,
};

MP_DEFINE_CONST_OBJ_TYPE(
    vstaudio_dynamics_type,
    MP_QSTR_Dynamics,
    MP_TYPE_FLAG_NONE,
    make_new, vstaudio_dynamics_make_new,
    locals_dict, &vstaudio_dynamics_locals,
    protocol, &vstaudio_dynamics_proto
    );

// ---------------------------------------------------------------- Splitter

#define SPLITTER_RING_FRAMES 8192u
#define SPLITTER_MAX_TAPS 4u
#define SPLITTER_CHUNK_FRAMES 256u

typedef struct vstaudio_splitter_obj vstaudio_splitter_obj_t;

typedef struct vstaudio_splitter_tap_obj {
    audiosample_base_t base;
    vstaudio_splitter_obj_t *owner;
    uint32_t index;
} vstaudio_splitter_tap_obj_t;

struct vstaudio_splitter_obj {
    mp_obj_base_t obj_base;
    mp_obj_t source;
    uint32_t tap_count;
    uint32_t write_pos;
    uint32_t read_pos[SPLITTER_MAX_TAPS];
    mp_obj_t taps[SPLITTER_MAX_TAPS];
    int16_t ring[SPLITTER_RING_FRAMES * 2];
    int16_t silence[SPLITTER_CHUNK_FRAMES * 2];
};

extern const mp_obj_type_t vstaudio_splitter_tap_type;

static void splitter_pull(vstaudio_splitter_obj_t *self) {
    if (self->source == MP_OBJ_NULL) {
        return;
    }
    uint8_t *raw = NULL;
    uint32_t raw_bytes = 0;
    audioio_get_buffer_result_t result = audiosample_get_buffer(
        self->source, false, 0, &raw, &raw_bytes);
    if (result == GET_BUFFER_ERROR || raw == NULL) {
        return;
    }
    const int16_t *frames = (const int16_t *)raw;
    uint32_t count = raw_bytes / 4u;
    while (count-- != 0) {
        const uint32_t at = (self->write_pos % SPLITTER_RING_FRAMES) * 2u;
        self->ring[at] = frames[0];
        self->ring[at + 1u] = frames[1];
        frames += 2;
        ++self->write_pos;
        for (uint32_t tap = 0; tap < self->tap_count; ++tap) {
            if (self->write_pos - self->read_pos[tap] > SPLITTER_RING_FRAMES) {
                ++self->read_pos[tap];   // an unread tap must not wedge the ring
            }
        }
    }
}

static audioio_get_buffer_result_t vstaudio_splitter_tap_get_buffer(
    mp_obj_t self_in, bool single_channel_output, uint8_t channel,
    uint8_t **buffer, uint32_t *buffer_length) {
    (void)single_channel_output;
    (void)channel;
    vstaudio_splitter_tap_obj_t *tap = MP_OBJ_TO_PTR(self_in);
    vstaudio_splitter_obj_t *self = tap->owner;
    if (self->write_pos == self->read_pos[tap->index]) {
        splitter_pull(self);
    }
    uint32_t available = self->write_pos - self->read_pos[tap->index];
    if (available == 0) {
        memset(self->silence, 0, sizeof(self->silence));
        *buffer = (uint8_t *)self->silence;
        *buffer_length = sizeof(self->silence);
        return GET_BUFFER_MORE_DATA;
    }
    const uint32_t start = self->read_pos[tap->index] % SPLITTER_RING_FRAMES;
    uint32_t run = SPLITTER_RING_FRAMES - start;
    if (run > available) {
        run = available;
    }
    if (run > SPLITTER_CHUNK_FRAMES) {
        run = SPLITTER_CHUNK_FRAMES;
    }
    *buffer = (uint8_t *)&self->ring[start * 2u];
    *buffer_length = run * 4u;
    self->read_pos[tap->index] += run;
    return GET_BUFFER_MORE_DATA;
}

static void vstaudio_splitter_tap_reset_buffer(mp_obj_t self_in,
    bool single_channel_output, uint8_t channel) {
    (void)self_in;
    (void)single_channel_output;
    (void)channel;
}

static const audiosample_p_t vstaudio_splitter_tap_proto = {
    MP_PROTO_IMPLEMENT(MP_QSTR_protocol_audiosample)
    .reset_buffer = vstaudio_splitter_tap_reset_buffer,
    .get_buffer = vstaudio_splitter_tap_get_buffer,
};

MP_DEFINE_CONST_OBJ_TYPE(
    vstaudio_splitter_tap_type,
    MP_QSTR_SplitterTap,
    MP_TYPE_FLAG_NONE,
    protocol, &vstaudio_splitter_tap_proto
    );

static mp_obj_t vstaudio_splitter_make_new(const mp_obj_type_t *type,
    size_t n_args, size_t n_kw, const mp_obj_t *all_args) {
    mp_arg_check_num(n_args, n_kw, 1, 2, true);
    mp_obj_t source = all_args[0];
    audiosample_base_t *sample = audiosample_check(source);
    uint32_t taps = n_args >= 2 ? (uint32_t)mp_obj_get_int(all_args[1]) : 2u;
    if (taps < 1u || taps > SPLITTER_MAX_TAPS) {
        mp_raise_ValueError(MP_ERROR_TEXT("taps must be 1..4"));
    }
    vstaudio_splitter_obj_t *self = mp_obj_malloc(vstaudio_splitter_obj_t, type);
    self->source = source;
    self->tap_count = taps;
    self->write_pos = 0;
    for (uint32_t index = 0; index < SPLITTER_MAX_TAPS; ++index) {
        self->read_pos[index] = 0;
        self->taps[index] = MP_OBJ_NULL;
    }
    for (uint32_t index = 0; index < taps; ++index) {
        vstaudio_splitter_tap_obj_t *tap =
            mp_obj_malloc(vstaudio_splitter_tap_obj_t,
                &vstaudio_splitter_tap_type);
        tap->base.sample_rate = sample->sample_rate;
        tap->base.max_buffer_length = SPLITTER_CHUNK_FRAMES * 4u;
        tap->base.bits_per_sample = 16;
        tap->base.channel_count = 2;
        tap->base.samples_signed = 1;
        tap->base.single_buffer = false;
        tap->owner = self;
        tap->index = index;
        self->taps[index] = MP_OBJ_FROM_PTR(tap);
    }
    return MP_OBJ_FROM_PTR(self);
}

static mp_obj_t vstaudio_splitter_tap(mp_obj_t self_in, mp_obj_t index_in) {
    vstaudio_splitter_obj_t *self = MP_OBJ_TO_PTR(self_in);
    const uint32_t index = (uint32_t)mp_obj_get_int(index_in);
    if (index >= self->tap_count) {
        mp_raise_ValueError(MP_ERROR_TEXT("tap index out of range"));
    }
    return self->taps[index];
}
static MP_DEFINE_CONST_FUN_OBJ_2(vstaudio_splitter_tap_obj_fun,
    vstaudio_splitter_tap);

static const mp_rom_map_elem_t vstaudio_splitter_locals_table[] = {
    { MP_ROM_QSTR(MP_QSTR_tap), MP_ROM_PTR(&vstaudio_splitter_tap_obj_fun) },
};
static MP_DEFINE_CONST_DICT(vstaudio_splitter_locals,
    vstaudio_splitter_locals_table);

MP_DEFINE_CONST_OBJ_TYPE(
    vstaudio_splitter_type,
    MP_QSTR_Splitter,
    MP_TYPE_FLAG_NONE,
    make_new, vstaudio_splitter_make_new,
    locals_dict, &vstaudio_splitter_locals
    );
