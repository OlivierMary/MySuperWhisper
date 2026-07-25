#!/bin/bash
set -e

# Couleurs pour l'affichage
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}       MySuperWhisper - Installation            ${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# Récupération du chemin absolu du dossier du projet
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
DESKTOP_TEMPLATE="$PROJECT_DIR/mysuperwhisper.desktop"
AUTOSTART_DIR="$HOME/.config/autostart"
APPLICATIONS_DIR="$HOME/.local/share/applications"
DEST_FILE_AUTOSTART="$AUTOSTART_DIR/mysuperwhisper.desktop"
DEST_FILE_APP="$APPLICATIONS_DIR/mysuperwhisper.desktop"
VENV_DIR="$PROJECT_DIR/venv"

echo -e "${GREEN}[1/6]${NC} Dossier du projet : $PROJECT_DIR"

# =============================================================================
# Détection du gestionnaire de paquets
# =============================================================================
echo ""
echo -e "${GREEN}[2/6]${NC} Détection du système..."

detect_package_manager() {
    if command -v apt &> /dev/null; then
        echo "apt"
    elif command -v dnf &> /dev/null; then
        echo "dnf"
    elif command -v pacman &> /dev/null; then
        echo "pacman"
    elif command -v zypper &> /dev/null; then
        echo "zypper"
    else
        echo "unknown"
    fi
}

PKG_MANAGER=$(detect_package_manager)
echo "   Gestionnaire de paquets : $PKG_MANAGER"

# Détection du type de session (X11 ou Wayland)
SESSION_TYPE="${XDG_SESSION_TYPE:-x11}"
echo "   Type de session : $SESSION_TYPE"

# =============================================================================
# Installation des dépendances système
# =============================================================================
echo ""
echo -e "${GREEN}[3/6]${NC} Installation des dépendances système..."

install_system_deps() {
    case $PKG_MANAGER in
        apt)
            # Dépendances de base
            DEPS="python3 python3-pip python3-venv python3-dev"
            # GUI (tkinter pour la popup historique et la config raccourcis)
            DEPS="$DEPS python3-tk"
            # Audio
            DEPS="$DEPS portaudio19-dev libsndfile1"
            # GTK/Tray (python3-gi for distro Python; -dev + cairo for pip PyGObject
            # when the venv Python ABI does not match system gi, e.g. Python 3.13)
            DEPS="$DEPS python3-gi gir1.2-ayatanaappindicator3-0.1"
            DEPS="$DEPS libgirepository1.0-dev libgirepository-2.0-dev libcairo2-dev"
            # Clipboard
            DEPS="$DEPS xclip xsel"
            # Typing tool selon la session
            if [ "$SESSION_TYPE" = "wayland" ]; then
                DEPS="$DEPS wtype"
            else
                DEPS="$DEPS xdotool"
            fi
            echo "   Installation via apt..."
            sudo apt update
            sudo apt install -y $DEPS
            ;;
        dnf)
            DEPS="python3 python3-pip python3-devel"
            DEPS="$DEPS python3-tkinter"
            DEPS="$DEPS portaudio-devel libsndfile"
            DEPS="$DEPS python3-gobject gtk3 libappindicator-gtk3"
            DEPS="$DEPS xclip xsel"
            if [ "$SESSION_TYPE" = "wayland" ]; then
                DEPS="$DEPS wtype"
            else
                DEPS="$DEPS xdotool"
            fi
            echo "   Installation via dnf..."
            sudo dnf install -y $DEPS
            ;;
        pacman)
            DEPS="python python-pip"
            DEPS="$DEPS tk"
            DEPS="$DEPS portaudio libsndfile"
            DEPS="$DEPS python-gobject gtk3 libappindicator-gtk3"
            DEPS="$DEPS xclip xsel"
            if [ "$SESSION_TYPE" = "wayland" ]; then
                DEPS="$DEPS wtype"
            else
                DEPS="$DEPS xdotool"
            fi
            echo "   Installation via pacman..."
            sudo pacman -S --needed --noconfirm $DEPS
            ;;
        zypper)
            DEPS="python3 python3-pip python3-devel"
            DEPS="$DEPS python3-tk"
            DEPS="$DEPS portaudio-devel libsndfile1"
            DEPS="$DEPS python3-gobject gtk3 typelib-1_0-AyatanaAppIndicator3-0_1"
            DEPS="$DEPS xclip xsel"
            if [ "$SESSION_TYPE" = "wayland" ]; then
                DEPS="$DEPS wtype"
            else
                DEPS="$DEPS xdotool"
            fi
            echo "   Installation via zypper..."
            sudo zypper install -y $DEPS
            ;;
        *)
            echo -e "${YELLOW}   Gestionnaire de paquets non reconnu.${NC}"
            echo "   Veuillez installer manuellement les dépendances suivantes :"
            echo "   - Python 3, pip, venv"
            echo "   - PortAudio (dev)"
            echo "   - GTK3, GObject Introspection, AppIndicator"
            echo "   - xclip ou xsel"
            if [ "$SESSION_TYPE" = "wayland" ]; then
                echo "   - wtype (pour Wayland)"
            else
                echo "   - xdotool (pour X11)"
            fi
            read -p "   Appuyez sur Entrée pour continuer ou Ctrl+C pour annuler..."
            ;;
    esac
}

install_system_deps

# =============================================================================
# Création de l'environnement virtuel Python
# =============================================================================
echo ""
echo -e "${GREEN}[4/6]${NC} Configuration de l'environnement Python..."

VENV_NEEDS_RECREATE=false

if [ -d "$VENV_DIR" ]; then
    # Vérifier si le venv a été créé avec --system-site-packages
    if [ -f "$VENV_DIR/pyvenv.cfg" ]; then
        if ! grep -q "include-system-site-packages = true" "$VENV_DIR/pyvenv.cfg"; then
            echo -e "${YELLOW}   Venv existant sans accès système, recréation nécessaire...${NC}"
            VENV_NEEDS_RECREATE=true
        fi
    else
        VENV_NEEDS_RECREATE=true
    fi
fi

if [ ! -d "$VENV_DIR" ] || [ "$VENV_NEEDS_RECREATE" = true ]; then
    if [ -d "$VENV_DIR" ]; then
        echo "   Suppression de l'ancien venv..."
        rm -rf "$VENV_DIR"
    fi
    echo "   Création de l'environnement virtuel..."
    # --system-site-packages permet d'accéder à python3-gi du système
    python3 -m venv --system-site-packages "$VENV_DIR"
else
    echo "   Environnement virtuel existant OK."
fi

# Utilisation directe du pip du venv (pas besoin d'activer)
VENV_PIP="$VENV_DIR/bin/pip"

# Mise à jour de pip
echo "   Mise à jour de pip..."
"$VENV_PIP" install --upgrade pip --quiet

# =============================================================================
# Installation des dépendances Python
# =============================================================================
echo ""
echo -e "${GREEN}[5/6]${NC} Installation des dépendances Python..."

if [ -f "$PROJECT_DIR/requirements.txt" ]; then
    echo "   Installation depuis requirements.txt..."
    "$VENV_PIP" install --upgrade -r "$PROJECT_DIR/requirements.txt"
else
    echo -e "${YELLOW}   requirements.txt non trouvé, installation manuelle...${NC}"
    "$VENV_PIP" install --upgrade faster-whisper sounddevice numpy pynput pystray Pillow pyperclip
fi

# =============================================================================
# Configuration des fichiers .desktop
# =============================================================================
echo ""
echo -e "${GREEN}[6/6]${NC} Configuration du lancement automatique..."

PYTHON_EXEC="$VENV_DIR/bin/python"

# Création du dossier Autostart si inexistant
if [ ! -d "$AUTOSTART_DIR" ]; then
    mkdir -p "$AUTOSTART_DIR"
fi

# Création du dossier Applications si inexistant
if [ ! -d "$APPLICATIONS_DIR" ]; then
    mkdir -p "$APPLICATIONS_DIR"
fi

# Génération des fichiers .desktop
if [ -f "$DESKTOP_TEMPLATE" ]; then
    sed -e "s|__PYTHON_EXEC__|$PYTHON_EXEC|g" \
        -e "s|__SCRIPT_PATH__|-m mysuperwhisper|g" \
        -e "s|__WORK_DIR__|$PROJECT_DIR/|g" \
        -e "s|__ICON_PATH__|$PROJECT_DIR/mysuperwhisper.svg|g" \
        "$DESKTOP_TEMPLATE" > "$DEST_FILE_AUTOSTART"

    cp "$DEST_FILE_AUTOSTART" "$DEST_FILE_APP"
    chmod +x "$DEST_FILE_AUTOSTART"
    chmod +x "$DEST_FILE_APP"

    echo "   Fichiers .desktop créés :"
    echo "   - $DEST_FILE_AUTOSTART"
    echo "   - $DEST_FILE_APP"
else
    echo -e "${YELLOW}   Template .desktop non trouvé, étape ignorée.${NC}"
fi

# =============================================================================
# Résumé
# =============================================================================
echo ""
echo -e "${BLUE}================================================${NC}"
echo -e "${GREEN}Installation terminée !${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""
echo "Configuration :"
echo "  - Session     : $SESSION_TYPE"
if [ "$SESSION_TYPE" = "wayland" ]; then
    echo "  - Outil typing: wtype"
else
    echo "  - Outil typing: xdotool"
fi
echo "  - Python      : $PYTHON_EXEC"
echo ""
echo "Pour lancer manuellement :"
echo "  cd $PROJECT_DIR && $PYTHON_EXEC -m mysuperwhisper"
echo ""
echo "Le programme se lancera automatiquement à la prochaine session."
echo "Il est également disponible dans le menu d'applications."
echo ""
