-- install.lua
-- Script d'installation téléchargé via :
--   wget run http://<server>:4334/api/install
--
-- Télécharge tous les fichiers du client depuis le serveur et les installe
-- dans /vbc/ sur l'ordinateur CC.

local INSTALL_DIR = "/vbc"
local FILES = {
    "vbc.lua",
    "config.lua",
    "net.lua",
    "frames.lua",
    "player.lua",
    "ui.lua",
}

-- Détecte l'URL du serveur depuis les args ou depuis l'URL de ce script
local server_url = ...  -- passé par wget run si besoin

if not server_url then
    -- Essaie de lire vbc.server depuis les settings
    local s = settings.get("vbc.server")
    if s then
        server_url = s:gsub("/+$", "")
    else
        print("Usage: wget run <url_install> <url_serveur>")
        print("  ou : set vbc.server http://<ip>:4334  puis relance")
        error("URL serveur manquante", 0)
    end
end

print("Installation de VBC depuis " .. server_url)
print("Dossier : " .. INSTALL_DIR)
print("")

-- Crée le dossier si besoin
if not fs.exists(INSTALL_DIR) then
    fs.makeDir(INSTALL_DIR)
end

-- Télécharge chaque fichier
local ok_count = 0
for _, fname in ipairs(FILES) do
    local url  = server_url .. "/api/client/" .. fname
    local dest = fs.combine(INSTALL_DIR, fname)
    io.write("  " .. fname .. " ... ")
    local ok = http.checkURL(url)
    if ok then
        local success = shell.execute("wget", "-q", url, dest)
        if success then
            print("OK")
            ok_count = ok_count + 1
        else
            print("ECHEC (wget)")
        end
    else
        print("ECHEC (URL inaccessible)")
    end
end

print("")
print(ok_count .. "/" .. #FILES .. " fichiers installés.")

if ok_count == #FILES then
    -- Crée un alias 'vbc' dans le PATH
    local alias_path = "/vbc/vbc"
    -- Sous CC, on peut créer un shell alias ou mettre vbc.lua dans /bin
    -- On copie vbc.lua vers /bin/vbc pour qu'il soit accessible partout
    if fs.exists("/bin") or true then
        fs.copy(INSTALL_DIR .. "/vbc.lua", "/bin/vbc")
        print("Alias /bin/vbc créé.")
    end

    -- Sauvegarde l'URL du serveur
    settings.set("vbc.server", server_url)
    settings.save()

    print("")
    print("Installation terminée !")
    print("Configure le serveur si pas déjà fait :")
    print("  set vbc.server " .. server_url)
    print("")
    print("Commandes disponibles :")
    print("  vbc list")
    print("  vbc play <id>")
else
    print("Installation incomplète. Vérifie la connexion au serveur.")
end
