#!/bin/zsh
# Deploy Plainsight from this Mac to the live server: runs the tests, copies the code, installs
# the Python packages there, restarts the service and checks the public site.
#
# Normally you don't need this: merging a PR into main deploys automatically (.github/workflows/deploy.yml).
# Use it for the first deploy, after changing deploy/plainsight.service (only this script installs it),
# or if GitHub Actions is down. It copies this folder as it is, including uncommitted changes.
# Run from anywhere in the project:
#
#   deploy/deploy.sh                    # deploys to ram@jhola.ramiyer.tech (the same server as Jhola)
#   deploy/deploy.sh other@some-host    # or somewhere else
#
# The server asks once for ram's own password (for sudo), not the root password.
# Secrets stay on the server in /opt/plainsight/.env.production and are never copied.

set -euo pipefail
HOST=${1:-ram@jhola.ramiyer.tech}
SITE=https://plainsight.ramiyer.tech
cd "${0:A:h}/.."

if [[ -x .venv/bin/pytest ]]; then
  echo "→ Running tests"
  .venv/bin/pytest -q
else
  echo "→ Skipping tests (no .venv/bin/pytest in this folder)"
fi

echo "→ Copying code to $HOST"
# Into a staging folder in your home on the server first; the server then copies it into place.
rsync -az --delete \
  --include='.env.example' --exclude='.env*' --exclude='.streamlit/secrets.toml' \
  --exclude='.venv' --exclude='.git' --exclude='.claude' --exclude='data/' \
  --exclude='__pycache__' --exclude='.DS_Store' \
  ./ "$HOST:plainsight-src/"

echo "→ Installing and restarting on $HOST (sudo asks for your server user's password)"
ssh -t "$HOST" 'set -e
  sudo rsync -a --delete --include=".env.example" --exclude=".env*" --exclude=".streamlit/secrets.toml" --exclude=".venv" --exclude="__pycache__" ~/plainsight-src/ /opt/plainsight/
  sudo chown -R plainsight:plainsight /opt/plainsight
  sudo install -d -o plainsight -g plainsight -m 750 /var/lib/plainsight
  cd /opt/plainsight
  if [ ! -x .venv/bin/python ]; then sudo -u plainsight env HOME=/var/lib/plainsight python3 -m venv .venv; fi
  sudo -u plainsight env HOME=/var/lib/plainsight .venv/bin/pip install --quiet --disable-pip-version-check -r requirements.txt
  sudo cp deploy/plainsight.service /etc/systemd/system/plainsight.service
  sudo systemctl daemon-reload
  sudo systemctl enable --quiet plainsight
  sudo systemctl restart plainsight
  # Wait quietly for the app to come up (Streamlit takes a few seconds after a restart).
  for i in $(seq 1 30); do curl -fs -o /dev/null http://127.0.0.1:8501/_stcore/health && break; sleep 1; done
  curl -fsS -o /dev/null -w "→ App answered on the server: HTTP %{http_code}\n" http://127.0.0.1:8501/_stcore/health'

if [[ "$HOST" == "ram@jhola.ramiyer.tech" ]]; then
  echo "→ Checking $SITE"
  if ! curl -fsS -o /dev/null -w "→ Public site: HTTP %{http_code} in %{time_total}s\n" "$SITE/"; then
    echo "! The public site didn't answer. On the first deploy that's expected: nginx and HTTPS come next (deploy/README.md)."
  fi
fi

echo "✓ Deployed"
