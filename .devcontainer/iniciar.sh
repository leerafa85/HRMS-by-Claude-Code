#!/usr/bin/env bash
# Arranca el HRMS en GitHub Codespaces: actualiza el código, prepara la base y levanta el servidor.
cd "$(dirname "$0")/.." || exit 1

URL="https://${CODESPACE_NAME:-localhost}-8000.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
[ -z "$CODESPACE_NAME" ] && URL="http://localhost:8000"

aviso() {
  printf '\n\033[1;32m%s\033[0m\n' "=================================================================="
  printf '\033[1;32m  HRMS funcionando. Abrilo tocando este enlace o el globo del puerto 8000:\033[0m\n'
  printf '\033[1;36m  %s\033[0m\n' "$URL"
  printf '\033[1;32m  Usuario: admin   Clave: admin1234\033[0m\n'
  printf '\033[1;32m%s\033[0m\n\n' "=================================================================="
}

# Si el servidor ya está corriendo (por ejemplo, al reconectar), solo se muestra el aviso.
if curl -fsS -o /dev/null --max-time 3 http://127.0.0.1:8000/estado/ 2>/dev/null; then
  aviso
  exit 0
fi

echo "Actualizando el HRMS (puede tardar un minuto)..."
git pull --ff-only -q || echo "No se pudo actualizar desde GitHub; se usa la versión actual."
pip install -q -r requirements.txt
python manage.py migrate --noinput
python manage.py inicializar
[ -f .devcontainer/.datos_demo_ok ] || { python manage.py datos_demo && touch .devcontainer/.datos_demo_ok; }

aviso
exec python manage.py runserver 0.0.0.0:8000
