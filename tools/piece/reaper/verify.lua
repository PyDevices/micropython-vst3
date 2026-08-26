--[[
Headless verification and bounce for the Perihelion project.

Runs as Scripts/__startup.lua with the project given on the command line.
Confirms every declared MicroPython instrument/effect instance comes up ready,
that the macro automation envelopes are present, renders the full piece to
WAV, and quits.
Report lines go to MPVST_SCORE_REPORT.

A host with no live audio device only processes while rendering, so every
status read is preceded by a short render (see the DAW matrix notes).
]]

local REPORT = os.getenv("MPVST_SCORE_REPORT")
local WORKDIR = os.getenv("MPVST_SCORE_WORKDIR")
local RENDER_SECONDS = tonumber(os.getenv("MPVST_SCORE_SECONDS") or "238.1")
-- Base name for the rendered file; launch.sh looks for <name>.wav.
local BOUNCE = os.getenv("MPVST_SCORE_BOUNCE") or "perihelion_bounce"
local TRACKS = tonumber(os.getenv("MPVST_SCORE_TRACKS") or "16")
local INSTANCES = tonumber(os.getenv("MPVST_SCORE_INSTANCES") or tostring(TRACKS))
local MIN_ENVS = tonumber(os.getenv("MPVST_SCORE_MIN_ENVS") or "19")
local DEADLINE = os.time() + tonumber(os.getenv("MPVST_SCORE_DEADLINE")
                                      or "2400")

local report = io.open(REPORT, "w")

local function emit(line)
    report:write(line .. "\n")
    report:flush()
end

local function quit()
    emit("DONE")
    report:close()
    reaper.Main_OnCommand(40004, 0)
end

local function render(name, end_pos)
    reaper.GetSetProjectInfo(0, "RENDER_SETTINGS", 0, true)
    reaper.GetSetProjectInfo(0, "RENDER_BOUNDSFLAG", 0, true)
    reaper.GetSetProjectInfo(0, "RENDER_STARTPOS", 0.0, true)
    reaper.GetSetProjectInfo(0, "RENDER_ENDPOS", end_pos, true)
    reaper.GetSetProjectInfo(0, "RENDER_TAILFLAG", 0, true)
    reaper.GetSetProjectInfo(0, "RENDER_SRATE", 48000, true)
    reaper.GetSetProjectInfo(0, "RENDER_CHANNELS", 2, true)
    reaper.GetSetProjectInfo(0, "RENDER_ADDTOPROJ", 0, true)
    reaper.GetSetProjectInfo_String(0, "RENDER_FILE", WORKDIR, true)
    reaper.GetSetProjectInfo_String(0, "RENDER_PATTERN", name, true)
    reaper.Main_OnCommand(41824, 0)
end

local function param_index(track, fx, wanted)
    local count = reaper.TrackFX_GetNumParams(track, fx)
    for i = 0, count - 1 do
        local ok, name = reaper.TrackFX_GetParamName(track, fx, i, "")
        if ok and name == wanted then
            return i
        end
    end
    return nil
end

local steps = {}
local step_index = 1
local wait_until = 0

local function sleep_ms(ms)
    wait_until = reaper.time_precise() + ms / 1000.0
end

local function step(fn)
    steps[#steps + 1] = fn
end

step(function()
    local tracks = reaper.CountTracks(0)
    emit("INFO tracks " .. tracks)
    if tracks ~= TRACKS then
        emit("FAIL track_count expected " .. TRACKS .. " got " .. tracks)
        return "abort"
    end
    local instances = 0
    for t = 0, tracks - 1 do
        local track = reaper.GetTrack(0, t)
        instances = instances + reaper.TrackFX_GetCount(track)
    end
    emit("INFO instances " .. instances)
    if instances ~= INSTANCES then
        emit("FAIL fx_count expected " .. INSTANCES .. " got " .. instances)
        return "abort"
    end
    emit("PASS project_loaded " .. TRACKS .. " tracks, " .. INSTANCES ..
         " instances")
    sleep_ms(12000)
end)

step(function()
    -- publish sidecar status
    render("warmup", 2.0)
    sleep_ms(1500)
end)

step(function()
    local ready_count = 0
    local errors = {}
    for t = 0, TRACKS - 1 do
        local track = reaper.GetTrack(0, t)
        local _, name = reaper.GetTrackName(track)
        for fx = 0, reaper.TrackFX_GetCount(track) - 1 do
            local ridx = param_index(track, fx, "Engine Ready")
            local eidx = param_index(track, fx, "Engine Error")
            local ready = ridx and
                reaper.TrackFX_GetParamNormalized(track, fx, ridx) or 0
            local err = eidx and math.floor(
                reaper.TrackFX_GetParamNormalized(track, fx, eidx) * 255 + 0.5)
                or -1
            if ready > 0.5 and err == 0 then
                ready_count = ready_count + 1
            else
                errors[#errors + 1] = string.format(
                    "%s/fx%d ready=%.2f err=%d", name, fx, ready, err)
            end
        end
    end
    emit("INFO engines_ready " .. ready_count)
    if ready_count == INSTANCES then
        emit("PASS engines_ready " .. ready_count .. " of " .. INSTANCES)
    else
        emit("FAIL engines_ready " .. table.concat(errors, "; "))
        return "abort"
    end
end)

step(function()
    -- macro automation envelopes present where the score declares them
    local envs = 0
    for t = 0, TRACKS - 1 do
        local track = reaper.GetTrack(0, t)
        for fx = 0, reaper.TrackFX_GetCount(track) - 1 do
            -- Macros occupy ordinals 5..20: 0 Bypass, 1 Reload Script,
            -- 2 Engine Ready, 3 Engine Error, 4 Patches, then the macros.
            for p = 5, 20 do
                local env = reaper.GetFXEnvelope(track, fx, p, false)
                if env ~= nil and reaper.CountEnvelopePointsEx(env, -1) > 1 then
                    envs = envs + 1
                end
            end
        end
    end
    emit("INFO macro_envelopes " .. envs)
    if envs >= MIN_ENVS then
        emit("PASS automation " .. envs .. " macro envelopes")
    else
        emit("FAIL automation expected >=" .. MIN_ENVS ..
             " envelopes, found " .. envs)
    end
end)

step(function()
    emit("INFO render_begin " .. os.date("%H:%M:%S"))
    render(BOUNCE, RENDER_SECONDS)
    emit("INFO render_end " .. os.date("%H:%M:%S"))
    emit("PASS rendered " .. BOUNCE .. ".wav")
end)

local function driver()
    if os.time() > DEADLINE then
        emit("FAIL deadline exceeded")
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
        emit("FAIL step" .. (step_index - 1) .. " " .. tostring(result))
        quit()
        return
    elseif result == "abort" then
        quit()
        return
    end
    reaper.defer(driver)
end

emit("BEGIN")
emit("INFO reaper_version " .. reaper.GetAppVersion())
driver()
