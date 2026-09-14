#!/usr/bin/env bash
# Restore the /opt/dominion/deer-flow checkout to the clean pre-build state
# that scripts/deploy_deerflow_runtime_remote.sh requires at line 40
# (`git diff --quiet`) before it will start a Docker build.
#
# WHY THIS IS NEEDED: the deploy script temporarily patches exactly two
# tracked upstream files during build preparation --
#   backend/Dockerfile    (APT_HTTPS_PATCHED)
#   backend/pyproject.toml (OLLAMA_DEP_PATCHED)
# -- and restores them from an EXIT trap. The disk-full interruption killed
# the run before that trap could complete, so one or both stayed modified
# and every later run now dies in under a second on the clean-state check.
#
# AUTHORIZED SCOPE: `git checkout --` of those two paths and nothing else.
#
# NEVER, in any mode: git reset, git clean, git checkout of a directory or
# of '.', any force checkout, any branch change, any fetch/pull/clone, any
# deletion of untracked files, any Docker or deployment action. The workflow
# gate greps this file for those before it is allowed to run.
#
# If ANY tracked file outside those two paths is modified, this stops and
# reports it rather than overwriting it -- an unexpected tracked change is
# somebody's work or an unknown defect, and either way it is not this
# lane's to discard.
#
# Two modes:
#   inspect  (default, read-only) -- Step 1 and Step 2 classification only.
#   repair   -- restores the two sanctioned paths, then re-proves Step 3.
set -uo pipefail

MODE="${1:-inspect}"

DEERFLOW_ROOT="${DEERFLOW_ROOT:-/opt/dominion/deer-flow}"
EXPECTED_ORIGIN="https://github.com/bytedance/deer-flow.git"
EXPECTED_TAG="v2.0.0"
# The only two paths this lane may ever restore.
SANCTIONED_1="backend/Dockerfile"
SANCTIONED_2="backend/pyproject.toml"

say()   { printf '%s\n' "$*"; }
head2() { printf '\n== %s ==\n' "$*"; }
die()   { say ""; say "RESULT=STOP reason=$*"; say "DEERFLOW_PREBUILD_RECOVERY_END"; exit 3; }

say "DEERFLOW_PREBUILD_RECOVERY_BEGIN"
say "collected_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
say "hostname=$(hostname 2>/dev/null || echo UNKNOWN)"
say "mode=$MODE"
say "deerflow_root=$DEERFLOW_ROOT"

[ -d "$DEERFLOW_ROOT/.git" ] || die "$DEERFLOW_ROOT is not a git working tree"
cd "$DEERFLOW_ROOT" || die "cannot enter $DEERFLOW_ROOT"

# ══ STEP 1 — inspect only ══════════════════════════════════════════════
head2 "STEP 1: REMOTE"
git remote -v 2>&1 | sed 's/^/    /'
ORIGIN="$(git remote get-url origin 2>/dev/null)"
say "  origin=$ORIGIN"
say "  expected_origin=$EXPECTED_ORIGIN"

head2 "STEP 1: STATUS"
git status --short 2>&1 | sed 's/^/    /'

head2 "STEP 1: DIFF backend/Dockerfile"
git diff -- "$SANCTIONED_1" 2>&1 | sed 's/^/    /' | head -60

head2 "STEP 1: DIFF backend/pyproject.toml"
git diff -- "$SANCTIONED_2" 2>&1 | sed 's/^/    /' | head -60

head2 "STEP 1: STAGED DIFF"
git diff --cached 2>&1 | sed 's/^/    /' | head -60

head2 "STEP 1: HEAD AND TAG"
HEAD_SHA="$(git rev-parse HEAD 2>/dev/null)"
HEAD_TAG="$(git describe --tags --exact-match HEAD 2>/dev/null || true)"
say "  head_sha=$HEAD_SHA"
say "  head_tag=${HEAD_TAG:-<none>}"
say "  expected_tag=$EXPECTED_TAG"

# ══ STEP 2 — classify dirty state ══════════════════════════════════════
# Uses git plumbing rather than parsing porcelain: `git diff --name-only`
# and `--cached --name-only` are exactly the two conditions the deploy
# script's clean-state check tests, so what is classified here is precisely
# what is blocking it.
head2 "STEP 2: CLASSIFY DIRTY STATE"
UNSTAGED="$(git diff --name-only 2>/dev/null | sort -u)"
STAGED="$(git diff --cached --name-only 2>/dev/null | sort -u)"
TRACKED_DIRTY="$(printf '%s\n%s\n' "$UNSTAGED" "$STAGED" | grep -v '^$' | sort -u)"
UNTRACKED="$(git ls-files --others --exclude-standard 2>/dev/null | sort -u)"

say "  -- tracked, modified in working tree --"
printf '%s\n' "${UNSTAGED:-<none>}" | sed 's/^/    /'
say "  -- tracked, staged --"
printf '%s\n' "${STAGED:-<none>}" | sed 's/^/    /'
say "  -- untracked (never touched by this lane) --"
printf '%s\n' "${UNTRACKED:-<none>}" | sed 's/^/    /'

if [ -z "$TRACKED_DIRTY" ]; then
  say ""
  say "  classification=ALREADY_CLEAN (no tracked modification)"
  UNEXPECTED=""
else
  # Anything dirty that is not one of the two sanctioned paths.
  UNEXPECTED="$(printf '%s\n' "$TRACKED_DIRTY" \
    | grep -vxF "$SANCTIONED_1" | grep -vxF "$SANCTIONED_2" || true)"
  if [ -n "$UNEXPECTED" ]; then
    say ""
    say "  classification=UNEXPECTED_TRACKED_CHANGES"
    say "  the following tracked files are modified but are NOT sanctioned"
    say "  build-preparation files, so this lane will not overwrite them:"
    printf '%s\n' "$UNEXPECTED" | sed 's/^/      /'
  else
    say ""
    say "  classification=SANCTIONED_BUILD_PREP_ONLY"
    say "  every tracked modification is one of the two files the deploy"
    say "  script patches and restores from its EXIT trap."
  fi
fi

if [ "$MODE" != "repair" ]; then
  say ""
  say "RESULT=INSPECTED_NOT_REPAIRED"
  say "ACTION_TAKEN=NONE (inspect mode)"
  say "DEERFLOW_PREBUILD_RECOVERY_END"
  exit 0
fi

# ══════════════════════════ REPAIR MODE ════════════════════════════════

# Identity gates first. A checkout that is not the pinned upstream one is
# not the thing this lane was written for.
[ "$ORIGIN" = "$EXPECTED_ORIGIN" ] \
  || die "origin is '$ORIGIN', expected '$EXPECTED_ORIGIN'"
[ "$HEAD_TAG" = "$EXPECTED_TAG" ] \
  || die "HEAD is at tag '${HEAD_TAG:-<none>}', expected '$EXPECTED_TAG'"

# The hard refusal the directive requires.
[ -z "$UNEXPECTED" ] \
  || die "tracked files outside the two sanctioned paths are modified; refusing to overwrite them"

if [ -z "$TRACKED_DIRTY" ]; then
  say ""
  say "  nothing to restore -- the checkout is already clean"
else
  head2 "REPAIR: RESTORE SANCTIONED PATHS ONLY"
  # Named explicitly, one path each. Never a directory, never '.', never
  # a force flag, so nothing outside these two files can be affected.
  for f in "$SANCTIONED_1" "$SANCTIONED_2"; do
    if printf '%s\n' "$TRACKED_DIRTY" | grep -qxF "$f"; then
      say "  restoring $f"
      git checkout -- "$f" 2>&1 | sed 's/^/    /'
    else
      say "  $f already clean, not touched"
    fi
  done
fi

# ══ STEP 3 — prove clean state ═════════════════════════════════════════
head2 "STEP 3: PROVE CLEAN STATE"
say "  -- git status --short --"
git status --short 2>&1 | sed 's/^/    /'

fails=0
if git diff --quiet 2>/dev/null; then
  say "  check_no_worktree_diff=PASS"
else
  say "  check_no_worktree_diff=FAIL"; fails=$((fails + 1))
fi
if git diff --cached --quiet 2>/dev/null; then
  say "  check_no_staged_diff=PASS"
else
  say "  check_no_staged_diff=FAIL"; fails=$((fails + 1))
fi

FINAL_TAG="$(git describe --tags --exact-match HEAD 2>/dev/null || true)"
if [ "$FINAL_TAG" = "$EXPECTED_TAG" ]; then
  say "  check_exact_tag=PASS ($FINAL_TAG)"
else
  say "  check_exact_tag=FAIL (${FINAL_TAG:-<none>})"; fails=$((fails + 1))
fi

FINAL_ORIGIN="$(git remote get-url origin 2>/dev/null)"
if [ "$FINAL_ORIGIN" = "$EXPECTED_ORIGIN" ]; then
  say "  check_exact_origin=PASS"
else
  say "  check_exact_origin=FAIL ($FINAL_ORIGIN)"; fails=$((fails + 1))
fi

say "  final_head_sha=$(git rev-parse HEAD 2>/dev/null)"

# Untracked files are reported for the record but were never touched; they
# do not affect the tracked clean-state checks the deploy script runs.
say ""
say "  -- untracked after repair (unchanged, informational) --"
git ls-files --others --exclude-standard 2>/dev/null | sed 's/^/    /' \
  || say "    <none>"

if [ "$fails" -ne 0 ]; then
  die "$fails clean-state check(s) failed after repair"
fi

say ""
say "DEERFLOW_PREBUILD_STATE_RECOVERY=PASS"
say "DEERFLOW_PREBUILD_RECOVERY_END"
say "MUTATIONS_KIND=git_checkout_two_sanctioned_paths"
