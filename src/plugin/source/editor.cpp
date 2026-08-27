#include "editor.h"

#include "controller.h"
#include "mpvst/atomic.h"

#include "public.sdk/source/vst/vsteditcontroller.h"

#include <algorithm>
#include <cstring>

#if defined(__linux__)
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#endif

namespace PyDevices::MicroPythonVST3 {

using namespace Steinberg;
using namespace Steinberg::Vst;

namespace {

// 30 Hz. Fast enough that a slider drag reads as continuous, slow enough that
// an idle editor is not a background load on a machine that is rendering
// audio in another process.
constexpr std::uint32_t kFrameIntervalMs = 33U;

std::int32_t scaled (std::int32_t logical, double scale)
{
    return static_cast<std::int32_t> (
        static_cast<double> (logical) * scale + 0.5);
}

} // namespace

Editor::Editor (Controller* owner, std::string mappingName,
                std::uint32_t generation)
    : CPluginView (nullptr)
    , owner_ (owner)
    , mappingName_ (std::move (mappingName))
    , generation_ (generation)
{
    // A view reports a size before it is ever attached, and it cannot ask the
    // engine for one until the mapping is open. The compiled default is the
    // same size the stock panel declares, so the common case is exact and the
    // rare one is corrected by the first checkSizeConstraint.
    rect.left = 0;
    rect.top = 0;
    rect.right = static_cast<int32> (MPVST_UI_DEFAULT_WIDTH);
    rect.bottom = static_cast<int32> (MPVST_UI_DEFAULT_HEIGHT);
    if (openMapping ())
    {
        std::int32_t width = 0;
        std::int32_t height = 0;
        logicalSize (width, height);
        rect.right = static_cast<int32> (width);
        rect.bottom = static_cast<int32> (height);
    }
}

Editor::~Editor ()
{
    if (owner_ != nullptr)
        owner_->editorClosed (this);
    closeMapping ();
}

bool Editor::openMapping ()
{
    if (state_ != nullptr)
        return true;
    if (mappingName_.empty ())
        return false;
    const auto bytes = mpvst_ui_mapping_bytes ();
    if (!mapping_.open (mappingName_, bytes) ||
        !mpvst_ui_validate (mapping_.data (), bytes))
    {
        mapping_.close ();
        return false;
    }
    state_ = static_cast<mpvst_ui_state*> (mapping_.data ());
    frame_.assign (static_cast<std::size_t> (mpvst_ui_framebuffer_bytes ()), 0U);
    dirty_ = false;
    everPainted_ = false;
    return true;
}

void Editor::closeMapping ()
{
    if (state_ != nullptr)
        markEditorOpen (false);
    state_ = nullptr;
    mapping_.close ();
    frame_.clear ();
    frame_.shrink_to_fit ();
}

void Editor::mappingChanged (const std::string& mappingName,
                             std::uint32_t generation)
{
    if (mappingName == mappingName_ && generation == generation_ &&
        state_ != nullptr)
        return;
    const bool attachedNow = isAttached ();
    closeMapping ();
    mappingName_ = mappingName;
    generation_ = generation;
    if (!openMapping ())
        return;
    if (attachedNow)
        markEditorOpen (true);
}

void Editor::markEditorOpen (bool open)
{
    if (state_ == nullptr)
        return;
    mpvst::release_store_u32 (&state_->editor_open, open ? 1U : 0U);
}

void Editor::logicalSize (std::int32_t& width, std::int32_t& height) const
{
    width = static_cast<std::int32_t> (MPVST_UI_DEFAULT_WIDTH);
    height = static_cast<std::int32_t> (MPVST_UI_DEFAULT_HEIGHT);
    if (state_ == nullptr)
        return;
    const auto declaredWidth = mpvst::acquire_load_u32 (&state_->width);
    const auto declaredHeight = mpvst::acquire_load_u32 (&state_->height);
    if (declaredWidth != 0U && declaredWidth <= MPVST_UI_MAX_WIDTH)
        width = static_cast<std::int32_t> (declaredWidth);
    if (declaredHeight != 0U && declaredHeight <= MPVST_UI_MAX_HEIGHT)
        height = static_cast<std::int32_t> (declaredHeight);
}

std::int32_t Editor::toLogical (std::int32_t windowPixels) const
{
    if (scale_ <= 0.0 || scale_ == 1.0)
        return windowPixels;
    return static_cast<std::int32_t> (
        static_cast<double> (windowPixels) / scale_ + 0.5);
}

tresult PLUGIN_API Editor::checkSizeConstraint (ViewRect* size)
{
    if (size == nullptr)
        return kResultFalse;
    std::int32_t width = 0;
    std::int32_t height = 0;
    logicalSize (width, height);
    size->left = 0;
    size->top = 0;
    size->right = scaled (width, scale_);
    size->bottom = scaled (height, scale_);
    return kResultTrue;
}

tresult PLUGIN_API Editor::onSize (ViewRect* newSize)
{
    // Not resizable in v1: report the one size that works rather than
    // accepting whatever the host proposed and then drawing wrong.
    (void)newSize;
    return checkSizeConstraint (&rect);
}

tresult PLUGIN_API Editor::setContentScaleFactor (ScaleFactor factor)
{
    if (factor <= 0.0)
        return kResultFalse;
    scale_ = static_cast<double> (factor);
    if (state_ != nullptr)
        mpvst::release_store_u32 (
            &state_->content_scale_ppm,
            static_cast<std::uint32_t> (scale_ * MPVST_UI_SCALE_UNITY + 0.5));
    std::int32_t width = 0;
    std::int32_t height = 0;
    logicalSize (width, height);
    rect.right = static_cast<int32> (scaled (width, scale_));
    rect.bottom = static_cast<int32> (scaled (height, scale_));
    return kResultTrue;
}

tresult PLUGIN_API Editor::onWheel (float distance)
{
    // The host's own wheel forwarding, which some frames use instead of
    // letting the child window see the message. One unit is one notch.
    if (state_ == nullptr || distance == 0.0F)
        return kResultFalse;
    pushInput (MPVST_UI_INPUT_WHEEL, 0U, 0, 0,
               static_cast<std::int32_t> (distance * MPVST_UI_WHEEL_NOTCH), 0);
    return kResultTrue;
}

//------------------------------------------------------------------------
// Shared-memory traffic
//------------------------------------------------------------------------

bool Editor::sampleFrame ()
{
    if (state_ == nullptr)
        return false;

    const auto sequence = mpvst::acquire_load_u64 (&state_->frame_sequence);
    if (sequence % 2U != 0U)
        return false; // caught mid-write; try again on the next tick

    auto tail = mpvst::acquire_load_u64 (&state_->rect_tail);
    const auto head = mpvst::acquire_load_u64 (&state_->rect_head);
    if (head == tail)
        return false;
    // A view that fell behind a busy engine has lost the oldest rectangles.
    // Take the newest capacity-worth and let the union cover the rest.
    bool lost = false;
    if (head - tail > MPVST_UI_RECT_CAPACITY)
    {
        tail = head - MPVST_UI_RECT_CAPACITY;
        lost = true;
    }

    const auto* rects = mpvst_ui_rects (mapping_.data ());
    const auto* pixels = mpvst_ui_framebuffer (mapping_.data ());
    const auto stride = mpvst_ui_stride_bytes ();
    std::int32_t width = 0;
    std::int32_t height = 0;
    logicalSize (width, height);

    std::int32_t left = width;
    std::int32_t top = height;
    std::int32_t right = 0;
    std::int32_t bottom = 0;
    for (auto position = tail; position != head; ++position)
    {
        const auto& source = rects[position % MPVST_UI_RECT_CAPACITY];
        const std::int32_t x = source.x;
        const std::int32_t y = source.y;
        const std::int32_t w = source.width;
        const std::int32_t h = source.height;
        if (w <= 0 || h <= 0 || x < 0 || y < 0 || x + w > width || y + h > height)
            continue;
        const auto rowBytes = static_cast<std::size_t> (w) * MPVST_UI_PIXEL_BYTES;
        for (std::int32_t row = 0; row < h; ++row)
        {
            const auto offset = static_cast<std::size_t> (y + row) * stride +
                                static_cast<std::size_t> (x) * MPVST_UI_PIXEL_BYTES;
            std::memcpy (frame_.data () + offset, pixels + offset, rowBytes);
        }
        left = std::min (left, x);
        top = std::min (top, y);
        right = std::max (right, x + w);
        bottom = std::max (bottom, y + h);
    }

    // The seqlock's whole purpose: if the engine published anything while the
    // copy was in flight, throw the copy away without moving the cursor. The
    // same rectangles come round again next tick, and a discarded frame costs
    // one repaint rather than a torn one.
    if (mpvst::acquire_load_u64 (&state_->frame_sequence) != sequence)
        return false;
    mpvst::release_store_u64 (&state_->rect_tail, head);
    if (right <= left || bottom <= top)
        return false;

    if (lost || !everPainted_)
    {
        left = 0;
        top = 0;
        right = width;
        bottom = height;
    }
    if (dirty_)
    {
        dirtyLeft_ = std::min (dirtyLeft_, left);
        dirtyTop_ = std::min (dirtyTop_, top);
        dirtyRight_ = std::max (dirtyRight_, right);
        dirtyBottom_ = std::max (dirtyBottom_, bottom);
    }
    else
    {
        dirtyLeft_ = left;
        dirtyTop_ = top;
        dirtyRight_ = right;
        dirtyBottom_ = bottom;
        dirty_ = true;
    }
    return true;
}

void Editor::drainEdits ()
{
    if (state_ == nullptr || owner_ == nullptr)
        return;
    auto tail = mpvst::acquire_load_u64 (&state_->edit_tail);
    const auto head = mpvst::acquire_load_u64 (&state_->edit_head);
    if (head == tail)
        return;
    if (head - tail > MPVST_UI_EDIT_CAPACITY)
        tail = head - MPVST_UI_EDIT_CAPACITY;

    const auto* edits = mpvst_ui_edits (mapping_.data ());
    for (auto position = tail; position != head; ++position)
    {
        const auto& record = edits[position % MPVST_UI_EDIT_CAPACITY];
        const auto id = static_cast<ParamID> (record.parameter_id);
        const auto value = static_cast<ParamValue> (
            std::clamp (record.value, 0.0F, 1.0F));
        switch (record.kind)
        {
            case MPVST_UI_EDIT_BEGIN:
                (void)owner_->beginEdit (id);
                break;
            case MPVST_UI_EDIT_PERFORM:
                // Both calls are needed and they are not the same thing:
                // performEdit tells the host to record and forward the change,
                // setParamNormalized keeps the controller's own copy in step
                // so its generic UI and getParamNormalized agree with the
                // panel.
                (void)owner_->setParamNormalized (id, value);
                (void)owner_->performEdit (id, value);
                break;
            case MPVST_UI_EDIT_END:
                (void)owner_->endEdit (id);
                break;
            default:
                break;
        }
    }
    mpvst::release_store_u64 (&state_->edit_tail, head);
}

void Editor::pushInput (std::uint32_t type, std::uint32_t buttons,
                        std::int32_t x, std::int32_t y,
                        std::int32_t wheelVertical, std::int32_t wheelHorizontal)
{
    if (state_ == nullptr)
        return;
    auto* inputs = mpvst_ui_inputs (mapping_.data ());
    auto head = mpvst::acquire_load_u64 (&state_->input_head);
    const auto tail = mpvst::acquire_load_u64 (&state_->input_tail);

    // Coalesce rather than flood. Only the latest pointer position matters,
    // but every wheel delta counts toward the total, so one is replaced and
    // the other is summed.
    if (head != tail)
    {
        auto& last = inputs[(head - 1U) % MPVST_UI_INPUT_CAPACITY];
        if (type == MPVST_UI_INPUT_POINTER_MOVE &&
            last.type == MPVST_UI_INPUT_POINTER_MOVE && last.buttons == buttons)
        {
            last.x = x;
            last.y = y;
            return;
        }
        if (type == MPVST_UI_INPUT_WHEEL && last.type == MPVST_UI_INPUT_WHEEL)
        {
            last.wheel_vertical += wheelVertical;
            last.wheel_horizontal += wheelHorizontal;
            return;
        }
    }

    if (head - tail >= MPVST_UI_INPUT_CAPACITY)
    {
        // The engine is not draining - a stalled or very busy sidecar. Drop
        // the oldest and keep going; waiting here would block the UI thread on
        // a process that may never answer.
        mpvst::release_store_u64 (&state_->input_tail,
                                  head - MPVST_UI_INPUT_CAPACITY + 1U);
    }
    auto& record = inputs[head % MPVST_UI_INPUT_CAPACITY];
    record.type = type;
    record.buttons = buttons;
    record.x = x;
    record.y = y;
    record.wheel_vertical = wheelVertical;
    record.wheel_horizontal = wheelHorizontal;
    record.sequence = head + 1U;
    mpvst::release_store_u64 (&state_->input_head, head + 1U);
}

void Editor::tick ()
{
    if (state_ == nullptr)
        return;
    // Re-assert on every pass rather than only on attach: a sidecar restart
    // reinitialises the region, which clears the flag, and the engine would
    // otherwise stop painting for a view that is still on screen.
    markEditorOpen (true);
    drainEdits ();
    if (!sampleFrame ())
        return;
#if defined(_WIN32)
    if (window_ != nullptr)
    {
        RECT area;
        area.left = scaled (dirtyLeft_, scale_);
        area.top = scaled (dirtyTop_, scale_);
        area.right = scaled (dirtyRight_, scale_);
        area.bottom = scaled (dirtyBottom_, scale_);
        InvalidateRect (window_, &area, FALSE);
    }
#elif defined(__linux__)
    paint ();
#endif
}

//------------------------------------------------------------------------
#if defined(_WIN32)
//------------------------------------------------------------------------

namespace {

const wchar_t* const kWindowClass = L"PyDevicesMicroPythonVST3Editor";
UINT_PTR const kFrameTimer = 1;

// windowsx.h's GET_X_LPARAM by hand: the cast through short is the part that
// matters, since a coordinate can legitimately be negative once the mouse is
// captured and leaves the window.
int lparamX (LPARAM value)
{
    return static_cast<int> (static_cast<short> (LOWORD (value)));
}

int lparamY (LPARAM value)
{
    return static_cast<int> (static_cast<short> (HIWORD (value)));
}

HINSTANCE moduleHandle ()
{
    HMODULE module = nullptr;
    GetModuleHandleExW (GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                            GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                        reinterpret_cast<LPCWSTR> (&moduleHandle), &module);
    return module;
}

} // namespace

LRESULT CALLBACK Editor::windowProc (HWND window, UINT message, WPARAM wparam,
                                     LPARAM lparam)
{
    auto* editor = reinterpret_cast<Editor*> (
        GetWindowLongPtrW (window, GWLP_USERDATA));
    if (editor == nullptr)
        return DefWindowProcW (window, message, wparam, lparam);
    return editor->handleMessage (window, message, wparam, lparam);
}

LRESULT Editor::handleMessage (HWND window, UINT message, WPARAM wparam,
                               LPARAM lparam)
{
    switch (message)
    {
        case WM_TIMER:
            if (wparam == kFrameTimer)
            {
                tick ();
                return 0;
            }
            break;
        case WM_ERASEBKGND:
            // Every pixel is painted from the framebuffer, so erasing first
            // only buys a flash of the background colour.
            return 1;
        case WM_PAINT:
        {
            PAINTSTRUCT paintStruct;
            HDC device = BeginPaint (window, &paintStruct);
            paint (device);
            EndPaint (window, &paintStruct);
            return 0;
        }
        case WM_MOUSEMOVE:
            pushInput (MPVST_UI_INPUT_POINTER_MOVE,
                       (wparam & MK_LBUTTON) != 0U ? 1U : 0U,
                       toLogical (lparamX (lparam)),
                       toLogical (lparamY (lparam)), 0, 0);
            return 0;
        case WM_LBUTTONDOWN:
            // Wheel messages go to the focused window, and a child that has
            // never been clicked has no focus - so without this the wheel
            // reaches the editor only on hosts that forward it through
            // IPlugView::onWheel.
            SetFocus (window);
            SetCapture (window);
            capturing_ = true;
            pushInput (MPVST_UI_INPUT_POINTER_DOWN, 1U,
                       toLogical (lparamX (lparam)),
                       toLogical (lparamY (lparam)), 0, 0);
            return 0;
        case WM_LBUTTONUP:
            if (capturing_)
            {
                ReleaseCapture ();
                capturing_ = false;
            }
            pushInput (MPVST_UI_INPUT_POINTER_UP, 0U,
                       toLogical (lparamX (lparam)),
                       toLogical (lparamY (lparam)), 0, 0);
            return 0;
        case WM_CAPTURECHANGED:
            capturing_ = false;
            return 0;
        case WM_MOUSEWHEEL:
            // Already a signed multiple of WHEEL_DELTA, which is exactly the
            // unit mpvst_ui_input carries. The legacy-versus-precise ambiguity
            // that dogs SDL simply does not exist here.
            pushInput (MPVST_UI_INPUT_WHEEL, 0U, 0, 0,
                       GET_WHEEL_DELTA_WPARAM (wparam), 0);
            return 0;
        case WM_MOUSEHWHEEL:
            pushInput (MPVST_UI_INPUT_WHEEL, 0U, 0, 0, 0,
                       GET_WHEEL_DELTA_WPARAM (wparam));
            return 0;
        default:
            break;
    }
    return DefWindowProcW (window, message, wparam, lparam);
}

void Editor::paint (HDC device)
{
    if (state_ == nullptr || frame_.empty ())
        return;
    std::int32_t width = 0;
    std::int32_t height = 0;
    logicalSize (width, height);

    // A panel that died is reported here, in the view's own drawing, because
    // the engine cannot be trusted to paint anything once its panel is gone.
    // A broken editor has to look broken rather than frozen.
    if (mpvst::acquire_load_u32 (&state_->ui_error) != 0U)
    {
        RECT area {0, 0, scaled (width, scale_), scaled (height, scale_)};
        FillRect (device, &area,
                  static_cast<HBRUSH> (GetStockObject (BLACK_BRUSH)));
        SetBkMode (device, TRANSPARENT);
        SetTextColor (device, RGB (0xF8, 0x51, 0x49));
        DrawTextW (device, L"Editor unavailable - the panel raised an error.",
                   -1, &area, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
        everPainted_ = false;
        dirty_ = false;
        return;
    }

    // RGB565 straight to the screen: a 16-bit BI_BITFIELDS DIB is blitted
    // without a conversion pass, which is the same technique WinDisplay uses
    // for exactly the same reason.
    struct
    {
        BITMAPINFOHEADER header;
        DWORD masks[3];
    } info {};
    info.header.biSize = sizeof (BITMAPINFOHEADER);
    info.header.biWidth = static_cast<LONG> (MPVST_UI_MAX_WIDTH);
    // Negative height means top-down, which is how the framebuffer is laid out.
    info.header.biHeight = -static_cast<LONG> (MPVST_UI_MAX_HEIGHT);
    info.header.biPlanes = 1;
    info.header.biBitCount = 16;
    info.header.biCompression = BI_BITFIELDS;
    info.masks[0] = 0xF800U;
    info.masks[1] = 0x07E0U;
    info.masks[2] = 0x001FU;

    const auto destinationWidth = scaled (width, scale_);
    const auto destinationHeight = scaled (height, scale_);
    SetStretchBltMode (device, HALFTONE);
    StretchDIBits (device, 0, 0, destinationWidth, destinationHeight, 0, 0,
                   width, height, frame_.data (),
                   reinterpret_cast<const BITMAPINFO*> (&info), DIB_RGB_COLORS,
                   SRCCOPY);
    everPainted_ = true;
    dirty_ = false;
}

tresult PLUGIN_API Editor::isPlatformTypeSupported (FIDString type)
{
    return (type != nullptr && std::strcmp (type, kPlatformTypeHWND) == 0)
        ? kResultTrue : kResultFalse;
}

tresult PLUGIN_API Editor::attached (void* parent, FIDString type)
{
    if (isPlatformTypeSupported (type) != kResultTrue || parent == nullptr)
        return kResultFalse;
    if (!openMapping ())
        return kResultFalse;

    static bool registered = false;
    if (!registered)
    {
        WNDCLASSEXW description {};
        description.cbSize = sizeof (description);
        description.style = CS_HREDRAW | CS_VREDRAW;
        description.lpfnWndProc = &Editor::windowProc;
        description.hInstance = moduleHandle ();
        description.hCursor = LoadCursorW (nullptr, IDC_ARROW);
        description.lpszClassName = kWindowClass;
        if (RegisterClassExW (&description) == 0 &&
            GetLastError () != ERROR_CLASS_ALREADY_EXISTS)
            return kResultFalse;
        registered = true;
    }

    std::int32_t width = 0;
    std::int32_t height = 0;
    logicalSize (width, height);
    window_ = CreateWindowExW (0, kWindowClass, L"", WS_CHILD | WS_VISIBLE, 0, 0,
                               scaled (width, scale_), scaled (height, scale_),
                               static_cast<HWND> (parent), nullptr,
                               moduleHandle (), nullptr);
    if (window_ == nullptr)
        return kResultFalse;
    SetWindowLongPtrW (window_, GWLP_USERDATA, reinterpret_cast<LONG_PTR> (this));
    SetTimer (window_, kFrameTimer, kFrameIntervalMs, nullptr);
    everPainted_ = false;
    markEditorOpen (true);
    return CPluginView::attached (parent, type);
}

tresult PLUGIN_API Editor::removed ()
{
    markEditorOpen (false);
    if (window_ != nullptr)
    {
        KillTimer (window_, kFrameTimer);
        SetWindowLongPtrW (window_, GWLP_USERDATA, 0);
        DestroyWindow (window_);
        window_ = nullptr;
    }
    capturing_ = false;
    return CPluginView::removed ();
}

//------------------------------------------------------------------------
#elif defined(__linux__)
//------------------------------------------------------------------------

Steinberg::Linux::IRunLoop* Editor::runLoop () const
{
    if (plugFrame == nullptr)
        return nullptr;
    Steinberg::Linux::IRunLoop* loop = nullptr;
    if (plugFrame->queryInterface (Steinberg::Linux::IRunLoop::iid,
                                   reinterpret_cast<void**> (&loop)) != kResultOk)
        return nullptr;
    // queryInterface hands back a reference the caller owns. The frame
    // outlives this view, so releasing here and using the raw pointer is
    // safe and keeps the refcount honest.
    loop->release ();
    return loop;
}

void Editor::createWindow (void* parent)
{
    // A connection of the view's own, rather than the host's: X11 is happy to
    // reparent across connections to the same server, and owning the
    // connection is what makes the file descriptor the run loop watches ours
    // to drain.
    auto* display = XOpenDisplay (nullptr);
    if (display == nullptr)
        return;

    // The conversion below writes 32-bit pixels, which ZPixmap stores one per
    // four bytes at depth 24 or 32 and not at any other depth. Rather than
    // paint garbage on an exotic visual, refuse the window: the host falls
    // back to its generic parameter editor, which reaches everything.
    const auto screen = DefaultScreen (display);
    const auto depth = DefaultDepth (display, screen);
    if (depth != 24 && depth != 32)
    {
        XCloseDisplay (display);
        return;
    }
    display_ = display;

    std::int32_t width = 0;
    std::int32_t height = 0;
    logicalSize (width, height);
    const auto parentWindow = static_cast<Window> (
        reinterpret_cast<std::uintptr_t> (parent));
    window_ = XCreateSimpleWindow (
        display, parentWindow, 0, 0,
        static_cast<unsigned> (scaled (width, scale_)),
        static_cast<unsigned> (scaled (height, scale_)), 0,
        BlackPixel (display, screen), BlackPixel (display, screen));
    XSelectInput (display, window_,
                  ExposureMask | ButtonPressMask | ButtonReleaseMask |
                      PointerMotionMask | StructureNotifyMask);
    XMapWindow (display, window_);
    XFlush (display);

    graphicsContext_ = XCreateGC (display, window_, 0, nullptr);
    converted_.assign (static_cast<std::size_t> (MPVST_UI_MAX_WIDTH) *
                           MPVST_UI_MAX_HEIGHT,
                       0U);
    image_ = XCreateImage (
        display, DefaultVisual (display, screen),
        static_cast<unsigned> (depth), ZPixmap, 0,
        reinterpret_cast<char*> (converted_.data ()), MPVST_UI_MAX_WIDTH,
        MPVST_UI_MAX_HEIGHT, 32, 0);
}

void Editor::destroyWindow ()
{
    auto* display = static_cast<Display*> (display_);
    if (display == nullptr)
        return;
    if (image_ != nullptr)
    {
        // The pixel storage belongs to converted_, so hand XDestroyImage a
        // null pointer rather than letting it free a std::vector's buffer.
        auto* image = static_cast<XImage*> (image_);
        image->data = nullptr;
        XDestroyImage (image);
        image_ = nullptr;
    }
    if (graphicsContext_ != nullptr)
    {
        XFreeGC (display, static_cast<GC> (graphicsContext_));
        graphicsContext_ = nullptr;
    }
    if (window_ != 0U)
    {
        XDestroyWindow (display, window_);
        window_ = 0U;
    }
    XCloseDisplay (display);
    display_ = nullptr;
    converted_.clear ();
    converted_.shrink_to_fit ();
}

void Editor::paint ()
{
    auto* display = static_cast<Display*> (display_);
    if (display == nullptr || image_ == nullptr || !dirty_ || frame_.empty ())
        return;
    std::int32_t width = 0;
    std::int32_t height = 0;
    logicalSize (width, height);

    // See the Windows path: a dead panel is reported by the view, not by the
    // engine that lost it.
    if (mpvst::acquire_load_u32 (&state_->ui_error) != 0U)
    {
        static const char message[] =
            "Editor unavailable - the panel raised an error.";
        XClearWindow (display, window_);
        XDrawString (display, window_, static_cast<GC> (graphicsContext_),
                     16, scaled (height, scale_) / 2, message,
                     static_cast<int> (sizeof (message) - 1U));
        XFlush (display);
        everPainted_ = false;
        dirty_ = false;
        return;
    }

    const auto left = std::max (0, dirtyLeft_);
    const auto top = std::max (0, dirtyTop_);
    const auto right = std::min (width, dirtyRight_);
    const auto bottom = std::min (height, dirtyBottom_);
    if (right <= left || bottom <= top)
    {
        dirty_ = false;
        return;
    }

    const auto stride = mpvst_ui_stride_bytes ();
    for (std::int32_t y = top; y < bottom; ++y)
    {
        const auto* row = reinterpret_cast<const std::uint16_t*> (
            frame_.data () + static_cast<std::size_t> (y) * stride);
        auto* out = converted_.data () +
                    static_cast<std::size_t> (y) * MPVST_UI_MAX_WIDTH;
        for (std::int32_t x = left; x < right; ++x)
        {
            const auto pixel = row[x];
            // Widen each channel by replicating its top bits, so full-scale
            // stays full-scale instead of landing a few counts short.
            const std::uint32_t red = ((pixel >> 11) & 0x1FU) * 255U / 31U;
            const std::uint32_t green = ((pixel >> 5) & 0x3FU) * 255U / 63U;
            const std::uint32_t blue = (pixel & 0x1FU) * 255U / 31U;
            out[x] = (red << 16) | (green << 8) | blue;
        }
    }
    XPutImage (display, window_, static_cast<GC> (graphicsContext_),
               static_cast<XImage*> (image_), left, top, left, top,
               static_cast<unsigned> (right - left),
               static_cast<unsigned> (bottom - top));
    XFlush (display);
    everPainted_ = true;
    dirty_ = false;
}

void Editor::drainX ()
{
    auto* display = static_cast<Display*> (display_);
    if (display == nullptr)
        return;
    XEvent event;
    while (XPending (display) > 0)
    {
        XNextEvent (display, &event);
        switch (event.type)
        {
            case Expose:
                dirtyLeft_ = 0;
                dirtyTop_ = 0;
                logicalSize (dirtyRight_, dirtyBottom_);
                dirty_ = true;
                paint ();
                break;
            case MotionNotify:
                pushInput (MPVST_UI_INPUT_POINTER_MOVE,
                           (event.xmotion.state & Button1Mask) != 0U ? 1U : 0U,
                           toLogical (event.xmotion.x),
                           toLogical (event.xmotion.y), 0, 0);
                break;
            case ButtonPress:
                // X11 delivers wheel notches as presses of buttons 4-7. There
                // is no legacy-versus-smooth ambiguity to resolve here because
                // this path never asks for XInput2 valuators; one press is one
                // notch, which is the unit the protocol carries.
                if (event.xbutton.button == 4 || event.xbutton.button == 5)
                    pushInput (MPVST_UI_INPUT_WHEEL, 0U, 0, 0,
                               event.xbutton.button == 4 ? MPVST_UI_WHEEL_NOTCH
                                                         : -MPVST_UI_WHEEL_NOTCH,
                               0);
                else if (event.xbutton.button == 6 || event.xbutton.button == 7)
                    pushInput (MPVST_UI_INPUT_WHEEL, 0U, 0, 0, 0,
                               event.xbutton.button == 7 ? MPVST_UI_WHEEL_NOTCH
                                                         : -MPVST_UI_WHEEL_NOTCH);
                else if (event.xbutton.button == Button1)
                    pushInput (MPVST_UI_INPUT_POINTER_DOWN, 1U,
                               toLogical (event.xbutton.x),
                               toLogical (event.xbutton.y), 0, 0);
                break;
            case ButtonRelease:
                if (event.xbutton.button == Button1)
                    pushInput (MPVST_UI_INPUT_POINTER_UP, 0U,
                               toLogical (event.xbutton.x),
                               toLogical (event.xbutton.y), 0, 0);
                break;
            default:
                break;
        }
    }
}

void PLUGIN_API Editor::onFDIsSet (Steinberg::Linux::FileDescriptor)
{
    drainX ();
}

void PLUGIN_API Editor::onTimer ()
{
    drainX ();
    tick ();
}

tresult PLUGIN_API Editor::isPlatformTypeSupported (FIDString type)
{
    return (type != nullptr && std::strcmp (type, kPlatformTypeX11EmbedWindowID) == 0)
        ? kResultTrue : kResultFalse;
}

tresult PLUGIN_API Editor::attached (void* parent, FIDString type)
{
    if (isPlatformTypeSupported (type) != kResultTrue || parent == nullptr)
        return kResultFalse;
    if (!openMapping ())
        return kResultFalse;
    createWindow (parent);
    if (display_ == nullptr)
        return kResultFalse;

    // The host owns the event loop on Linux; a plug-in that spins its own
    // would be fighting it. Both the X connection and the frame timer are
    // registered with the host's run loop instead.
    if (auto* loop = runLoop ())
    {
        auto* display = static_cast<Display*> (display_);
        handlerRegistered_ =
            loop->registerEventHandler (this, ConnectionNumber (display)) == kResultOk;
        timerRegistered_ =
            loop->registerTimer (this, kFrameIntervalMs) == kResultOk;
    }
    everPainted_ = false;
    markEditorOpen (true);
    return CPluginView::attached (parent, type);
}

tresult PLUGIN_API Editor::removed ()
{
    markEditorOpen (false);
    if (auto* loop = runLoop ())
    {
        if (timerRegistered_)
            (void)loop->unregisterTimer (this);
        if (handlerRegistered_)
            (void)loop->unregisterEventHandler (this);
    }
    timerRegistered_ = false;
    handlerRegistered_ = false;
    destroyWindow ();
    return CPluginView::removed ();
}

//------------------------------------------------------------------------
#else
//------------------------------------------------------------------------

tresult PLUGIN_API Editor::isPlatformTypeSupported (FIDString)
{
    return kResultFalse;
}

tresult PLUGIN_API Editor::attached (void*, FIDString)
{
    return kResultFalse;
}

tresult PLUGIN_API Editor::removed ()
{
    return CPluginView::removed ();
}

#endif

} // namespace PyDevices::MicroPythonVST3
