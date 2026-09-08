#!/usr/bin/env bash
# Release-gating npm audit that distinguishes "there is a critical vulnerability"
# from "npmjs.org did not answer".
#
# `npm audit --audit-level=critical` exits non-zero for both, and the second is
# not a finding about this repository. It matters because this target is on the
# release path -- release-check -> ci -> frontend-ci -> frontend-audit -- so a
# registry outage fails the Release workflow *after* the tag has been pushed,
# which reads as "this release is unsafe" when it means "npm had a bad minute".
# That is not hypothetical: it happened on the v4.12.0 release PR itself, with
# `503 Service Unavailable` from the bulk advisories endpoint.
#
# So: retry a few times, fail on an actual critical advisory, and warn loudly
# (but pass) when the registry could not be reached. Passing on an unreachable
# registry is the deliberate half of this trade -- an audit that cannot run has
# told us nothing, and a third-party outage should not be able to block a
# release. The warning is on stderr and in the job log for whoever reads it.
set -uo pipefail

cd "$(dirname "$0")/../frontend" || exit 1

attempts=3
delay=5
out=""

for i in $(seq 1 "$attempts"); do
  out="$(npm audit --json 2>/dev/null)"

  # A successful audit always carries metadata.vulnerabilities. An outage
  # returns a payload with .error and no metadata, so key on the metadata
  # rather than on the exit code, which is non-zero in both cases.
  critical="$(printf '%s' "$out" \
    | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{
        try{const j=JSON.parse(s);const v=j?.metadata?.vulnerabilities;
        process.stdout.write(v&&typeof v.critical==="number"?String(v.critical):"");}
        catch(e){process.stdout.write("");}})' 2>/dev/null)"

  if [[ -n "$critical" ]]; then
    if [[ "$critical" -gt 0 ]]; then
      echo "npm audit: ${critical} critical vulnerability(ies) found." >&2
      npm audit --audit-level=critical >&2 || true
      exit 1
    fi
    echo "npm audit: no critical vulnerabilities."
    exit 0
  fi

  if [[ $i -lt $attempts ]]; then
    echo "npm audit: no usable result (attempt ${i}/${attempts}); retrying in ${delay}s..." >&2
    sleep "$delay"
    delay=$((delay * 2))
  fi
done

echo "warning: npm audit could not reach the registry after ${attempts} attempts." >&2
echo "warning: the audit did NOT run -- this is not a statement that the tree is clean." >&2
printf '%s\n' "$out" | head -c 2000 >&2
echo >&2
exit 0
