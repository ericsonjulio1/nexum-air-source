#!/usr/bin/env bash
# =============================================================================
# Build the NexumAir PRODUCTION image (Phase 1).
#
#   ./build.sh                 # build linux/amd64, --load into local docker
#   ./build.sh --push          # build + push to the registry (needs docker login)
#   ./build.sh --tag v16-prod-2 --repo ericsonjulio/erpnext   # default repo; override for GHCR etc.
#   PLATFORM=linux/arm64 ./build.sh   # native arm64 (for testing on this Mac)
#
# Env overrides: FRAPPE_DOCKER, PLATFORM, IMAGE_REPO, TAG, BRANDING_REPO.
#
# NOTE: amd64 on an arm64 Mac uses QEMU emulation (slow). If buildx errors with
# "exec format" / missing platform, install the emulators once:
#     docker run --privileged --rm tonistiigi/binfmt --install amd64
# Faster alternative: run this script ON the x86 target server (PLATFORM unset).
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRANDING_REPO="${BRANDING_REPO:-$(cd "$SCRIPT_DIR/../.." && pwd)}"   # repo root
FRAPPE_DOCKER="${FRAPPE_DOCKER:-$HOME/dev/frappe_docker}"
PLATFORM="${PLATFORM:-linux/amd64}"
IMAGE_REPO="${IMAGE_REPO:-ericsonjulio/erpnext}"   # Docker Hub account the user OWNS (NOT the nexumair org)
TAG="${TAG:-v16-prod-1}"
PUSH=0

PRINT_ARGS=0
while [ $# -gt 0 ]; do
  case "$1" in
    --push)            PUSH=1 ;;
    --tag)             TAG="$2"; shift ;;
    --repo)            IMAGE_REPO="$2"; shift ;;
    --platform)        PLATFORM="$2"; shift ;;
    --print-args)      PRINT_ARGS=1 ;;
    -h|--help)         sed -n '2,18p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
  shift
done

FULL_TAG="${IMAGE_REPO}:${TAG}"
STAGE="${FRAPPE_DOCKER}/.nexum-build/my_branding"

# ---- pins: apps.pinned.json -> one SHA_<APP> build arg per app --------------
# The Containerfile checks out these exact commits, so a build can never
# silently absorb an upstream push. Refresh deliberately with pin-apps.sh.
PINS_JSON="$SCRIPT_DIR/apps.pinned.json"
[ -f "$PINS_JSON" ] || { echo "ERROR: $PINS_JSON missing — run pin-apps.sh first"; exit 1; }
PIN_ARGS=()
PINNED_APPS=" "
while read -r url sha; do
  [ -z "$url" ] && continue
  case "$url" in local:*) continue ;; esac
  [ "$sha" = "UNRESOLVED" ] && { echo "ERROR: unresolved pin for $url — re-run pin-apps.sh"; exit 1; }
  app="$(basename "$url" | tr '[:lower:]-' '[:upper:]_')"
  PIN_ARGS+=(--build-arg "SHA_${app}=${sha}")
  PINNED_APPS="${PINNED_APPS}${app} "
done <<< "$(grep -oE '"url"[^}]*"commit"[[:space:]]*:[[:space:]]*"[^"]*"' "$PINS_JSON" \
  | sed -E 's/.*"url"[[:space:]]*:[[:space:]]*"([^"]+)".*"commit"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1 \2/')"
# every app the Containerfile fetches must have a pin (fail HERE, not 2h into the build)
for need in FRAPPE ERPNEXT HRMS PAYMENTS PRINT_DESIGNER INSIGHTS TELEPHONY HELPDESK CRM \
            GAMEPLAN BUILDER LMS SLIDES WEBSHOP ECOMMERCE_INTEGRATIONS DRIVE LENDING; do
  case "$PINNED_APPS" in *" $need "*) : ;; *)
    echo "ERROR: no pin for $need in $PINS_JSON — run pin-apps.sh"; exit 1 ;;
  esac
done
echo "==> $(( ${#PIN_ARGS[@]} / 2 )) app pins from apps.pinned.json (generated $(grep -oE '"generated"[^,]*' "$PINS_JSON" | cut -d'"' -f4))"
if [ "$PRINT_ARGS" -eq 1 ]; then printf '%s\n' "${PIN_ARGS[@]}"; exit 0; fi

# ---- pre-flight -------------------------------------------------------------
command -v docker >/dev/null || { echo "ERROR: docker not found"; exit 1; }
docker buildx version >/dev/null 2>&1 || { echo "ERROR: docker buildx not available"; exit 1; }
[ -f "$FRAPPE_DOCKER/resources/core/start.sh" ] || {
  echo "ERROR: FRAPPE_DOCKER=$FRAPPE_DOCKER doesn't look like a frappe_docker checkout"; exit 1; }
[ -f "$BRANDING_REPO/my_branding/hooks.py" ] || {
  echo "ERROR: BRANDING_REPO=$BRANDING_REPO doesn't contain the my_branding app"; exit 1; }

# ---- stage my_branding (committed HEAD; baked into the image) ---------------
if [ -n "$(git -C "$BRANDING_REPO" status --porcelain)" ]; then
  echo "WARNING: $BRANDING_REPO has uncommitted changes — the image bakes the"
  echo "         COMMITTED state only. Commit + push before a real release."
fi
MB_SHA="$(git -C "$BRANDING_REPO" rev-parse --short HEAD)"
echo "==> staging my_branding @ $MB_SHA"
rm -rf "$STAGE"
mkdir -p "$(dirname "$STAGE")"
git clone --quiet --depth 1 "file://$BRANDING_REPO" "$STAGE"
rm -rf "$STAGE/.git"

# ---- build ------------------------------------------------------------------
OUTPUT="--load"; [ "$PUSH" -eq 1 ] && OUTPUT="--push"
echo "==> building $FULL_TAG  platform=$PLATFORM  output=${OUTPUT#--}"
echo "    context=$FRAPPE_DOCKER  containerfile=$SCRIPT_DIR/Containerfile"

set -x
docker buildx build \
  --platform "$PLATFORM" \
  --file "$SCRIPT_DIR/Containerfile" \
  --tag "$FULL_TAG" \
  --build-arg FRAPPE_BRANCH=version-16 \
  "${PIN_ARGS[@]}" \
  --label "com.nexumair.my_branding_sha=$MB_SHA" \
  $OUTPUT \
  "$FRAPPE_DOCKER"
set +x

# ---- cleanup ----------------------------------------------------------------
rm -rf "$STAGE"
echo "==> done: $FULL_TAG  (my_branding @ $MB_SHA)"
[ "$PUSH" -eq 0 ] && echo "    loaded locally; re-run with --push to publish to the registry."
