#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
PYTHON_BIN=${PYTHON_BIN:-python3}
DATA_DIR=${XDG_DATA_HOME:-${HOME:?HOME is required}/.local/share}/research-radar
BIN_DIR=${XDG_BIN_HOME:-${HOME:?HOME is required}/.local/bin}
CODEX_ROOT=${CODEX_HOME:-${HOME:?HOME is required}/.codex}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --python)
            PYTHON_BIN=$2
            shift 2
            ;;
        --data-dir)
            DATA_DIR=$2
            shift 2
            ;;
        --bin-dir)
            BIN_DIR=$2
            shift 2
            ;;
        --codex-home)
            CODEX_ROOT=$2
            shift 2
            ;;
        -h|--help)
            echo "Usage: scripts/install.sh [--python PATH] [--data-dir DIR] [--bin-dir DIR] [--codex-home DIR]"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 2
            ;;
    esac
done

for target in "$REPO_ROOT" "$DATA_DIR" "$BIN_DIR" "$CODEX_ROOT"; do
    case "$target" in
        /*) ;;
        *)
            echo "Installation paths must be absolute: $target" >&2
            exit 2
            ;;
    esac
done

"$PYTHON_BIN" -c 'import sys; assert sys.version_info >= (3, 9), "Research Radar requires Python 3.9+"'

VENV_DIR=$DATA_DIR/venv
mkdir -p "$DATA_DIR" "$BIN_DIR" "$CODEX_ROOT/skills"
if [ ! -x "$VENV_DIR/bin/python" ]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/python" -m pip install --upgrade "$REPO_ROOT"

SKILL_SOURCE=$REPO_ROOT/.agents/skills/research-radar
SKILL_TARGET=$CODEX_ROOT/skills/research-radar
if [ ! -f "$SKILL_SOURCE/SKILL.md" ]; then
    echo "Repository skill is missing: $SKILL_SOURCE/SKILL.md" >&2
    exit 2
fi
STAGING_DIR=$(mktemp -d "${TMPDIR:-/tmp}/research-radar-skill.XXXXXX")
trap 'rm -rf "$STAGING_DIR"' EXIT HUP INT TERM
cp -R "$SKILL_SOURCE" "$STAGING_DIR/research-radar"
if [ -e "$SKILL_TARGET" ]; then
    SKILL_BACKUP=$SKILL_TARGET.backup.$(date -u +%Y%m%dT%H%M%SZ)
    mv "$SKILL_TARGET" "$SKILL_BACKUP"
    echo "Previous skill preserved at $SKILL_BACKUP"
fi
mv "$STAGING_DIR/research-radar" "$SKILL_TARGET"

WRAPPER_TMP=$(mktemp "${TMPDIR:-/tmp}/research-radar-wrapper.XXXXXX")
printf '#!/bin/sh\n\nexec "%s" "$@"\n' "$VENV_DIR/bin/research-radar" > "$WRAPPER_TMP"
chmod 755 "$WRAPPER_TMP"
mv "$WRAPPER_TMP" "$BIN_DIR/research-radar"

"$VENV_DIR/bin/research-radar" --help >/dev/null
INSTALLED_VERSION=$(
    "$VENV_DIR/bin/python" -c 'import research_radar; print(research_radar.__version__)'
)

echo "Installed Research Radar $INSTALLED_VERSION"
echo "CLI: $BIN_DIR/research-radar"
echo "Skill: $SKILL_TARGET"
echo "If this is the first install, start a new Codex turn before invoking \$research-radar."
