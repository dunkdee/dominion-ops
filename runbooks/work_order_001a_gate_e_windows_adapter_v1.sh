#!/usr/bin/env bash
set -euo pipefail

# Work Order 001A — Gate E Windows OpenSSH adapter v1
# Runs the exact sibling Gate E v1 script while narrowly replacing only its
# two `gcloud compute ssh ... --command="bash -s"` calls. File transfers remain
# normal `gcloud compute scp` calls. This adapter does not disable host-key
# checking, create a PATH shim, extract archives, delete data, or continue to
# Gate F.

EXPECTED_GATE_E_NAME=work_order_001a_gate_e_v1.sh
EXPECTED_REMOTE=malachisingleton8@foundation-vm
EXPECTED_ZONE=us-central1-a
EXPECTED_PROJECT=dominion-ascendant
SSH_TARGET=malachisingleton8@34.135.158.163
SSH_KEY=/c/Users/Dell/.ssh/google_compute_engine
SSH_BIN=/usr/bin/ssh

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
GATE_E_SCRIPT="$SCRIPT_DIR/$EXPECTED_GATE_E_NAME"

[ -f "$GATE_E_SCRIPT" ] && [ ! -L "$GATE_E_SCRIPT" ] || {
  echo "BLOCKED: exact sibling Gate E script missing or unsafe: $GATE_E_SCRIPT"
  exit 170
}
[ -x "$SSH_BIN" ] || {
  echo "BLOCKED: OpenSSH binary unavailable: $SSH_BIN"
  exit 171
}
[ -f "$SSH_KEY" ] && [ ! -L "$SSH_KEY" ] || {
  echo "BLOCKED: Google Compute OpenSSH key missing or unsafe: $SSH_KEY"
  exit 172
}

REAL_GCLOUD=$(type -P gcloud || true)
[ -n "$REAL_GCLOUD" ] && [ -x "$REAL_GCLOUD" ] || {
  echo 'BLOCKED: real gcloud executable unavailable'
  exit 173
}

# Intercept only the exact seven-argument SSH invocation emitted by Gate E v1.
# Every other gcloud call, including all four exact SCP calls, is passed through
# unchanged to the real executable discovered before this function existed.
gcloud() {
  if [ "$#" -eq 7 ] \
    && [ "$1" = compute ] \
    && [ "$2" = ssh ] \
    && [ "$3" = "$EXPECTED_REMOTE" ] \
    && [ "$4" = "--zone=$EXPECTED_ZONE" ] \
    && [ "$5" = "--project=$EXPECTED_PROJECT" ] \
    && [ "$6" = --quiet ] \
    && [ "$7" = '--command=bash -s' ]; then
    "$SSH_BIN" \
      -i "$SSH_KEY" \
      -o BatchMode=yes \
      -o IdentitiesOnly=yes \
      -o StrictHostKeyChecking=yes \
      -T \
      "$SSH_TARGET" \
      'bash -s'
    return
  fi

  "$REAL_GCLOUD" "$@"
}

printf '%s\n' '=== WORK ORDER 001A GATE E WINDOWS ADAPTER V1 ==='
printf 'gate_e_script=%s\n' "$GATE_E_SCRIPT"
printf 'ssh_binary=%s\n' "$SSH_BIN"
printf 'ssh_target=%s\n' "$SSH_TARGET"
printf 'strict_host_key_checking=yes\n'

# Source rather than spawn so Gate E resolves the narrowly scoped gcloud
# function above. Gate E's own set -euo pipefail, validations, trap, and hard
# stop remain in force.
# shellcheck source=work_order_001a_gate_e_v1.sh
source "$GATE_E_SCRIPT"
