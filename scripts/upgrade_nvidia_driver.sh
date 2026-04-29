#!/usr/bin/env bash
# Instala o driver NVIDIA recomendado pelo Ubuntu para esta GPU (Jammy).
# Execução: sudo bash scripts/upgrade_nvidia_driver.sh
# Depois: reinicia o sistema e verifica com: nvidia-smi

set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Execute como root: sudo bash $0" >&2
  exit 1
fi

echo "Pacotes NVIDIA atuais:"
dpkg -l 'nvidia-driver-*' 2>/dev/null | grep '^ii' || true

echo ""
echo "Atualizando índice apt e instalando nvidia-driver-580-open (recomendado por ubuntu-drivers para RTX 3090 / Jammy)..."
set +e
apt-get update -qq
APT_UPD="$?"
set -e
if [[ "$APT_UPD" -ne 0 ]]; then
  echo ""
  echo "AVISO: apt-get update falhou (exit $APT_UPD)."
  echo "Repositórios de terceiros costumam bloquear o update — por exemplo Spotify ou Microsoft Teams (erros NO_PUBKEY / InRelease)."
  echo "Correção rápida: desativar temporariamente as listas problemáticas, por exemplo:"
  echo "  sudo mv /etc/apt/sources.list.d/spotify.list /etc/apt/sources.list.d/spotify.list.off 2>/dev/null || true"
  echo "  sudo sed -i 's/^/#/' /etc/apt/sources.list.d/microsoft-teams.list 2>/dev/null || true"
  echo "Depois: sudo apt-get update && sudo bash $0"
  echo ""
  echo "A tentar instalar o driver na mesma (usa listas APT já existentes)..."
  echo ""
fi

apt-get install -y nvidia-driver-580-open

echo ""
echo "Concluído. Reinicie o computador antes de testar CUDA/PyTorch:"
echo "  sudo reboot"
echo "Depois:"
echo "  nvidia-smi"
echo "  conda activate pdfextreme && python scripts/ingest.py"
