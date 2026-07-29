#!/usr/bin/env bash
# ============================================================================
#  SSDASSIST — one-shot prerequisite installer for the always-on Ubuntu PC.
#  Installs the HOST tools only (git, Docker, cloudflared) and stops the PC
#  from sleeping. The app's Python libraries install themselves inside Docker.
#
#  Usage on the Ubuntu PC:
#     chmod +x setup_server.sh
#     ./setup_server.sh
#  Then LOG OUT and back in (or reboot) so Docker works without sudo.
# ============================================================================
set -e

echo ">> Updating system packages..."
sudo apt update && sudo apt -y upgrade

echo ">> Installing basics (git, curl, ca-certificates, nano)..."
sudo apt -y install git curl ca-certificates nano

if ! command -v docker >/dev/null 2>&1; then
  echo ">> Installing Docker Engine + Compose plugin..."
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER"
else
  echo ">> Docker already installed — skipping."
fi

if ! command -v cloudflared >/dev/null 2>&1; then
  echo ">> Installing cloudflared (Cloudflare Tunnel agent)..."
  curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o /tmp/cloudflared.deb
  sudo dpkg -i /tmp/cloudflared.deb
else
  echo ">> cloudflared already installed — skipping."
fi

echo ">> Disabling sleep/suspend so the PC stays always-on..."
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target || true

echo ""
echo "============================================================"
echo " Installed:"
command -v git >/dev/null && echo "   git         : $(git --version)"
command -v docker >/dev/null && echo "   docker      : $(docker --version)"
docker compose version >/dev/null 2>&1 && echo "   compose     : $(docker compose version | head -1)"
command -v cloudflared >/dev/null && echo "   cloudflared : $(cloudflared --version 2>/dev/null | head -1)"
echo ""
echo " NEXT: LOG OUT and back in (or reboot) so Docker runs without sudo,"
echo "       then follow SELF_HOSTING_GUIDE.md from Part C."
echo "============================================================"
