#!/bin/zsh
# Updating means the site updates. This delegates to update_and_publish.command so
# the shortest-named command can never leave the published site a day behind —
# which is exactly what it did while this was the data-only variant.
# Data-only remains available as: python -m scripts.morning_update
exec "$(dirname "$0")/update_and_publish.command"
