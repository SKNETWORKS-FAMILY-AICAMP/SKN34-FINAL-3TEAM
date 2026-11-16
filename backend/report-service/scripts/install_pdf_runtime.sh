#!/bin/sh
# report-only installer, shared by GitHub Actions and the report image build.
set -eu

if [ "$#" -eq 0 ]; then
    echo "Usage: sh install_pdf_runtime.sh <playwright command...>" >&2
    exit 2
fi

as_root() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    else
        sudo "$@"
    fi
}

retry() {
    attempt=1
    while :; do
        if "$@"; then
            return 0
        else
            status=$?
        fi
        if [ "$attempt" -ge 3 ]; then
            echo "PDF runtime: failed after $attempt attempts: $*" >&2
            return "$status"
        fi
        echo "PDF runtime: attempt $attempt failed; retrying: $*" >&2
        sleep "$((attempt * 5))"
        attempt=$((attempt + 1))
    done
}

# install-deps starts apt itself (using sudo on a non-root runner), so configure
# apt rather than passing flags only to our separate font installation command.
printf '%s\n' \
    'Acquire::Retries "3";' \
    'Acquire::http::Timeout "30";' \
    'Acquire::https::Timeout "30";' \
    'APT::Update::Error-Mode "any";' \
    | as_root tee /etc/apt/apt.conf.d/80report-pdf-runtime >/dev/null

export PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=45000
retry "$@" install-deps chromium
retry as_root apt-get install -y --no-install-recommends fonts-noto-cjk
retry "$@" install chromium
as_root apt-get clean
