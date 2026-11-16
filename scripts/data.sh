#!/usr/bin/env bash
# Manage the `data` branch (drafts, state, post images) used by the bot.
#   scripts/data.sh pull   -> clone/create the data branch into ./data
#   scripts/data.sh push   -> commit and push ./data (retries on conflicts)
set -euo pipefail
BRANCH="${TM_DATA_BRANCH:-data}"
URL="https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"

case "${1:-}" in
  pull)
    if git clone --quiet --depth 20 --branch "$BRANCH" "$URL" data 2>/dev/null; then
      echo "data branch checked out"
    else
      echo "data branch not found - creating it"
      mkdir -p data && cd data
      git init --quiet -b "$BRANCH"
      git remote add origin "$URL"
      echo "# Bot state and post images. Managed automatically - do not edit by hand." > README.md
    fi
    ;;
  push)
    cd data
    git config user.name "ticker-market-bot"
    git config user.email "bot@users.noreply.github.com"
    git add -A
    if git diff --cached --quiet; then echo "nothing to save"; exit 0; fi
    git commit --quiet -m "bot: ${TM_JOB:-update} $(date -u +%FT%TZ)"
    for i in 1 2 3 4 5; do
      git pull --quiet --rebase origin "$BRANCH" 2>/dev/null || true
      if git push --quiet origin "HEAD:$BRANCH"; then echo "saved"; exit 0; fi
      sleep $((i * 3))
    done
    echo "push failed after retries" >&2; exit 1
    ;;
  *) echo "usage: $0 pull|push"; exit 2 ;;
esac
