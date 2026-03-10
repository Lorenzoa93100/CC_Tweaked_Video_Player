-- vbc.lua
-- Point d'entrée principal : vbc play <id> [no]
--                            vbc list
--                            vbc info <id>
--
-- Installation : wget run http://<server>:4334/api/install

local VBC_VERSION = "2.0.0"

-- ── Charge les modules depuis le même dossier ────────────────────────────────
local scriptDir = fs.getDir(shell.getRunningProgram())
local function require_local(name)
    local path = fs.combine(scriptDir, name .. ".lua")
    if not fs.exists(path) then
        error("Module manquant : " .. path .. "\nRelance l'installateur.", 2)
    end
    local fn, err = loadfile(path)
    if not fn then error(err, 2) end
    return fn()
end

local config  = require_local("config")
local net     = require_local("net")
local player  = require_local("player")
local ui      = require_local("ui")

-- ── Commandes ────────────────────────────────────────────────────────────────

local function cmd_list()
    ui.header("VBC " .. VBC_VERSION)
    local ok, videos = pcall(net.get_videos)
    if not ok then
        ui.error("Impossible de contacter le serveur : " .. tostring(videos))
        return
    end
    if #videos == 0 then
        ui.info("Aucune vidéo sur le serveur.")
        return
    end
    ui.info(string.format("%-10s %-6s %-6s %-6s %s", "ID", "FPS", "DUR", "STATUS", "NOM"))
    ui.divider()
    for _, v in ipairs(videos) do
        local dur = v.duration and string.format("%.0fs", v.duration) or "?"
        local status = v.status or "?"
        local name = v.name or v.id or "?"
        ui.print(string.format("%-10s %-6s %-6s %-6s %s",
            v.id or "?", tostring(v.fps or "?"), dur, status, name))
    end
end

local function cmd_info(id)
    if not id then ui.error("Usage: vbc info <id>") return end
    local ok, meta = pcall(net.get_meta, id)
    if not ok then ui.error(tostring(meta)) return end
    ui.header("Vidéo : " .. id)
    for k, v in pairs(meta) do
        ui.print(string.format("  %-18s %s", k, tostring(v)))
    end
end

local function cmd_play(id, no_audio_flag)
    if not id then
        ui.error("Usage: vbc play <id> [no]")
        return
    end

    local use_audio = (no_audio_flag ~= "no")

    -- Vérifie que la vidéo est prête
    ui.status("Vérification de la vidéo " .. id .. "...")
    local ok, status = pcall(net.wait_ready, id, 30)
    if not ok then
        ui.error(tostring(status))
        return
    end

    local ok2, meta = pcall(net.get_meta, id)
    if not ok2 then
        ui.error("Impossible de récupérer les métadonnées : " .. tostring(meta))
        return
    end

    -- Trouve le monitor et le speaker
    local monitor = peripheral.find("monitor")
    if not monitor then
        ui.error("Aucun monitor détecté. Attache un Advanced Monitor.")
        return
    end

    local speaker = nil
    if use_audio and meta.has_audio then
        speaker = peripheral.find("speaker")
        if not speaker then
            ui.info("Aucun speaker trouvé. Lecture sans audio.")
        end
    end

    -- Lance la lecture
    ui.status(string.format("Lecture : %s (%dx%d @ %dfps, %.1fs)",
        meta.name or id, meta.width, meta.height, meta.fps, meta.duration or 0))
    
    player.play(meta, monitor, speaker)

    ui.status("Lecture terminée.")
end

local function cmd_help()
    ui.header("VBC " .. VBC_VERSION .. " — Video Block Converter")
    ui.print("  vbc play <id> [no]   Jouer une vidéo (no = sans audio)")
    ui.print("  vbc list             Lister les vidéos du serveur")
    ui.print("  vbc info <id>        Infos sur une vidéo")
    ui.print("")
    ui.print("Config: set vbc.server http://<ip>:4334")
end

-- ── Dispatch ─────────────────────────────────────────────────────────────────

local args = { ... }
local cmd = args[1]

if cmd == "play"  then cmd_play(args[2], args[3])
elseif cmd == "list"  then cmd_list()
elseif cmd == "info"  then cmd_info(args[2])
elseif cmd == "help" or cmd == nil then cmd_help()
else
    ui.error("Commande inconnue : " .. cmd)
    cmd_help()
end
