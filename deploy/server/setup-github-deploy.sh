#!/bin/bash
# One-time setup that lets GitHub Actions deploy Plainsight. Run on the server as root:
#
#   sudo bash setup-github-deploy.sh plainsight_deploy.pub
#
# where plainsight_deploy.pub is the public half of the key GitHub will use. It:
#   1. installs git if it's missing;
#   2. installs plainsight-deploy (from the same folder as this script) to /usr/local/sbin, owned by root;
#   3. creates a "plainsight-deploy" user with no password, whose only SSH key can run nothing
#      but plainsight-deploy;
#   4. lets "plainsight-deploy" run exactly that one script as root without a password.
#
# It uses its own user on purpose. Jhola's setup script writes the "deploy" user's
# authorized_keys from scratch, so sharing that user would break one site's deploys whenever
# the other's key is set. This script never touches the "deploy" user or Jhola's sudo rule.
#
# Safe to run again, e.g. to install a newer plainsight-deploy or replace the key.

set -euo pipefail

DEPLOY_USER=plainsight-deploy
SCRIPT=/usr/local/sbin/plainsight-deploy

if [[ $(id -u) -ne 0 ]]; then
  echo "Run this with sudo: sudo bash $0 <public key file>" >&2
  exit 1
fi
PUBKEY_FILE=${1:-}
if [[ -z $PUBKEY_FILE || ! -f $PUBKEY_FILE ]]; then
  echo "Usage: sudo bash $0 <public key file, e.g. plainsight_deploy.pub>" >&2
  exit 1
fi
PUBKEY=$(head -n 1 "$PUBKEY_FILE")
if [[ ! $PUBKEY =~ ^ssh-ed25519\ [A-Za-z0-9+/=]+(\ .*)?$ ]]; then
  echo "$PUBKEY_FILE doesn't look like an ed25519 public key (it should start with ssh-ed25519)." >&2
  exit 1
fi
HERE=$(cd "$(dirname "$0")" && pwd)

echo "→ Checking tools"
if ! command -v git > /dev/null; then
  apt-get install -y git
fi

echo "→ Installing $SCRIPT"
install -o root -g root -m 755 "$HERE/plainsight-deploy" "$SCRIPT"

echo "→ Creating the $DEPLOY_USER user"
if ! id "$DEPLOY_USER" > /dev/null 2>&1; then
  # /bin/sh (not nologin) because sshd runs the forced command below through the user's shell.
  useradd --system --create-home --home-dir "/home/$DEPLOY_USER" --shell /bin/sh "$DEPLOY_USER"
fi
passwd -l "$DEPLOY_USER" > /dev/null # no password login, ever

# The key can only run plainsight-deploy, with the commit SHA GitHub sends as its one argument
# ($SSH_ORIGINAL_COMMAND is passed as a single quoted word and checked by the script).
# "restrict" turns off terminals, port forwarding and agent forwarding.
# root owns the file, so the deploy user can't change its own key.
install -d -o root -g root -m 755 "/home/$DEPLOY_USER/.ssh"
# shellcheck disable=SC2016 # $SSH_ORIGINAL_COMMAND is for sshd to fill in, not this script
printf 'restrict,command="sudo -n %s \\"$SSH_ORIGINAL_COMMAND\\"" %s\n' "$SCRIPT" "$PUBKEY" \
  > "/home/$DEPLOY_USER/.ssh/authorized_keys"
chown root:root "/home/$DEPLOY_USER/.ssh/authorized_keys"
chmod 644 "/home/$DEPLOY_USER/.ssh/authorized_keys"

echo "→ Allowing $DEPLOY_USER to run plainsight-deploy (and nothing else) as root"
RULE=/etc/sudoers.d/plainsight-deploy
printf '%s ALL=(root) NOPASSWD: %s\n' "$DEPLOY_USER" "$SCRIPT" > "$RULE"
chmod 440 "$RULE"
# A broken sudoers file can lock everyone out of sudo, so check it and remove it if anything's off.
if command -v visudo > /dev/null && ! visudo -cf "$RULE" > /dev/null; then
  rm -f "$RULE"
  echo "The sudo rule didn't pass visudo's check, so it was removed. Nothing else changed in sudo." >&2
  exit 1
fi
if ! sudo -l -U "$DEPLOY_USER" 2>/dev/null | grep -q "$SCRIPT"; then
  rm -f "$RULE"
  echo "sudo didn't accept the rule, so it was removed. Nothing else changed in sudo." >&2
  exit 1
fi

echo "✓ GitHub deploy access is set up. Test it from your Mac with the private key."
