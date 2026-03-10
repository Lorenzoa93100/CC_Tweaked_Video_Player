-- net.lua
-- Helpers HTTP pour communiquer avec le serveur VBC.
--
-- Optimisation clé : les frames sont téléchargées en binaire (application/octet-stream)
-- via http.get avec binary=true, ce qui évite toute conversion UTF-8 et est 2-3× 
-- plus rapide que du JSON côté parsing Lua.

local config = require_local("config")
local net = {}

-- ── Helpers de base ──────────────────────────────────────────────────────────

-- GET JSON → table Lua
function net.get_json(path)
    local url = config.url(path)
    local res, err = http.get(url)
    if not res then
        error("HTTP GET " .. url .. " échoué : " .. tostring(err), 2)
    end
    local body = res.readAll()
    res.close()
    local ok, data = pcall(textutils.unserialiseJSON, body)
    if not ok or data == nil then
        error("JSON invalide depuis " .. url, 2)
    end
    return data
end

-- GET binaire → string de bytes
function net.get_binary(path)
    local url = config.url(path)
    local res, err = http.get(url, nil, true)  -- true = mode binaire
    if not res then
        error("HTTP GET (bin) " .. url .. " échoué : " .. tostring(err), 2)
    end
    local data = res.readAll()
    res.close()
    return data
end

-- ── API VBC ──────────────────────────────────────────────────────────────────

function net.get_videos()
    return net.get_json("/api/videos")
end

function net.get_meta(id)
    return net.get_json("/api/videos/" .. id)
end

function net.get_status(id)
    return net.get_json("/api/videos/" .. id .. "/status")
end

-- Attend que la vidéo soit "ready" (polling, timeout en secondes)
function net.wait_ready(id, timeout)
    local deadline = os.clock() + (timeout or 30)
    while os.clock() < deadline do
        local status_data = net.get_status(id)
        if status_data.status == "ready" then return true end
        if status_data.status == "error" then
            error("Erreur serveur : " .. (status_data.error or "inconnue"), 2)
        end
        os.sleep(1)
    end
    error("Timeout : la vidéo n'est pas prête après " .. timeout .. "s", 2)
end

-- Télécharge tout le fichier frames.bin en binaire
function net.get_frames(id)
    return net.get_binary("/api/videos/" .. id .. "/frames")
end

-- Télécharge un chunk audio DFPWM en binaire
function net.get_audio_chunk(id, chunk_index)
    return net.get_binary("/api/videos/" .. id .. "/audio/" .. chunk_index)
end

return net
