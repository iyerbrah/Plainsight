# Plainsight's server

Plainsight runs at **https://plainsight.ramiyer.tech** on the Hostinger VPS that also runs Jhola (https://jhola.ramiyer.tech) and QuoteRunner (https://quoterunner.ramiyer.tech). The three sites share the machine and nginx but nothing else: each has its own user, folder, port, service, secrets and deploy key.

```
Browser ──HTTPS──▶ nginx (ports 80/443, Let's Encrypt certificate; also serves Jhola and QuoteRunner)
                     │  sets X-Real-IP, caps /api/ask per address
                     ▼
                   FastAPI (uvicorn) on 127.0.0.1:8100 (systemd service "plainsight", user "plainsight")
                     ├──▶ OpenAI API (gpt-5.4-mini)
                     └──▶ olist.duckdb in /opt/plainsight (opened read-only, ships with the code)
```

| What | Where |
| --- | --- |
| Live site | https://plainsight.ramiyer.tech |
| Server | Hostinger VPS `srv2139468`, Ubuntu, nginx 1.28, Ubuntu's own Python 3. Shared with Jhola (port 3000) and QuoteRunner (port 8000) |
| SSH login | `ram@jhola.ramiyer.tech` (the same machine); `sudo` asks for **ram's** password, not root's |
| DNS | Hostinger DNS: an A record for `plainsight` pointing at the VPS (the same IP as `jhola`), TTL 300 |
| App code | `/opt/plainsight`, owned by the `plainsight` user, which has no login and no admin rights |
| Python packages | `/opt/plainsight/.venv`, built on the server from [requirements.txt](../requirements.txt); deploys keep it and update it |
| Secrets | `/opt/plainsight/.env.production` (only on the server; deploys never copy or overwrite it) |
| App's own files | `/var/lib/plainsight`, the app's HOME and pip's cache. The only place the app can write |
| Service | `/etc/systemd/system/plainsight.service`, from [plainsight.service](plainsight.service); only `deploy/deploy.sh` installs it |
| nginx | `/etc/nginx/sites-available/plainsight`, from [nginx/plainsight.conf](nginx/plainsight.conf) plus certbot's HTTPS lines |
| Certificate | Let's Encrypt, its own certificate for `plainsight.ramiyer.tech`, renews itself |
| Logs | `sudo journalctl -u plainsight` |
| Health check | `curl -s http://127.0.0.1:8100/healthz` on the server prints `{"status":"ok"}` (no model call) |
| Deploys | GitHub Actions ([.github/workflows/deploy.yml](../.github/workflows/deploy.yml)) after CI passes on `main` |
| Deploy user | `plainsight-deploy`: no password; its one SSH key can only run `/usr/local/sbin/plainsight-deploy` (from [server/plainsight-deploy](server/plainsight-deploy)). Jhola's `deploy` user is separate and untouched |
| Deploy state | `/var/lib/plainsight-deploy`: a clone of the repo, `current` (the live commit) and `history` (every deploy) |
| Staging copy | `~/plainsight-src` in ram's home (only the manual `deploy/deploy.sh` uses it) |

## Day to day

### Ship a change

Merge a pull request into `main`. CI runs on `main` again, and when it passes the **Deploy** workflow:

1. connects to the server as `plainsight-deploy` (the server's host key is pinned, so it can't be fooled into talking to another machine);
2. runs `plainsight-deploy <commit>`, which fetches that commit from GitHub, refuses anything that isn't on `main`, copies it into `/opt/plainsight` (never touching the secrets file or `.venv`), installs the Python packages as the `plainsight` user, restarts the app and waits for `/healthz` to answer;
3. checks the public site answers.

Follow it under **Actions → Deploy** on GitHub; each run also shows up under **Deployments** on the repo page. A deploy takes under a minute, and the site is down only for the second or two of the restart. A restart also clears the answer cache and the question counts, which live in the app's memory.

To see which commit is live, on the server:

```bash
cat /var/lib/plainsight-deploy/current
```

### Roll back

On GitHub, open **Actions → Deploy → Run workflow**, paste the full SHA of an earlier commit on `main` (from `git log` or the commits page) and run it. Leaving the box empty redeploys the latest `main`. On the server, `cat /var/lib/plainsight-deploy/history` lists every deploy with its time.

The same works on the server by hand:

```bash
sudo /usr/local/sbin/plainsight-deploy <commit SHA>
```

### Deploy by hand from the Mac

`deploy/deploy.sh` is needed in three cases: the first deploy, after changing [plainsight.service](plainsight.service) (only this script installs it), and if GitHub Actions is down. It copies the code from your Mac, including uncommitted changes, so otherwise prefer merging a PR. It never copies `.env`, so your local key stays on your Mac.

```bash
deploy/deploy.sh
```

It runs the tests, copies the code, installs the Python packages on the server, installs the service file, then restarts the app. The server asks once for ram's password.

### Change the deploy script itself

Deploys never update `/usr/local/sbin/plainsight-deploy`, the service file or nginx, so a merged PR can't give itself more access to the server. After changing [server/plainsight-deploy](server/plainsight-deploy), install it by hand, from the project folder on your Mac:

```bash
scp deploy/server/plainsight-deploy deploy/server/setup-github-deploy.sh ~/.ssh/plainsight_deploy.pub ram@jhola.ramiyer.tech:
```

```bash
ssh -t ram@jhola.ramiyer.tech 'sudo bash setup-github-deploy.sh plainsight_deploy.pub'
```

Jhola's setup script has the same name, `setup-github-deploy.sh`, so the copy in ram's home is whichever was copied last. That's fine as long as you copy and run them together like this.

### Apply an nginx change

Deploys never change nginx, so a change to [nginx/plainsight.conf](nginx/plainsight.conf) has to be copied into the live file by hand. The live file also has certbot's HTTPS lines, so edit it rather than replacing it:

```bash
sudo nano /etc/nginx/sites-available/plainsight
```

Make the same change there: `limit_req_zone` lines go at the top, outside any `server` block, and a `location` block goes inside the `server` block that has `listen 443`. Save with Ctrl+O, Enter, Ctrl+X, then check and reload:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

`nginx -t` must say `syntax is ok` and `test is successful` before the reload; if it doesn't, every site keeps running on the old config. Fix the file and try again. nginx is shared with Jhola and QuoteRunner, so a mistake here can take them down too: always run `nginx -t` first.

### Watch the logs

```bash
sudo journalctl -u plainsight -f
```

Each request logs one line. A question the app couldn't answer logs `Couldn't answer` with the reason underneath (a bad key, a quota, a timeout). Ctrl+C stops watching.

### Change a secret or setting

```bash
sudo -u plainsight nano /opt/plainsight/.env.production
```

Save with Ctrl+O, Enter, Ctrl+X, then:

```bash
sudo systemctl restart plainsight
```

The file holds `LLM_PROVIDER`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `REASONING_EFFORT`, `RATE_LIMIT_PER_HOUR` and `DAILY_QUESTION_CAP`. Values go without quote marks. [.env.example](../.env.example) explains each one.

### Rotate the OpenAI key

Create the new key first (in the Plainsight project on platform.openai.com), put it in the secrets file, restart, check a question gets answered, then revoke the old key.

### Other checks

| To | Run (on the server) |
| --- | --- |
| See if the app is running | `systemctl status plainsight` |
| Ask the app if it's healthy | `curl -s http://127.0.0.1:8100/healthz` |
| Test certificate renewal | `sudo certbot renew --dry-run` (covers the other sites' certificates too) |
| See the certificates' expiry | `sudo certbot certificates` |
| Install Ubuntu updates | `sudo apt update && sudo apt upgrade`, then `sudo systemctl restart plainsight jhola quoterunner` |
| Rebuild the Python packages from scratch | `sudo rm -rf /opt/plainsight/.venv`, then `deploy/deploy.sh` from your Mac |

After an Ubuntu upgrade that changes the Python version (e.g. 3.12 to 3.13), the old `.venv` stops working; rebuild it as in the last row.

## Setting up from scratch

These are the steps that set up the current server. Jhola was there first, so nginx, certbot, rsync and the firewall were already in place; on a brand new server, do steps 2 and 3 of Jhola's `deploy/README.md` first (install rsync, certbot and python3-certbot-nginx; open the firewall for SSH and the web). Commands run on the server unless they say "on your Mac".

### 1. Point the domain at the server

Find the VPS's IP, which Jhola already points at. On your Mac:

```bash
dig +short jhola.ramiyer.tech
```

In Hostinger, open **Domains → ramiyer.tech → DNS / Nameservers** and add:

| Type | Name | Points to | TTL |
| --- | --- | --- | --- |
| A | `plainsight` | the IP that `dig` just printed | 300 |

Delete any other A or AAAA records for `plainsight` (Hostinger's parking records), or some visitors reach the wrong server. Only add an AAAA record if the VPS has IPv6.

Check it. It must print the same IP:

```bash
dig +short plainsight.ramiyer.tech
```

### 2. Check Python and the port

```bash
python3 --version
```

It must say 3.11 or newer. Then install the tool that makes Python environments (Ubuntu leaves it out; QuoteRunner's setup may already have installed it, which is fine):

```bash
sudo apt-get install -y python3-venv
```

Check nothing else is using port 8100. This must print nothing:

```bash
sudo ss -ltnp | grep ':8100'
```

### 3. Create the app user and folder

```bash
sudo useradd --system --home-dir /var/lib/plainsight --create-home --shell /usr/sbin/nologin plainsight
```

```bash
sudo mkdir -p /opt/plainsight && sudo chown plainsight:plainsight /opt/plainsight
```

### 4. Add the secrets

```bash
sudo -u plainsight nano /opt/plainsight/.env.production
```

```
LLM_PROVIDER=openrouter
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.4-mini
OPENROUTER_API_KEY=
OPENROUTER_MODEL=nvidia/nemotron-3.5-super-vl:free
REASONING_EFFORT=low
RATE_LIMIT_PER_HOUR=20
DAILY_QUESTION_CAP=300
```

Paste the key for the provider in `LLM_PROVIDER` after its `=` sign (`OPENROUTER_API_KEY` or `OPENAI_API_KEY`), with no quote marks. Use Plainsight's own key, not Jhola's or QuoteRunner's, so the sites' spend and limits stay apart. Then lock the file down:

```bash
sudo chmod 600 /opt/plainsight/.env.production
```

### 5. First deploy (on your Mac)

From the project folder:

```bash
deploy/deploy.sh
```

It should end with `→ App answered on the server: HTTP 200`, then say the public site didn't answer: that's expected until the next two steps are done.

### 6. Put nginx in front

```bash
sudo cp /opt/plainsight/deploy/nginx/plainsight.conf /etc/nginx/sites-available/plainsight
```

```bash
sudo ln -s /etc/nginx/sites-available/plainsight /etc/nginx/sites-enabled/plainsight
```

Don't remove anything else from `sites-enabled`: Jhola's and QuoteRunner's sites are there and live.

```bash
sudo nginx -t && sudo systemctl reload nginx
```

`nginx -t` should say `syntax is ok` and `test is successful`. `http://plainsight.ramiyer.tech` should then show Plainsight, without the padlock yet.

### 7. Turn on HTTPS

```bash
sudo certbot --nginx -d plainsight.ramiyer.tech --redirect
```

It should end with "Successfully deployed certificate". It doesn't touch the other sites' certificates. `https://plainsight.ramiyer.tech` should now show Plainsight with the padlock, and an example question should get an answer. Then test renewal:

```bash
sudo certbot renew --dry-run
```

### 8. Let GitHub deploy

All on your Mac, from the project folder. Make a key just for GitHub (no passphrase, since a robot uses it). It's a different key from Jhola's:

```bash
ssh-keygen -t ed25519 -N "" -C "github-actions-plainsight-deploy" -f ~/.ssh/plainsight_deploy
```

Copy the setup files and the public key to the server, then run the setup (it asks for ram's password twice: once to log in, once for sudo). It creates its own `plainsight-deploy` user and leaves Jhola's `deploy` user alone:

```bash
scp deploy/server/plainsight-deploy deploy/server/setup-github-deploy.sh ~/.ssh/plainsight_deploy.pub ram@jhola.ramiyer.tech:
```

```bash
ssh -t ram@jhola.ramiyer.tech 'sudo bash setup-github-deploy.sh plainsight_deploy.pub'
```

It ends with `✓ GitHub deploy access is set up`. Test the key by deploying the latest `main` with it. This is a real deploy, ending with `✓ Deployed` and the commit:

```bash
git fetch origin && ssh -i ~/.ssh/plainsight_deploy -o IdentitiesOnly=yes plainsight-deploy@plainsight.ramiyer.tech "$(git rev-parse origin/main)"
```

The first time, SSH asks you to confirm the fingerprint of `plainsight.ramiyer.tech`. It's the same machine as Jhola, so it must be Jhola's: `SHA256:9W6wUY9u/Vz2AgOMXvGUT4WYyrr/fQJkbK0MglgeUCI`. Type `yes` only if it matches.

Then give GitHub the private key and the server's host key:

```bash
gh secret set DEPLOY_SSH_KEY --repo iyerbrah/Plainsight < ~/.ssh/plainsight_deploy
```

```bash
ssh-keyscan -t ed25519 plainsight.ramiyer.tech 2>/dev/null | gh variable set DEPLOY_KNOWN_HOSTS --repo iyerbrah/Plainsight
```

Check the host key's fingerprint is Jhola's too:

```bash
ssh-keyscan -t ed25519 plainsight.ramiyer.tech 2>/dev/null | ssh-keygen -lf -
```

### 9. Cap the OpenAI spend

On platform.openai.com, open the **Plainsight** project's limits page and set a monthly budget with an email alert. One question costs about $0.0015, so the site's own cap of 300 questions a day comes to under $15 a month; a $15 budget covers that and stops anything that gets past the app's limits.

## If something goes wrong

| What you see | Cause and fix |
| --- | --- |
| nginx shows "502 Bad Gateway" | The app isn't running. `systemctl status plainsight` and `sudo journalctl -u plainsight -n 50` show why: usually a missing package (rerun `deploy/deploy.sh`) or a mistake in the secrets file. |
| Every question says "The model could not be reached" | The logs under `Couldn't answer` say why: `OPENAI_API_KEY isn't set` (the secrets file is missing the key, or the service wasn't restarted after adding it), a wrong or revoked key, or the project's budget or quota ran out. |
| The page loads but looks unstyled | `/static/` isn't reaching the app. `curl -sI https://plainsight.ramiyer.tech/static/style.css` should say `200`; if not, check the `location /static/` block in the live nginx file. |
| Logs say `Read-only file system` or `Permission denied` for a path | Something in the app tried to write outside `/var/lib/plainsight`, which the service forbids. Check the service still has `Environment=HOME=/var/lib/plainsight`; anything else the app writes must go under that folder. |
| `address already in use` in the logs | Another program has port 8100. `sudo ss -ltnp \| grep ':8100'` shows which. Pick a free port and change it in the service file, the nginx file and the two deploy scripts' health checks. |
| `The virtual environment was not created successfully because ensurepip is not available` | `python3-venv` is missing: `sudo apt-get install -y python3-venv`, then `sudo rm -rf /opt/plainsight/.venv` and deploy again. |
| `.venv/bin/python: No such file or directory` or `bad interpreter` after an Ubuntu upgrade | The Python version changed under the old environment. `sudo rm -rf /opt/plainsight/.venv`, then `deploy/deploy.sh`. |
| Every visitor hits the question limit quickly | The app sees everyone as one address. The nginx file must keep its `X-Real-IP $remote_addr` line. |
| Visitors get "Too many requests" (429) without asking much | nginx's backstop caught them. The limits are at the top of the nginx file; raise them there, then `sudo nginx -t && sudo systemctl reload nginx`. |
| `https://plainsight.ramiyer.tech` shows another site, or a certificate warning | Either the nginx site isn't enabled (step 6) or HTTPS isn't set up yet (step 7). `ls /etc/nginx/sites-enabled` should list `plainsight` next to the others. |
| certbot: `Invalid Location header` or an IP that isn't the VPS | `plainsight.ramiyer.tech` doesn't point at this server yet. Check `dig +short plainsight.ramiyer.tech` and wait for DNS. Five failed tries block the name for an hour. |
| `sudo: Authentication failed` | It wants ram's password, not root's. |
| Deploy workflow: `DEPLOY_SSH_KEY secret or DEPLOY_KNOWN_HOSTS variable is missing` | Step 8's two `gh` commands weren't run, or were run for another repo. `gh secret list --repo iyerbrah/Plainsight` and `gh variable list --repo iyerbrah/Plainsight` should show them. |
| Deploy workflow: `Host key verification failed` | The server's host key changed (e.g. the VPS was rebuilt). Check the new fingerprint on the server with `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`, then rerun the `ssh-keyscan … \| gh variable set` command. Jhola's variable needs the same update. |
| Deploy workflow: `Permission denied (publickey)` | The key in the secret doesn't match `/home/plainsight-deploy/.ssh/authorized_keys`. Rerun the setup with `~/.ssh/plainsight_deploy.pub`, then `gh secret set` again. |
| Deploy workflow: `sudo: a password is required` | The sudo rule is missing. Rerun the setup script; it checks the rule and says if sudo rejected it. |
| Deploy workflow: `isn't on main` | Only commits on `main` can be deployed. Merge the PR first, or pick a SHA from `main`'s history. |
| Deploy workflow: `Repository not found` while fetching | The server clones `https://github.com/iyerbrah/Plainsight.git`. The repo must have that name and be public. |
| Deploy workflow: `The app didn't come back after the restart` | The log lines it prints say why. Most often a package failed to install or the app crashed at start; `sudo journalctl -u plainsight -n 50` on the server shows more. |
