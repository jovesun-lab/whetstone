#!/usr/bin/env bash
# Remove notify-me's user settings. The hook + scripts are removed by
# disabling/uninstalling the 'notify-me' plugin in your app.
rm -rf "$HOME/.notify-me"
echo "Removed ~/.notify-me. Now disable or uninstall the 'notify-me' plugin to remove the hook and scripts."
