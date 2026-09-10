#!/usr/bin/env bash
# Exercise the real remediation script against stubbed system commands.
# Uses a non-existent pid (999999) so that if a guard ever failed to stop
# execution, the kill would be visibly harmless rather than hitting a real process.
SCRIPT=/home/user/dominion-ops/scripts/remediation/remove_stray_ollama_11435.sh
GOOD_SHA=c05cece87b2e85a525ccf9548d329197b938e58daa46d4fad59e8dab54e8d57d
PID=999999

scenario() { # name mode ss_out exe sha cmd cgroup gov_cgroup gov_http nem_active expect_rc expect_str
  local name=$1 mode=$2; shift 2
  local ssout=$1 exe=$2 sha=$3 cmd=$4 cg=$5 govcg=$6 govhttp=$7 nem=$8 erc=$9 estr=${10}
  local d; d=$(mktemp -d)
  mkdir -p "$d/bin" "$d/proc/$PID" "$d/proc/441"
  printf '%s' "$cmd" | tr ' ' '\0' > "$d/proc/$PID/cmdline"
  printf '%s\n' "$cg" > "$d/proc/$PID/cgroup"
  printf '%s\n' "$govcg" > "$d/proc/441/cgroup"

  cat > "$d/bin/ss" <<EOF
#!/usr/bin/env bash
case "\$*" in
  *11435*) printf '%s\n' '$ssout' ;;
  *11434*) [ -n '$govcg' ] && printf '%s\n' 'LISTEN 0 4096 127.0.0.1:11434 0.0.0.0:* users:(("ollama",pid=441,fd=3))' ;;
esac
EOF
  cat > "$d/bin/readlink" <<EOF
#!/usr/bin/env bash
[ "\$2" = "/proc/$PID/exe" ] && { printf '%s\n' '$exe'; exit 0; }
exit 1
EOF
  cat > "$d/bin/sha256sum" <<EOF
#!/usr/bin/env bash
printf '%s  %s\n' '$sha' "\$1"
EOF
  cat > "$d/bin/cat" <<EOF
#!/usr/bin/env bash
case "\$1" in
  /proc/$PID/cgroup) /bin/cat '$d/proc/$PID/cgroup' ;;
  /proc/441/cgroup)  /bin/cat '$d/proc/441/cgroup' ;;
  *) /bin/cat "\$@" ;;
esac
EOF
  cat > "$d/bin/tr" <<EOF
#!/usr/bin/env bash
if [ -p /dev/stdin ] || [ ! -t 0 ]; then /usr/bin/tr "\$@"; fi
EOF
  cat > "$d/bin/curl" <<EOF
#!/usr/bin/env bash
case "\$*" in *11434*) printf '%s' '$govhttp' ;; *8091*) printf '%s' '200' ;; *) printf '%s' '000' ;; esac
EOF
  cat > "$d/bin/systemctl" <<EOF
#!/usr/bin/env bash
case "\$*" in *ActiveState*) printf '%s\n' '$nem' ;; *UnitFileState*) printf '%s\n' 'disabled' ;; esac
EOF
  chmod +x "$d/bin"/*
  # redirect /proc reads for the target pid
  sed "s#/proc/\$TARGET/cmdline#$d/proc/$PID/cmdline#; s#/proc/\$TARGET/cgroup#$d/proc/$PID/cgroup#; s#/proc/\$gov_pid/cgroup#$d/proc/441/cgroup#" "$SCRIPT" > "$d/script.sh"
  out=$(PATH="$d/bin:$PATH" HOME="$d" bash "$d/script.sh" "$mode" 2>&1); rc=$?
  if [ "$rc" = "$erc" ] && printf '%s' "$out" | grep -q "$estr"; then
    printf '  PASS  %-38s rc=%s\n' "$name" "$rc"
  else
    printf '  FAIL  %-38s rc=%s (want %s / %s)\n' "$name" "$rc" "$erc" "$estr"
    printf '%s\n' "$out" | tail -4 | sed 's/^/          /'
  fi
  rm -rf "$d"
}

OK_SS="LISTEN 0 4096 127.0.0.1:11435 0.0.0.0:* users:((\"ollama\",pid=$PID,fd=3))"
USER_CG="0::/user.slice/user-1000.slice/session-104082.scope"
GOV_CG="0::/system.slice/ollama.service"

echo "GUARD TESTS (remediate mode unless noted) — a guard must stop execution before any signal"
scenario "no listener -> already absent"      remediate ""      /usr/local/bin/ollama "$GOOD_SHA" "ollama serve" "$USER_CG" "$GOV_CG" 200 inactive 0 "RESULT=ALREADY_ABSENT"
scenario "wrong executable path"              remediate "$OK_SS" /usr/bin/python3      "$GOOD_SHA" "ollama serve" "$USER_CG" "$GOV_CG" 200 inactive 3 "RESULT=UNKNOWN"
scenario "wrong executable hash"              remediate "$OK_SS" /usr/local/bin/ollama deadbeef    "ollama serve" "$USER_CG" "$GOV_CG" 200 inactive 3 "RESULT=UNKNOWN"
scenario "wrong command line"                 remediate "$OK_SS" /usr/local/bin/ollama "$GOOD_SHA" "ollama run x" "$USER_CG" "$GOV_CG" 200 inactive 3 "RESULT=UNKNOWN"
scenario "CRITICAL target is a systemd unit"  remediate "$OK_SS" /usr/local/bin/ollama "$GOOD_SHA" "ollama serve" "0::/system.slice/ollama.service" "$GOV_CG" 200 inactive 3 "RESULT=UNKNOWN"
scenario "governed 11434 unhealthy"           remediate "$OK_SS" /usr/local/bin/ollama "$GOOD_SHA" "ollama serve" "$USER_CG" "$GOV_CG" 503 inactive 3 "RESULT=UNKNOWN"
scenario "governed not under ollama.service"  remediate "$OK_SS" /usr/local/bin/ollama "$GOOD_SHA" "ollama serve" "$USER_CG" "0::/user.slice/x.scope" 200 inactive 3 "RESULT=UNKNOWN"
scenario "nemotron came back active"          remediate "$OK_SS" /usr/local/bin/ollama "$GOOD_SHA" "ollama serve" "$USER_CG" "$GOV_CG" 200 active   3 "RESULT=UNKNOWN"
scenario "all match, VERIFY mode -> no kill"  verify    "$OK_SS" /usr/local/bin/ollama "$GOOD_SHA" "ollama serve" "$USER_CG" "$GOV_CG" 200 inactive 0 "RESULT=VERIFIED_NOT_REMEDIATED"
