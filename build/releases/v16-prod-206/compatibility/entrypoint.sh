#!/bin/bash
set -e
ASSETS_PATH=/home/frappe/frappe-bench/sites/assets
BAKED_PATH=/home/frappe/frappe-bench/assets
# Several services start together against the same sites volume. Serialize the
# legacy-directory conversion and atomically replace the shared asset symlink.
exec 9> /home/frappe/frappe-bench/sites/.assets-link.lock
flock 9
if [ -e "$ASSETS_PATH" ] && [ ! -L "$ASSETS_PATH" ]; then
  rm -rf "$ASSETS_PATH"
fi
LINK_DIR=$(mktemp -d /home/frappe/frappe-bench/sites/.assets-link.XXXXXX)
trap 'rm -rf "$LINK_DIR"' EXIT
ln -s "$BAKED_PATH" "$LINK_DIR/assets"
mv -Tf "$LINK_DIR/assets" "$ASSETS_PATH"
rmdir "$LINK_DIR"
trap - EXIT
flock -u 9
exec 9>&-
exec "$@"
