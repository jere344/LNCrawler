#!/bin/sh
# Runs llama-server with the arguments of the container, and restarts it when the worker asks. The worker writes
# /control/restart when the server stops answering in the middle of a call (see worker/llm.py). This script then stops
# llama-server (TERM, KILL after 10 s) and exits 1, so the container's restart policy starts it again. Stop signals
# (docker stop) are passed on to llama-server, and the script exits with its code.
set -u

FLAG=/control/restart
RESTARTING=/tmp/llama-restarting

rm -f "$RESTARTING" "$FLAG"  # a request left from before this start is already answered by it
llama-server "$@" &
pid=$!

# Passes stop signals on. A wait is cut short by a trapped signal, so the loop below waits again while llama-server runs.
trap 'kill -TERM "$pid" 2>/dev/null' TERM INT

# Looks for the flag every 5 seconds while llama-server runs.
watch() {
    while kill -0 "$pid" 2>/dev/null; do
        if [ -e "$FLAG" ]; then
            rm -f "$FLAG"
            echo "restart requested: stopping llama-server" >&2
            : > "$RESTARTING"
            kill -TERM "$pid" 2>/dev/null
            (sleep 10; kill -KILL "$pid" 2>/dev/null) &
            return
        fi
        sleep 5
    done
}
watch &

# wait reaps the process. kill -0 only tells it is gone once it has been reaped, so the loop checks after each wait.
code=0
while :; do
    wait "$pid"
    code=$?
    kill -0 "$pid" 2>/dev/null || break
done

if [ -e "$RESTARTING" ]; then
    rm -f "$RESTARTING"
    exit 1
fi
exit "$code"
