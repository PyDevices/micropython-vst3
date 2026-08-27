#pragma once

// Reading a script's declarations without running it.
//
// The controller names its parameters in the host's process, where there is
// no interpreter to ask, so it reads the source as text. What it reads is the
// same `MACRO_LABELS` a plug-in declares anywhere else - there is one way to
// declare macros, and this is it seen from the outside.

#include <array>
#include <cctype>
#include <string>
#include <string_view>

namespace PyDevices::MicroPythonVST3 {

constexpr std::string_view kMacroLabelsName = "MACRO_LABELS";

inline std::string trimMacroLabel(std::string_view value)
{
    while (!value.empty() &&
           std::isspace(static_cast<unsigned char>(value.front())) != 0)
        value.remove_prefix(1U);
    while (!value.empty() &&
           std::isspace(static_cast<unsigned char>(value.back())) != 0)
        value.remove_suffix(1U);
    constexpr std::size_t kMaximumLabelBytes = 63U;
    return std::string(value.substr(0U, kMaximumLabelBytes));
}

// The module-level `MACRO_LABELS = (...)` assignment, if the script has one.
//
// Text, not Python: a tuple of literals is all the declaration is allowed to
// be, so finding the assignment and taking the quoted strings out of it gives
// the same answer an interpreter would. An indented assignment is skipped -
// that one belongs to a class, and a script's own macros are the module's.
inline bool parseMacroLabels(const std::string& source,
                             std::array<std::string, 16>& labels)
{
    std::size_t lineStart = 0U;
    while (lineStart <= source.size())
    {
        const auto lineEnd = source.find('\n', lineStart);
        const auto length = lineEnd == std::string::npos
            ? source.size() - lineStart : lineEnd - lineStart;
        const std::string_view line(source.data() + lineStart, length);

        if (line.substr(0U, kMacroLabelsName.size()) == kMacroLabelsName)
        {
            auto rest = line.substr(kMacroLabelsName.size());
            while (!rest.empty() &&
                   std::isspace(static_cast<unsigned char>(rest.front())) != 0)
                rest.remove_prefix(1U);
            if (!rest.empty() && rest.front() == '=')
            {
                // From the "=" to wherever the brackets close, so a wrapped
                // tuple is read whole rather than truncated at the newline.
                const auto valueStart = lineStart + kMacroLabelsName.size() +
                    (line.size() - kMacroLabelsName.size() - rest.size()) + 1U;
                std::size_t depth = 0U;
                std::size_t at = valueStart;
                bool opened = false;
                for (; at < source.size(); ++at)
                {
                    const auto character = source[at];
                    if (character == '(' || character == '[')
                    {
                        ++depth;
                        opened = true;
                    }
                    else if (character == ')' || character == ']')
                    {
                        if (depth != 0U)
                            --depth;
                        if (depth == 0U)
                        {
                            ++at;
                            break;
                        }
                    }
                    else if (character == '\n' && !opened)
                        break;
                }

                const std::string_view value (source.data() + valueStart,
                                              at - valueStart);
                std::size_t index = 0U;
                std::size_t scan = 0U;
                while (index < labels.size() && scan < value.size())
                {
                    const auto quote = value[scan];
                    if (quote != '"' && quote != '\'')
                    {
                        ++scan;
                        continue;
                    }
                    const auto close = value.find(quote, scan + 1U);
                    if (close == std::string_view::npos)
                        break;
                    labels[index++] = trimMacroLabel(
                        value.substr(scan + 1U, close - scan - 1U));
                    scan = close + 1U;
                }
                return index != 0U;
            }
        }

        if (lineEnd == std::string::npos)
            break;
        lineStart = lineEnd + 1U;
    }
    return false;
}

} // namespace PyDevices::MicroPythonVST3
