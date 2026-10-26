#!/usr/bin/env bash
# Choose the ONE branch of the state machine this run takes. Pure: reads env only, writes outputs.
# action = resume-put | pending-sync | retire | rotate | adopt | noop | refuse (refuse exits 1, nothing changed).
# State: {current, pending, [phase put|env,] rotated_at}. retire fires only with NO pending, which after
# the phase marker exists only once a promote has happened, so the other slot is really the old value.
#
# Env: STATE_JSON ('' = no state), PRESENT (comma list of slots on the Worker), SLOT_A, SLOT_B,
# ROTATE_EVERY_DAYS, GRACE_HOURS, FORCE, NOW (epoch; tests inject it, default the clock).
set -eo pipefail

NOW="${NOW:-$(date +%s)}"
iso() { date -u -d "@$1" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -r "$1" +%Y-%m-%dT%H:%M:%SZ; }
has() { case ",${PRESENT}," in *",$1,"*) return 0 ;; esac; return 1; }
other() { if [ "$1" = "$SLOT_A" ]; then echo "$SLOT_B"; else echo "$SLOT_A"; fi; }
emit() { printf '%s=%s\n' "$1" "$2" >> "$GITHUB_OUTPUT"; }
finish() { # action new_slot retire_slot current rotated_at message
  emit action "$1"; emit new_slot "$2"; emit retire_slot "$3"; emit current "$4"; emit rotated_at "$5"; emit message "$6"
  echo "decision: $1 - $6"
  if [ "$1" = refuse ]; then exit 1; fi
  exit 0
}
refuse() { echo "::error::$1"; finish refuse "" "" "" "" "$1"; }

COUNT=0
if has "$SLOT_A"; then COUNT=$((COUNT + 1)); fi
if has "$SLOT_B"; then COUNT=$((COUNT + 1)); fi

if [ -z "$STATE_JSON" ]; then
  case "$COUNT" in
    0) finish rotate "$SLOT_A" "" "" "$NOW" "no state and no slot: bootstrap by rotating into ${SLOT_A}" ;;
    1) if has "$SLOT_A"; then S="$SLOT_A"; else S="$SLOT_B"; fi
       finish adopt "" "" "$S" "$NOW" "no state, only ${S} exists: adopting it as current" ;;
    *) refuse "no state variable but both slots exist, so which one is live is unknown. Check the Worker and set the state variable to {\"current\":\"<live slot>\",\"pending\":\"\",\"rotated_at\":<epoch>}." ;;
  esac
fi

if ! printf '%s' "$STATE_JSON" | jq -e 'type == "object" and (.current | type == "string") and (.pending | type == "string") and (.rotated_at | type == "number" and . == floor) and ((.phase // "") | type == "string")' >/dev/null 2>&1; then
  refuse "the state variable is not {current, pending, [phase,] rotated_at} JSON (rotated_at a whole epoch number). Check its value."
fi
CUR=$(printf '%s' "$STATE_JSON" | jq -r .current)
PEND=$(printf '%s' "$STATE_JSON" | jq -r .pending)
PHASE=$(printf '%s' "$STATE_JSON" | jq -r '.phase // ""')
if [ -n "$PEND" ]; then
  [ -n "$PHASE" ] || refuse "the state has pending (${PEND}) but no phase. Every state this action writes carries one, so check the state variable and the Worker slots."
  case "$PHASE" in put | env) ;; *) refuse "the state has phase '${PHASE}', neither put nor env. Check the state variable." ;; esac
fi
AT=$(printf '%s' "$STATE_JSON" | jq -r .rotated_at)

for v in "$CUR" "$PEND"; do
  if [ -n "$v" ] && [ "$v" != "$SLOT_A" ] && [ "$v" != "$SLOT_B" ]; then
    refuse "the state names '${v}', which is neither ${SLOT_A} nor ${SLOT_B}. Check the state variable and the slot inputs."
  fi
done
if [ -n "$PEND" ] && [ "$PEND" = "$CUR" ]; then
  refuse "the state has pending equal to current (${CUR}). Check the state variable."
fi
if [ -n "$CUR" ] && ! has "$CUR"; then
  refuse "the state names current slot ${CUR}, but the Worker has no such secret. Check the Worker secrets and the state variable."
fi

if [ -n "$PEND" ]; then
  # phase put: the PUT / environment write may or may not have happened
  # and a Worker secret cannot be read back, so redo both with a fresh value. Never retire here.
  if [ "$PHASE" != env ]; then
    finish resume-put "$PEND" "" "$CUR" "$AT" "a rotation into ${PEND} died before its environment secret was confirmed: writing a fresh value into ${PEND} and the environment secret, then syncing"
  fi
  has "$PEND" || refuse "the state names pending slot ${PEND}, but the Worker has no such secret. Check the Worker secrets and the state variable."
  finish pending-sync "$PEND" "" "$CUR" "$AT" "a sync of ${PEND} is pending: re-dispatching the sync"
fi
[ -n "$CUR" ] || refuse "the state has no current slot and nothing pending. Check the state variable."

AGE=$((NOW - AT))
if [ "$COUNT" = 2 ]; then
  OLD=$(other "$CUR")
  GRACE=$((GRACE_HOURS * 3600))
  if [ "$AGE" -ge "$GRACE" ]; then
    finish retire "" "$OLD" "$CUR" "$AT" "grace of ${GRACE_HOURS}h reached: retiring ${OLD}"
  fi
  finish noop "" "" "$CUR" "$AT" "grace not reached: old slot ${OLD} retires at $(iso $((AT + GRACE)))"
fi
DUE=$((ROTATE_EVERY_DAYS * 86400))
if [ "${FORCE:-false}" = "true" ] || [ "$AGE" -ge "$DUE" ]; then
  finish rotate "$(other "$CUR")" "" "$CUR" "$AT" "rotating into $(other "$CUR")"
fi
finish noop "" "" "$CUR" "$AT" "next rotation due at $(iso $((AT + DUE)))"
