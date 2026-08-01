#!/bin/sh
set -eu
PAM_FILE="/etc/pam.d/sudo_local"
if [ -r "$PAM_FILE" ] && grep -q "pam_tid.so" "$PAM_FILE"; then
    echo "OK: Touch ID for sudo already configured"
    exit 0
fi
echo "auth       sufficient     pam_tid.so" | sudo tee -a "$PAM_FILE" >/dev/null
echo "Configured Touch ID for sudo in $PAM_FILE"
