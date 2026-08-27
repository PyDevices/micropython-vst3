// The geometry of the editor's Windows present path, checked against GDI
// itself rather than against a reading of the documentation.
//
// This exists because the editor shipped with a blit that silently took the
// wrong rows. The framebuffer is 1024x600 and a panel declares a logical size
// inside it - 800x480 for the stock one - so the DIB handed to StretchDIBits
// describes a buffer taller than the rectangle being blitted. In HALFTONE
// stretch mode GDI reads ySrc as an offset from the bottom of the bitmap even
// when biHeight is negative (top-down), so it returned rows 120..599 instead
// of 0..479: the panel's header fell off the top, unwritten black filled the
// bottom, and every click was hit-tested 120 rows away from the pixel it hit.
//
// Nothing else in the suite could see it. The engine's framebuffer was
// correct on both platforms, the protocol was correct, and the render parity
// checks compare audio. Only a real blit answers this, so this does one.
//
// Windows only - it is a test about a Win32 API, and the Linux view is a
// different path entirely (XPutImage, which takes no source rectangle).

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>

#include "mpvst/ui.h"

#include <cstdint>
#include <iostream>
#include <vector>

namespace {

int failures = 0;

void check(bool condition, const char* message)
{
    if (!condition)
    {
        std::cerr << "FAIL: " << message << '\n';
        ++failures;
    }
}

// Every pixel of a row carries that row's index as its RGB565 value, so a
// destination pixel can name the source row it came from.
std::vector<std::uint16_t> rowIndexedSource()
{
    std::vector<std::uint16_t> pixels(
        static_cast<std::size_t>(MPVST_UI_MAX_WIDTH) * MPVST_UI_MAX_HEIGHT);
    for (std::uint32_t y = 0; y < MPVST_UI_MAX_HEIGHT; ++y)
        for (std::uint32_t x = 0; x < MPVST_UI_MAX_WIDTH; ++x)
            pixels[static_cast<std::size_t>(y) * MPVST_UI_MAX_WIDTH + x] =
                static_cast<std::uint16_t>(y);
    return pixels;
}

std::uint32_t decodeRow(std::uint32_t bgra)
{
    const auto red = (bgra >> 16) & 0xFFU;
    const auto green = (bgra >> 8) & 0xFFU;
    const auto blue = bgra & 0xFFU;
    return ((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3);
}

struct BlitResult
{
    std::uint32_t topRow = 0;
    std::uint32_t bottomRow = 0;
};

// Mirrors Editor::paint: a top-down BI_BITFIELDS RGB565 DIB whose width is
// the whole framebuffer (that is what carries the stride), blitted one to one
// into a destination the size of the logical frame.
BlitResult blit(const std::vector<std::uint16_t>& source, LONG declaredHeight,
                int stretchMode, std::uint32_t width, std::uint32_t height)
{
    struct
    {
        BITMAPINFOHEADER header;
        DWORD masks[3];
    } info {};
    info.header.biSize = sizeof(BITMAPINFOHEADER);
    info.header.biWidth = static_cast<LONG>(MPVST_UI_MAX_WIDTH);
    info.header.biHeight = -declaredHeight;
    info.header.biPlanes = 1;
    info.header.biBitCount = 16;
    info.header.biCompression = BI_BITFIELDS;
    info.masks[0] = 0xF800U;
    info.masks[1] = 0x07E0U;
    info.masks[2] = 0x001FU;

    BITMAPINFO destination {};
    destination.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    destination.bmiHeader.biWidth = static_cast<LONG>(width);
    destination.bmiHeader.biHeight = -static_cast<LONG>(height);
    destination.bmiHeader.biPlanes = 1;
    destination.bmiHeader.biBitCount = 32;
    destination.bmiHeader.biCompression = BI_RGB;

    void* bits = nullptr;
    HDC device = CreateCompatibleDC(nullptr);
    HBITMAP bitmap = CreateDIBSection(device, &destination, DIB_RGB_COLORS,
                                      &bits, nullptr, 0);
    HGDIOBJ previous = SelectObject(device, bitmap);

    SetStretchBltMode(device, stretchMode);
    if (stretchMode == HALFTONE)
        SetBrushOrgEx(device, 0, 0, nullptr);
    StretchDIBits(device, 0, 0, static_cast<int>(width),
                  static_cast<int>(height), 0, 0, static_cast<int>(width),
                  static_cast<int>(height), source.data(),
                  reinterpret_cast<const BITMAPINFO*>(&info), DIB_RGB_COLORS,
                  SRCCOPY);
    GdiFlush();

    const auto* pixels = static_cast<const std::uint32_t*>(bits);
    BlitResult result;
    result.topRow = decodeRow(pixels[0]);
    result.bottomRow =
        decodeRow(pixels[static_cast<std::size_t>(height - 1U) * width]);

    SelectObject(device, previous);
    DeleteObject(bitmap);
    DeleteDC(device);
    return result;
}

void testLogicalFrameStartsAtRowZero()
{
    const auto source = rowIndexedSource();
    const auto width = MPVST_UI_DEFAULT_WIDTH;
    const auto height = MPVST_UI_DEFAULT_HEIGHT;
    static_assert(MPVST_UI_DEFAULT_HEIGHT < MPVST_UI_MAX_HEIGHT,
                  "the whole point is a logical frame shorter than the buffer");

    // Both stretch modes, because the editor picks between them by whether it
    // is scaling, and a mode that only works in one of them is a trap.
    for (const auto mode : {COLORONCOLOR, HALFTONE})
    {
        const auto result =
            blit(source, static_cast<LONG>(height), mode, width, height);
        check(result.topRow == 0U,
              mode == HALFTONE
                  ? "HALFTONE: the top of the frame is source row 0"
                  : "COLORONCOLOR: the top of the frame is source row 0");
        check(result.bottomRow == height - 1U,
              mode == HALFTONE
                  ? "HALFTONE: the bottom of the frame is the last logical row"
                  : "COLORONCOLOR: the bottom of the frame is the last logical row");
    }
}

void testTallDibIsTheTrapItLooksLike()
{
    // Pins the reason the DIB is declared at the logical height rather than
    // the buffer height. If a future GDI stops doing this the test says so
    // out loud instead of quietly passing, because the fix would then look
    // unmotivated to whoever reads it next.
    const auto source = rowIndexedSource();
    const auto result = blit(source, static_cast<LONG>(MPVST_UI_MAX_HEIGHT),
                             HALFTONE, MPVST_UI_DEFAULT_WIDTH,
                             MPVST_UI_DEFAULT_HEIGHT);
    const auto expectedSkew = MPVST_UI_MAX_HEIGHT - MPVST_UI_DEFAULT_HEIGHT;
    if (result.topRow == 0U)
    {
        std::cout << "  note: a buffer-tall DIB no longer skews under "
                     "HALFTONE on this Windows; the editor does not rely on "
                     "that\n";
        return;
    }
    check(result.topRow == expectedSkew,
          "a buffer-tall DIB skews by exactly the unused rows, as diagnosed");
}

} // namespace

int main()
{
    testLogicalFrameStartsAtRowZero();
    testTallDibIsTheTrapItLooksLike();
    if (failures != 0)
        return 1;
    std::cout << "mpvst GDI blit geometry tests passed\n";
    return 0;
}
