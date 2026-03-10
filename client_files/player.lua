-- player.lua
-- Orchestre la lecture vidéo + audio en parallèle.
--
-- Architecture :
--   parallel.waitForAny(
--     video_task,   -- boucle de rendu des frames à fps constant
--     audio_task,   -- télécharge + joue les chunks DFPWM en avance
--     input_task    -- écoute 'q' pour quitter
--   )
--
-- Synchronisation audio/vidéo :
--   On utilise os.clock() comme référence de temps.
--   Chaque frame est affichée au bon moment : t_frame = frame_index / fps
--   Si le rendu prend trop longtemps, on saute des frames pour rattraper.
--
-- Gestion mémoire :
--   - Si la vidéo est petite (<= MAX_PRECOMPUTE_FRAMES), on pré-calcule
--     toutes les lignes blit en une seule passe (plus rapide à l'affichage).
--   - Sinon, on décode à la volée frame par frame (économise la RAM).

local net    = require_local("net")
local frames = require_local("frames")
local ui     = require_local("ui")

local player = {}

-- Seuil de pré-calcul : si la vidéo a moins de N frames, on pré-calcule tout
local MAX_PRECOMPUTE_FRAMES = 300  -- ~30s à 10fps, ~2MB pour 51×19

function player.play(meta, monitor, speaker)
    local id          = meta.id
    local width       = meta.width
    local height      = meta.height
    local fps         = meta.fps or 10
    local frame_count = meta.frame_count or 0
    local has_audio   = meta.has_audio and speaker ~= nil
    local n_chunks    = meta.audio_chunks or 0
    local chunk_secs  = meta.audio_chunk_seconds or 5

    -- ── Téléchargement des frames ──────────────────────────────────────────
    ui.status("Téléchargement des frames...")
    local raw_data = net.get_frames(id)

    -- Vérifie le header
    local w, h, fc = frames.parse_header(raw_data)
    if w ~= width or h ~= height then
        ui.info(string.format("Avertissement : résolution déclarée %dx%d, réelle %dx%d",
            width, height, w, h))
        width, height = w, h
    end
    frame_count = fc

    -- ── Prépare le monitor ─────────────────────────────────────────────────
    monitor.setTextScale(0.5)  -- taille minimale = plus de pixels
    monitor.clear()
    monitor.setCursorBlink(false)
    local mon_w, mon_h = monitor.getSize()

    if mon_w < width or mon_h < height then
        ui.info(string.format(
            "Monitor %dx%d trop petit pour %dx%d. Agrandis le monitor.",
            mon_w, mon_h, width, height))
    end

    -- ── Pré-calcul si possible ─────────────────────────────────────────────
    local precomputed = nil
    if frame_count <= MAX_PRECOMPUTE_FRAMES then
        ui.status("Pré-calcul des frames blit...")
        precomputed = frames.precompute(raw_data, width, height, frame_count)
        raw_data = nil  -- libère la mémoire du binaire brut
        collectgarbage()
    end

    -- ── Variable partagée entre tâches ─────────────────────────────────────
    local should_stop = false
    local start_time  = nil

    -- ── Tâche vidéo ───────────────────────────────────────────────────────
    local function video_task()
        local frame_duration = 1 / fps
        start_time = os.clock()

        for fi = 0, frame_count - 1 do
            if should_stop then break end

            -- Calcule quand cette frame doit être affichée
            local target_time = start_time + fi * frame_duration
            local now = os.clock()

            -- Si on est en retard de plus d'une frame, on saute
            if now > target_time + frame_duration then
                -- Skip silencieux (rattrapage)
            else
                -- Attend jusqu'au bon moment (sleep précis)
                local wait = target_time - now
                if wait > 0.001 then
                    os.sleep(wait)
                end

                -- Affiche la frame
                if precomputed then
                    frames.render_precomputed(monitor, precomputed[fi + 1], height)
                else
                    frames.render(monitor, raw_data, fi, width, height)
                end
            end
        end

        should_stop = true
    end

    -- ── Tâche audio ───────────────────────────────────────────────────────
    local function audio_task()
        if not has_audio or n_chunks == 0 then return end

        local dfpwm   = require("cc.audio.dfpwm")
        local decoder = dfpwm.make_decoder()

        -- Attend que la vidéo démarre (start_time est mis par video_task)
        while start_time == nil do os.sleep(0.05) end

        for ci = 0, n_chunks - 1 do
            if should_stop then break end

            -- Calcule à quel moment ce chunk doit démarrer
            local chunk_start = ci * chunk_secs

            -- Attend qu'on soit ~0.5s avant le chunk (précharge en avance)
            local deadline = start_time + chunk_start - 0.5
            local now = os.clock()
            if deadline > now then
                os.sleep(deadline - now)
            end

            if should_stop then break end

            -- Télécharge le chunk
            local ok, chunk_data = pcall(net.get_audio_chunk, id, ci)
            if not ok then
                -- Chunk manquant : on continue (pas fatal)
                ui.info("Chunk audio " .. ci .. " manquant, skip.")
            else
                -- Décode DFPWM → PCM par blocs de 16Ko
                local CHUNK_SIZE = 16 * 1024
                local pos = 1
                while pos <= #chunk_data do
                    if should_stop then break end
                    local sub = chunk_data:sub(pos, pos + CHUNK_SIZE - 1)
                    local pcm_buffer = decoder(sub)
                    -- speaker.playAudio retourne false si buffer plein → on attend
                    while not speaker.playAudio(pcm_buffer) do
                        os.pullEvent("speaker_audio_empty")
                    end
                    pos = pos + CHUNK_SIZE
                end
            end
        end
    end

    -- ── Tâche input ───────────────────────────────────────────────────────
    local function input_task()
        while not should_stop do
            local event, key = os.pullEvent("key")
            if key == keys.q then
                should_stop = true
                ui.status("Lecture interrompue.")
                return
            end
        end
    end

    -- ── Lancement parallèle ───────────────────────────────────────────────
    if has_audio then
        parallel.waitForAny(video_task, audio_task, input_task)
    else
        parallel.waitForAny(video_task, input_task)
    end

    -- Nettoie le monitor
    monitor.clear()
    monitor.setCursorPos(1, 1)
end

return player
