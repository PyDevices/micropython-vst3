#pragma once

// One IPlugView, serving the instrument and the effect alike. It blits a
// framebuffer, injects input, and replays parameter edits. It never
// interprets a pixel, and it knows nothing about sliders, patches or LVGL -
// everything visible is decided in the engine.
//
// The view is a child of whatever frame the host provides. It owns no
// top-level window, so "close the editor" can never mean "quit the engine":
// that distinction falls out of the structure rather than needing to be
// enforced.

#include "mpvst/shared_memory.h"
#include "mpvst/ui.h"

#include "pluginterfaces/gui/iplugviewcontentscalesupport.h"
#include "public.sdk/source/common/pluginview.h"

#include <cstdint>
#include <string>
#include <vector>

#if defined(_WIN32)
#define NOMINMAX
#include <windows.h>
#elif defined(__linux__)
#include "pluginterfaces/gui/iplugview.h"
#endif

namespace PyDevices::MicroPythonVST3 {

class Controller;

class Editor final : public Steinberg::CPluginView,
                     public Steinberg::IPlugViewContentScaleSupport
#if defined(__linux__)
    ,
                     public Steinberg::Linux::IEventHandler,
                     public Steinberg::Linux::ITimerHandler
#endif
{
public:
    Editor (Controller* owner, std::string mappingName,
            std::uint32_t generation);
    ~Editor () SMTG_OVERRIDE;

    // Told by the controller when the processor reports a new engine
    // generation, so a view that outlived a restart resyncs instead of
    // replaying input into a mapping nobody is reading.
    void mappingChanged (const std::string& mappingName,
                         std::uint32_t generation);

    Steinberg::tresult PLUGIN_API isPlatformTypeSupported (
        Steinberg::FIDString type) SMTG_OVERRIDE;
    Steinberg::tresult PLUGIN_API attached (void* parent,
                                            Steinberg::FIDString type) SMTG_OVERRIDE;
    Steinberg::tresult PLUGIN_API removed () SMTG_OVERRIDE;
    Steinberg::tresult PLUGIN_API onSize (Steinberg::ViewRect* newSize) SMTG_OVERRIDE;
    Steinberg::tresult PLUGIN_API canResize () SMTG_OVERRIDE
    {
        return Steinberg::kResultFalse;
    }
    Steinberg::tresult PLUGIN_API checkSizeConstraint (
        Steinberg::ViewRect* rect) SMTG_OVERRIDE;
    Steinberg::tresult PLUGIN_API onWheel (float distance) SMTG_OVERRIDE;

    Steinberg::tresult PLUGIN_API setContentScaleFactor (ScaleFactor factor) SMTG_OVERRIDE;

#if defined(__linux__)
    void PLUGIN_API onFDIsSet (Steinberg::Linux::FileDescriptor fd) SMTG_OVERRIDE;
    void PLUGIN_API onTimer () SMTG_OVERRIDE;
#endif

    OBJ_METHODS (Editor, Steinberg::CPluginView)
    DEFINE_INTERFACES
        DEF_INTERFACE (Steinberg::IPlugViewContentScaleSupport)
#if defined(__linux__)
        DEF_INTERFACE (Steinberg::Linux::IEventHandler)
        DEF_INTERFACE (Steinberg::Linux::ITimerHandler)
#endif
    END_DEFINE_INTERFACES (Steinberg::CPluginView)
    REFCOUNT_METHODS (Steinberg::CPluginView)

private:
    bool openMapping ();
    void closeMapping ();
    // One pass of the whole job: sample the frame, drain edits, repaint.
    void tick ();
    // Copy whatever the engine published since the last pass, discarding a
    // frame caught mid-write. Returns true when the local copy changed.
    bool sampleFrame ();
    void drainEdits ();
    void pushInput (std::uint32_t type, std::uint32_t buttons, std::int32_t x,
                    std::int32_t y, std::int32_t wheelVertical,
                    std::int32_t wheelHorizontal);
    void markEditorOpen (bool open);
    std::int32_t toLogical (std::int32_t windowPixels) const;
    void logicalSize (std::int32_t& width, std::int32_t& height) const;

    Controller* owner_ = nullptr;
    std::string mappingName_;
    std::uint32_t generation_ = 0U;
    mpvst::SharedMemory mapping_;
    mpvst_ui_state* state_ = nullptr;
    // The view's private copy of the framebuffer, which is what it actually
    // paints from. The shared one can change under a read at any moment.
    std::vector<std::uint8_t> frame_;
    // Union of everything that changed since the last repaint, in logical
    // pixels. Empty means nothing to draw.
    std::int32_t dirtyLeft_ = 0;
    std::int32_t dirtyTop_ = 0;
    std::int32_t dirtyRight_ = 0;
    std::int32_t dirtyBottom_ = 0;
    bool dirty_ = false;
    // Whether frame_ holds a real copy of the engine's frame. Emphatically
    // not "whether this view has ever drawn": a window is asked to paint the
    // moment it is created, long before the first timer tick, and answering
    // that with an empty buffer must not count as having a frame.
    bool haveFrame_ = false;
    double scale_ = 1.0;

#if defined(_WIN32)
    static LRESULT CALLBACK windowProc (HWND window, UINT message, WPARAM wparam,
                                        LPARAM lparam);
    LRESULT handleMessage (HWND window, UINT message, WPARAM wparam, LPARAM lparam);
    void paint (HDC device);
    HWND window_ = nullptr;
    bool capturing_ = false;
#elif defined(__linux__)
    void createWindow (void* parent);
    void destroyWindow ();
    void drainX ();
    void paint ();
    Steinberg::Linux::IRunLoop* runLoop () const;
    void* display_ = nullptr;
    unsigned long window_ = 0U;
    void* graphicsContext_ = nullptr;
    void* image_ = nullptr;
    // The XImage's own storage: 32-bit pixels converted from RGB565 on the
    // way out, because X has no 16-bit visual worth relying on.
    std::vector<std::uint32_t> converted_;
    bool timerRegistered_ = false;
    bool handlerRegistered_ = false;
#endif
};

} // namespace PyDevices::MicroPythonVST3
