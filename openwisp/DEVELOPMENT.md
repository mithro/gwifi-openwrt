# Developing the OpenWISP controller deployment

## Source of truth

**This directory (`gwifi-openwrt/openwisp/`) is the single source of truth** for
the OpenWISP controller deployment. Everything — playbook, templates, validators,
provisioning scripts, docs — lives here under version control.

For convenience the historical path `/home/tim/local/gwifi/openwisp` is a
**symlink** to this directory, so older absolute references keep working. Don't
edit "two copies": there is only one real directory (here).

## Secrets (never committed)

Two `0600` files hold live secrets and are **git-ignored** (see `.gitignore`):

| File | Contents |
|------|----------|
| `.admin-credentials` | OpenWISP admin password for `wisp.welland.mithis.com` |
| `.wifi-secrets`      | generated 802.11s/batman mesh key |

They exist **only in the primary checkout** (`gwifi-openwrt/`, on `main`) — that
is the machine you deploy from. They are untracked, so they persist across branch
switches but never appear in a worktree you create for a feature branch (a fresh
checkout has no untracked files). Deploy from the primary checkout; develop in
worktrees.

## Workflow: branches in worktrees, merge via PR

`main` is the trunk and is **only advanced by merged PRs** — never push to it
directly. Do each piece of work on a feature branch in its own git worktree:

```sh
cd ~/local/gwifi/gwifi-openwrt

# 1. New isolated workspace + branch off main (.worktrees/ is git-ignored)
git worktree add .worktrees/<topic> -b openwisp-<topic> main
cd .worktrees/<topic>/openwisp

# 2. Make small, focused commits. Validate the firmware map offline:
uv run --with pyyaml python validate-firmware-images.py
#    (point GWIFI_OPENWRT at the OpenWrt build tree if it isn't auto-found)

# 3. Push the branch and open a PR
git push -u origin openwisp-<topic>
gh pr create --base main --head openwisp-<topic>

# 4. After the PR merges, sync main and remove the worktree
cd ~/local/gwifi/gwifi-openwrt && git checkout main && git pull
git worktree remove .worktrees/<topic>
```

This repo already uses worktrees for other tracks (e.g. `.worktrees/renode-equiv`).
See the using-git-worktrees skill for the directory-selection / ignore-check rules.

## Deploying a merged change

Deploy runs Ansible **on the wisp VM against itself** (see `README.md` §5/§7).
From the primary checkout (which has the secrets):

```sh
# sync this dir to the box, then run the playbook there
rsync -a --exclude .worktrees ./ wisp.welland.mithis.com:~/openwisp/   # or scp the changed files
ssh wisp.welland.mithis.com 'cd ~/openwisp && ansible-playbook -i inventory playbook.yml'
```

Device pre-provisioning (idempotent, reads MACs from ten64 at runtime):

```sh
uv run python provision-openmesh.py            # dry-run
uv run python provision-openmesh.py --apply    # create/update devices on wisp
```

## What lives here

See `README.md` §4 for the file-by-file table.
