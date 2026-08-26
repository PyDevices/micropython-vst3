#pragma once

#include <array>
#include <cctype>
#include <string>
#include <string_view>

namespace PyDevices::MicroPythonVST3 {

constexpr std::string_view kMacroLabelPrefix = "# mpvst-macro-labels:";

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
        if (line.substr(0U, kMacroLabelPrefix.size()) == kMacroLabelPrefix)
        {
            auto values = line.substr(kMacroLabelPrefix.size());
            for (std::size_t index = 0U; index < labels.size(); ++index)
            {
                const auto separator = values.find('|');
                labels[index] = trimMacroLabel(values.substr(0U, separator));
                if (separator == std::string_view::npos)
                    break;
                values.remove_prefix(separator + 1U);
            }
            return true;
        }
        if (lineEnd == std::string::npos)
            break;
        lineStart = lineEnd + 1U;
    }
    return false;
}

} // namespace PyDevices::MicroPythonVST3
