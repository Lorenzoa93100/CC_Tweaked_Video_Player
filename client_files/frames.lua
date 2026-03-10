-- frames.lua
-- Décode le format binaire VBCF et convertit en blit CC.
--
-- Format VBCF (rappel) :
--   [4]  "VBCF"
--   [2]  width  (uint16 LE)
--   [2]  height (uint16 LE)
--   [4]  frame_count (uint32 LE)
--   puis frame_count × (width × height bytes), chaque byte = index CC 0-15
--
-- Optimisation rendu :
--   On utilise monitor.blit() ligne par ligne.
--   blit(text, fg, bg) prend des strings de caractères couleur CC hexadécimaux.
--   On pré-construit ces strings en Lua pur — c'est la méthode la plus rapide
--   pour remplir un monitor sans utiliser setCursorPos/setBackgroundColor/write
--   pour chaque pixel (ce qui serait 3 appels par pixel !).
--
-- Table de correspondance index CC → char hex blit :
--   0=white='0', 1=orange='1', ..., 9=cyan='9',
--   10=purple='a', 11=blue='b', 12=brown='c', 13=green='d', 14=red='e', 15=black='f'

local frames = {}

-- Hex chars pour blit (index CC 0-15 → char)
local HEX = { "0","1","2","3","4","5","6","7","8","9","a","b","c","d","e","f" }

-- ── Parsing du header ────────────────────────────────────────────────────────

local function bytes_to_u16_le(s, i)
    return string.byte(s, i) + string.byte(s, i+1) * 256
end

local function bytes_to_u32_le(s, i)
    return string.byte(s, i)
        + string.byte(s, i+1) * 256
        + string.byte(s, i+2) * 65536
        + string.byte(s, i+3) * 16777216
end

function frames.parse_header(data)
    if #data < 12 then error("Fichier frames trop court") end
    local magic = data:sub(1, 4)
    if magic ~= "VBCF" then error("Magic invalide : " .. magic) end
    local width       = bytes_to_u16_le(data, 5)
    local height      = bytes_to_u16_le(data, 7)
    local frame_count = bytes_to_u32_le(data, 9)
    return width, height, frame_count
end

-- ── Rendu d'une frame ────────────────────────────────────────────────────────
--
-- Construit les strings blit pour chaque ligne et les envoie au monitor.
-- 
-- Stratégie blit :
--   - text = une string de W espaces (" "×W) — on affiche des blocs pleins
--   - fg   = couleur de texte (inutilisée car que des espaces, mais obligatoire)
--   - bg   = couleur de fond pixel par pixel
--
-- En utilisant "\127" (bloc plein) comme caractère, on peut aussi mettre
-- la couleur dans fg et avoir un rendu légèrement différent, mais " " + bg
-- est plus simple et tout aussi efficace visuellement.

function frames.render(monitor, data, frame_index, width, height)
    local pixel_count = width * height
    -- Offset dans data : 12 bytes de header + frame_index * pixel_count
    local base = 12 + frame_index * pixel_count + 1  -- +1 : Lua 1-indexed

    for y = 1, height do
        local row_start = base + (y - 1) * width
        -- Construit les strings fg et bg pour cette ligne
        -- text = W espaces, fg = tout noir (peu importe), bg = couleurs pixels
        local bg_chars = {}
        for x = 1, width do
            local color_idx = string.byte(data, row_start + x - 1)
            bg_chars[x] = HEX[color_idx + 1]  -- +1 car Lua 1-indexed
        end
        local text_str = string.rep(" ", width)
        local fg_str   = string.rep("f", width)  -- noir, inutilisé
        local bg_str   = table.concat(bg_chars)
        monitor.setCursorPos(1, y)
        monitor.blit(text_str, fg_str, bg_str)
    end
end

-- ── Pré-construction des lignes (optionnel, pour perf extrême) ───────────────
--
-- Si on veut aller encore plus vite, on peut pré-construire toutes les lignes
-- de toutes les frames en une seule passe au chargement.
-- Utile si la vidéo tient entièrement en RAM CC (~2MB max).

function frames.precompute(data, width, height, frame_count)
    local pixel_count = width * height
    local all_frames = {}

    for fi = 0, frame_count - 1 do
        local base = 12 + fi * pixel_count + 1
        local frame_lines = {}
        for y = 1, height do
            local row_start = base + (y - 1) * width
            local bg_chars = {}
            for x = 1, width do
                local color_idx = string.byte(data, row_start + x - 1)
                bg_chars[x] = HEX[color_idx + 1]
            end
            frame_lines[y] = {
                text = string.rep(" ", width),
                fg   = string.rep("f", width),
                bg   = table.concat(bg_chars),
            }
        end
        all_frames[fi + 1] = frame_lines
    end

    return all_frames
end

-- Affiche une frame pré-calculée
function frames.render_precomputed(monitor, precomputed_frame, height)
    for y = 1, height do
        local line = precomputed_frame[y]
        monitor.setCursorPos(1, y)
        monitor.blit(line.text, line.fg, line.bg)
    end
end

return frames
