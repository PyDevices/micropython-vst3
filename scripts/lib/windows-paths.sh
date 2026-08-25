# Resolve Windows "known folders" as WSL paths. Source, don't execute.
#
# Do not assemble these by hand from a username: a profile need not live
# under C:\Users at all, and Group Policy folder redirection routinely
# moves Roaming AppData (and Documents/Music) onto a network share. Ask
# Windows for the real location instead.
#
# mpvst_load_windows_paths sets, as WSL paths:
#   WIN_USERPROFILE  WIN_LOCALAPPDATA  WIN_APPDATA  WIN_TEMP  WIN_MUSIC
# and returns non-zero if there is no reachable Windows host, or if a
# folder resolves somewhere WSL cannot reach (a UNC share, typically).

mpvst_load_windows_paths() {
    command -v powershell.exe >/dev/null 2>&1 || {
        echo "error: no Windows host reachable (powershell.exe not found)" >&2
        return 1
    }

    local raw
    raw=$(powershell.exe -NoProfile -Command '
        [Environment]::GetFolderPath("UserProfile")
        [Environment]::GetFolderPath("LocalApplicationData")
        [Environment]::GetFolderPath("ApplicationData")
        [System.IO.Path]::GetTempPath()
        [Environment]::GetFolderPath("MyMusic")
    ' 2>/dev/null | tr -d '\r') || {
        echo "error: could not query Windows known folders" >&2
        return 1
    }

    local names=(WIN_USERPROFILE WIN_LOCALAPPDATA WIN_APPDATA WIN_TEMP WIN_MUSIC)
    local index=0 line converted
    while IFS= read -r line; do
        [[ -n "$line" ]] || continue
        [[ $index -lt ${#names[@]} ]] || break
        line="${line%\\}"           # GetTempPath() has a trailing backslash
        if ! converted=$(wslpath -u "$line" 2>/dev/null) || [[ -z "$converted" ]]; then
            echo "error: ${names[$index]} resolves to '$line', which WSL cannot reach." >&2
            echo "  Set the matching override env var explicitly (see the script header)." >&2
            return 1
        fi
        printf -v "${names[$index]}" '%s' "$converted"
        index=$((index + 1))
    done <<< "$raw"

    [[ $index -eq ${#names[@]} ]] || {
        echo "error: Windows returned ${index} of ${#names[@]} expected folder paths" >&2
        return 1
    }
    return 0
}
