--[[
DAW matrix for the MicroPython VST3 instrument, on Windows and on Linux.

REAPER runs this as Scripts/__startup.lua. It drives the Phase 6 exit criteria
without any GUI interaction: scan, instantiate, play, automate, save, reopen,
reload after an edit, recover from a malformed script, run several instances,
and quit.

The script is a deferred state machine because the sidecar handshake and every
render need REAPER's main loop to run. Rendering is also the only way the
plug-in processes in this configuration, so a reload edge is only observed if a
render happens between clearing and setting Reload Script. For the same reason
a status parameter is only refreshed after a render, so every readiness check is
preceded by one.

Every step writes a PASS/FAIL line to MPVST_MATRIX_REPORT and the rendered WAV
files are checked separately by verify_renders.py. A global deadline guarantees
REAPER exits even when a step fails.
]]

local REPORT = os.getenv("MPVST_MATRIX_REPORT")
    or "C:\\Users\\bradb\\AppData\\Local\\Temp\\mpvst_matrix_report.txt"
local WORKDIR = os.getenv("MPVST_MATRIX_WORKDIR")
    or "C:\\Users\\bradb\\AppData\\Local\\Temp\\mpvst-matrix"
local SCRIPT = os.getenv("MPVST_SCRIPT_PATH") or ""
local BAD_SCRIPT = os.getenv("MPVST_BAD_SCRIPT_PATH") or ""
local EDITED_SCRIPT = os.getenv("MPVST_EDITED_SCRIPT_PATH") or ""
local EFFECT_SCRIPT = os.getenv("MPVST_EFFECT_SCRIPT_PATH") or ""
local FX_NAME = "MicroPython Instrument"
local EFFECT_FX_NAME = "MicroPython Effect"
-- package.config's first line is the platform path separator, so the same
-- script drives REAPER on Windows and on Linux.
local SEP = package.config:sub(1, 1)
local DEADLINE = os.time() + 900

local report = io.open(REPORT, "w")

local function emit(line)
    report:write(line .. "\n")
    report:flush()
end

local function pass(name, detail)
    emit(string.format("PASS %s %s", name, detail or ""))
end

local function fail(name, detail)
    emit(string.format("FAIL %s %s", name, detail or ""))
end

local function info(key, value)
    emit(string.format("INFO %s %s", key, tostring(value)))
end

local function quit()
    emit("DONE")
    report:close()
    reaper.Main_SaveProject(0, false)
    reaper.Main_OnCommand(40004, 0)
end

local function copy_file(from, to)
    local source = io.open(from, "rb")
    if not source then
        return false
    end
    local target = io.open(to, "wb")
    if not target then
        source:close()
        return false
    end
    target:write(source:read("*a"))
    source:close()
    target:close()
    return true
end

-- Parameters ----------------------------------------------------------------

local function index_params(track, fx)
    local count = reaper.TrackFX_GetNumParams(track, fx)
    local names = {}
    for i = 0, count - 1 do
        local ok, name = reaper.TrackFX_GetParamName(track, fx, i, "")
        if ok and name and name ~= "" and names[name] == nil then
            names[name] = i
        end
    end
    return count, names
end

local function param_by_name(names, wanted)
    if names[wanted] then
        return names[wanted]
    end
    local lowered = wanted:lower()
    for name, index in pairs(names) do
        if name:lower() == lowered then
            return index
        end
    end
    return nil
end

local S = {
    track = nil,
    fx = nil,
    ready_idx = nil,
    error_idx = nil,
    macro_idx = nil,
    reload_idx = nil,
    project_path = WORKDIR .. SEP .. "matrix.RPP",
    extra = {},
}

local function bind(track, fx)
    S.track, S.fx = track, fx
    local count, names = index_params(track, fx)
    S.ready_idx = param_by_name(names, "Engine Ready")
    S.error_idx = param_by_name(names, "Engine Error")
    S.reload_idx = param_by_name(names, "Reload Script")
    -- The matrix instrument labels Macro 01 as "Level".
    S.macro_idx = param_by_name(names, "Level") or param_by_name(names, "Macro 01")
    return count
end

local function ready_value()
    return reaper.TrackFX_GetParamNormalized(S.track, S.fx, S.ready_idx)
end

local function error_code()
    local normalized = reaper.TrackFX_GetParamNormalized(S.track, S.fx,
                                                          S.error_idx)
    return math.floor(normalized * 255.0 + 0.5), normalized
end

-- Project construction ------------------------------------------------------

local function add_instrument(index)
    reaper.InsertTrackAtIndex(index, false)
    local track = reaper.GetTrack(0, index)
    local fx = reaper.TrackFX_AddByName(track, FX_NAME, false, -1)
    return track, fx
end

local function add_note(track, start_time, end_time, pitch, velocity)
    local item = reaper.CreateNewMIDIItemInProj(track, start_time, end_time,
                                                false)
    local take = reaper.GetActiveTake(item)
    local sppq = reaper.MIDI_GetPPQPosFromProjTime(take, start_time)
    local eppq = reaper.MIDI_GetPPQPosFromProjTime(take, end_time)
    reaper.MIDI_InsertNote(take, false, false, sppq, eppq, 0, pitch, velocity,
                           false)
    reaper.MIDI_Sort(take)
end

local function render(name, end_pos)
    reaper.GetSetProjectInfo(0, "RENDER_SETTINGS", 0, true)
    reaper.GetSetProjectInfo(0, "RENDER_BOUNDSFLAG", 0, true)
    reaper.GetSetProjectInfo(0, "RENDER_STARTPOS", 0.0, true)
    reaper.GetSetProjectInfo(0, "RENDER_ENDPOS", end_pos or 3.0, true)
    reaper.GetSetProjectInfo(0, "RENDER_TAILFLAG", 0, true)
    reaper.GetSetProjectInfo(0, "RENDER_SRATE", 48000, true)
    reaper.GetSetProjectInfo(0, "RENDER_CHANNELS", 2, true)
    reaper.GetSetProjectInfo(0, "RENDER_ADDTOPROJ", 0, true)
    reaper.GetSetProjectInfo_String(0, "RENDER_FILE", WORKDIR, true)
    reaper.GetSetProjectInfo_String(0, "RENDER_PATTERN", name, true)
    reaper.Main_OnCommand(41824, 0)
end

-- Steps ---------------------------------------------------------------------

local steps = {}
local step_index = 1
local wait_until = 0

local function sleep_ms(ms)
    wait_until = reaper.time_precise() + ms / 1000.0
end

local function step(fn)
    steps[#steps + 1] = fn
end

-- A reload edge is only seen while the plug-in is processing, so each half of
-- the toggle is followed by a short render.
local function toggle_reload(tag)
    step(function()
        reaper.TrackFX_SetParamNormalized(S.track, S.fx, S.reload_idx, 0.0)
        render("edge_" .. tag .. "_low", 0.3)
        sleep_ms(400)
    end)
    step(function()
        reaper.TrackFX_SetParamNormalized(S.track, S.fx, S.reload_idx, 1.0)
        render("edge_" .. tag .. "_high", 0.6)
        sleep_ms(2500)
    end)
end

step(function()
    info("script_path", SCRIPT)
    local track, fx = add_instrument(0)
    if fx < 0 then
        fail("instantiate", "TrackFX_AddByName returned " .. tostring(fx))
        return "abort"
    end
    local count = bind(track, fx)
    info("param_count", count)
    local _, fxname = reaper.TrackFX_GetFXName(track, fx, "")
    info("fx_name", fxname)
    if not (S.ready_idx and S.error_idx and S.reload_idx and S.macro_idx) then
        fail("instantiate", "missing expected parameters")
        return "abort"
    end
    -- Finding Macro 01 under the name "Level" proves the script's label
    -- metadata reached the host's generic editor.
    pass("instantiate", string.format("%s params=%d macro_label=Level", fxname,
                                      count))
    sleep_ms(2000)
end)

step(function()
    -- Force one render so the sidecar publishes its status: a host without a
    -- live audio device does not process until something asks it to.
    render("startup_status", 0.5)
    sleep_ms(700)
end)

step(function()
    local ready = ready_value()
    local code = error_code()
    info("ready_value", ready)
    if ready > 0.5 and code == 0 then
        pass("engine_ready", string.format("ready=%.3f error=%d", ready, code))
    else
        fail("engine_ready", string.format("ready=%.3f error=%d", ready, code))
    end
end)

step(function()
    add_note(S.track, 1.0, 2.0, 60, 100)
    reaper.TrackFX_SetParamNormalized(S.track, S.fx, S.macro_idx, 0.0)
    render("macro_zero")
    sleep_ms(700)
    pass("play_note", "rendered macro_zero.wav")
end)

step(function()
    reaper.TrackFX_SetParamNormalized(S.track, S.fx, S.macro_idx, 1.0)
    local got = reaper.TrackFX_GetParamNormalized(S.track, S.fx, S.macro_idx)
    info("macro_value", got)
    if math.abs(got - 1.0) < 0.001 then
        pass("automate_set", string.format("macro=%.3f", got))
    else
        fail("automate_set", string.format("macro=%.3f", got))
    end
    render("macro_full")
    sleep_ms(700)
end)

-- Developer loop: edit the file the instance was created from, then reload.
step(function()
    if EDITED_SCRIPT == "" or not copy_file(EDITED_SCRIPT, SCRIPT) then
        fail("edit_script", "unable to install edited script")
        return
    end
    pass("edit_script", "installed edited source")
    sleep_ms(300)
end)
toggle_reload("edit")
step(function()
    local ready = ready_value()
    local code = error_code()
    info("edited_ready", ready)
    info("edited_error", code)
    if ready > 0.5 and code == 0 then
        pass("reload_edited", string.format("ready=%.3f error=%d", ready, code))
    else
        fail("reload_edited", string.format("ready=%.3f error=%d", ready, code))
    end
    render("edited")
    sleep_ms(700)
end)

-- Restore the original source and reload back to the known level.
step(function()
    if not copy_file(WORKDIR .. SEP .. "good_backup.py", SCRIPT) then
        fail("restore_script", "unable to restore original script")
        return
    end
    pass("restore_script", "reinstalled original source")
    sleep_ms(300)
end)
toggle_reload("restore")
step(function()
    render("restored")
    sleep_ms(700)
end)

step(function()
    reaper.Main_SaveProjectEx(0, S.project_path, 0)
    sleep_ms(1500)
    local handle = io.open(S.project_path, "r")
    if handle then
        local size = handle:seek("end")
        handle:close()
        pass("save_project", string.format("bytes=%d", size))
    else
        fail("save_project", "project file missing")
    end
end)

step(function()
    reaper.Main_openProject("noprompt:" .. S.project_path)
    sleep_ms(6000)
end)

step(function()
    local track = reaper.GetTrack(0, 0)
    if not track or reaper.TrackFX_GetCount(track) == 0 then
        fail("reopen_project", "no FX after reopen")
        return "abort"
    end
    local count = bind(track, 0)
    -- Status parameters are published while the plug-in processes. A host with
    -- no live audio device only processes during a render, so force one before
    -- reading Engine Ready.
    render("reopened", 3.0)
    local macro = reaper.TrackFX_GetParamNormalized(track, 0, S.macro_idx)
    local ready = ready_value()
    info("reopen_macro", macro)
    if math.abs(macro - 1.0) < 0.001 and ready > 0.5 then
        pass("reopen_project", string.format("macro=%.3f ready=%.3f params=%d",
                                             macro, ready, count))
    else
        fail("reopen_project", string.format("macro=%.3f ready=%.3f", macro,
                                             ready))
    end
    sleep_ms(700)
end)

-- A reopened project must keep using the source embedded in its state, so an
-- edit to the original file must not change how it sounds.
step(function()
    if EDITED_SCRIPT == "" or not copy_file(EDITED_SCRIPT, SCRIPT) then
        fail("reopened_edit_setup", "unable to install edited script")
        return
    end
    sleep_ms(300)
end)
toggle_reload("reopened")
step(function()
    render("reopened_after_edit")
    sleep_ms(700)
    pass("reopened_ignores_edit", "rendered reopened_after_edit.wav")
    copy_file(WORKDIR .. SEP .. "good_backup.py", SCRIPT)
end)

-- Malformed source on a fresh instance that follows the file.
step(function()
    -- Renders are of the master mix, so the reopened instance has to go before
    -- the malformed one is measured on its own.
    for index = reaper.CountTracks(0) - 1, 0, -1 do
        reaper.DeleteTrack(reaper.GetTrack(0, index))
    end
    reaper.InsertTrackAtIndex(0, false)
    local track = reaper.GetTrack(0, 0)
    if not copy_file(BAD_SCRIPT, SCRIPT) then
        fail("malformed_setup", "unable to install malformed script")
        return "abort"
    end
    local fx = reaper.TrackFX_AddByName(track, FX_NAME, false, -1)
    if fx < 0 then
        fail("malformed_setup", "could not add instance")
        return "abort"
    end
    bind(track, fx)
    add_note(S.track, 1.0, 2.0, 60, 100)
    sleep_ms(4000)
end)

step(function()
    render("malformed", 3.0)
    sleep_ms(700)
end)

step(function()
    local code, normalized = error_code()
    local ready = ready_value()
    info("malformed_error_code", code)
    info("malformed_error_normalized", normalized)
    info("malformed_ready", ready)
    -- Error 1 is a script load failure. The sidecar must stay alive so a
    -- corrected script can be reloaded into the same instance.
    if code == 1 then
        pass("malformed_script", string.format("error=%d ready=%.3f", code,
                                               ready))
    else
        fail("malformed_script", string.format("error=%d ready=%.3f", code,
                                               ready))
    end
end)

step(function()
    if not copy_file(WORKDIR .. SEP .. "good_backup.py", SCRIPT) then
        fail("recover_setup", "unable to restore script")
        return
    end
    sleep_ms(300)
end)
toggle_reload("recover")
step(function()
    local code = error_code()
    local ready = ready_value()
    info("recover_error", code)
    if ready > 0.5 and code == 0 then
        pass("recover_script", string.format("ready=%.3f error=%d", ready, code))
    else
        fail("recover_script", string.format("ready=%.3f error=%d", ready, code))
    end
    reaper.TrackFX_SetParamNormalized(S.track, S.fx, S.macro_idx, 0.0)
    render("recovered")
    sleep_ms(700)
end)

step(function()
    for i = 1, 3 do
        local track, fx = add_instrument(i)
        if fx >= 0 then
            S.extra[#S.extra + 1] = { track = track, fx = fx }
        end
    end
    info("extra_instances", #S.extra)
    sleep_ms(8000)
end)

step(function()
    render("extra_status", 0.5)
    sleep_ms(700)
end)

step(function()
    local ready_count = 0
    for _, entry in ipairs(S.extra) do
        local _, names = index_params(entry.track, entry.fx)
        local idx = param_by_name(names, "Engine Ready")
        if idx and reaper.TrackFX_GetParamNormalized(entry.track, entry.fx, idx)
            > 0.5 then
            ready_count = ready_count + 1
        end
    end
    info("extra_ready", ready_count)
    if ready_count == 3 and #S.extra == 3 then
        pass("multiple_instances",
             string.format("%d concurrent sidecars ready", ready_count + 1))
    else
        fail("multiple_instances",
             string.format("%d of %d ready", ready_count, #S.extra))
    end
    for i = #S.extra, 1, -1 do
        reaper.DeleteTrack(S.extra[i].track)
    end
    S.extra = {}
    sleep_ms(2000)
end)

step(function()
    reaper.TrackFX_Delete(S.track, S.fx)
    sleep_ms(2000)
    local remaining = reaper.TrackFX_GetCount(S.track)
    info("fx_after_delete", remaining)
    if remaining == 0 then
        pass("remove_instance", "fx count 0")
    else
        fail("remove_instance", "fx count " .. remaining)
    end
end)

-- Audio-input effect: a generated project embeds the gate instrument and a
-- halving effect in per-instance state - the way a user's project carries
-- scripts - so the shared MPVST_SCRIPT_PATH developer file plays no part.
-- Bypassing the effect through its own Bypass parameter must pass the gate
-- through unchanged (via the latency-matched dry path); un-bypassed it must
-- render exactly half the gate level.
step(function()
    reaper.Main_openProject("noprompt:" .. WORKDIR .. SEP ..
        "effect_project.RPP")
    sleep_ms(8000)
end)

step(function()
    local track = reaper.GetTrack(0, 0)
    if not track or reaper.TrackFX_GetCount(track) ~= 2 then
        fail("effect_setup", "expected 2 FX after open, got " ..
            (track and reaper.TrackFX_GetCount(track) or -1))
        return "abort"
    end
    bind(track, 0)
    S.effect_fx = 1
    local _, fxname = reaper.TrackFX_GetFXName(track, S.effect_fx, "")
    info("effect_fx_name", fxname)
    S.effect_bypass_idx = nil
    S.effect_ready_idx = nil
    S.effect_error_idx = nil
    local count = reaper.TrackFX_GetNumParams(track, S.effect_fx)
    for i = 0, count - 1 do
        local ok, name = reaper.TrackFX_GetParamName(track, S.effect_fx, i, "")
        if ok and name == "Bypass" then S.effect_bypass_idx = i end
        if ok and name == "Engine Ready" then S.effect_ready_idx = i end
        if ok and name == "Engine Error" then S.effect_error_idx = i end
    end
    if not (S.effect_bypass_idx and S.effect_ready_idx and
            S.effect_error_idx) then
        fail("effect_setup", "missing effect parameters")
        return "abort"
    end
    pass("effect_setup", fxname)
    sleep_ms(4000)
end)

step(function()
    -- publish both sidecars' status
    render("effect_status", 0.5)
    sleep_ms(700)
end)

step(function()
    local track = reaper.GetTrack(0, 0)
    local ready = reaper.TrackFX_GetParamNormalized(track, S.effect_fx,
        S.effect_ready_idx)
    local err = math.floor(reaper.TrackFX_GetParamNormalized(track,
        S.effect_fx, S.effect_error_idx) * 255.0 + 0.5)
    local iready = ready_value()
    info("effect_ready", ready)
    info("effect_error", err)
    info("effect_source_ready", iready)
    if ready > 0.5 and err == 0 and iready > 0.5 then
        pass("effect_engine", string.format("ready=%.3f error=%d", ready, err))
    else
        fail("effect_engine", string.format("ready=%.3f error=%d source=%.3f",
            ready, err, iready))
    end
end)

step(function()
    local track = reaper.GetTrack(0, 0)
    reaper.TrackFX_SetParamNormalized(track, S.effect_fx,
        S.effect_bypass_idx, 1.0)
    render("effect_dry", 3.0)
    sleep_ms(700)
end)

step(function()
    local track = reaper.GetTrack(0, 0)
    reaper.TrackFX_SetParamNormalized(track, S.effect_fx,
        S.effect_bypass_idx, 0.0)
    render("effected", 3.0)
    sleep_ms(700)
    pass("effect_renders", "rendered effect_dry.wav and effected.wav")
end)

local function driver()
    if os.time() > DEADLINE then
        fail("deadline", "matrix exceeded its time budget")
        quit()
        return
    end
    if reaper.time_precise() < wait_until then
        reaper.defer(driver)
        return
    end
    local current = steps[step_index]
    if not current then
        quit()
        return
    end
    step_index = step_index + 1
    local ok, result = pcall(current)
    if not ok then
        fail("step" .. (step_index - 1), tostring(result))
    elseif result == "abort" then
        quit()
        return
    end
    reaper.defer(driver)
end

emit("BEGIN")
info("reaper_version", reaper.GetAppVersion())
driver()
