#!/usr/bin/env python3
"""Startup and runtime self-checks for an unattended appliance.

The failure mode that matters on a kitchen wall is not a crash - systemd
restarts those within ten seconds and nobody notices. It is a process that
stays alive and stops working, because then systemd keeps reporting
`active (running)` and there is nothing to notice until somebody picks up
their phone and finds the app dead.

That happened: a leaked UDP socket per calendar refresh filled the
process's 1024-descriptor table over about two days, after which no new
socket could be created. Every outbound fetch failed, and so did Flask's
own accept(), so the wall and the phone both went blank while the service
looked healthy. The two checks here turn both halves of that into
something visible - the cause at startup, the symptom while running.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time

log = logging.getLogger('dashboard.selfcheck')

# The descriptor table is shared by sockets, database handles and photo
# uploads, so a dashboard that is merely busy sits well under a tenth of it.
# Past 60% something is leaking; past 85% the next calendar refresh is
# likely to be the one that cannot open a socket.
WARN_FRACTION = 0.60
FATAL_FRACTION = 0.85
CHECK_INTERVAL = 60.0

# Packages whose identity matters enough to check. Both are HTTP plumbing:
# a substituted urllib3 silently changes which protocols the dashboard
# speaks to Google and Apple, which is how the outage above began.
WATCHED_IMPORTS = ('urllib3', 'requests')


def descriptor_limit():
    """The soft RLIMIT_NOFILE, or None where the platform has no such thing."""
    try:
        import resource
    except ImportError:          # Windows - the dev machine
        return None
    soft, _hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft in (-1, getattr(resource, 'RLIM_INFINITY', -1)):
        return None
    return soft


def open_descriptors():
    """How many descriptors this process holds, or None if unknowable.

    /proc/self/fd is the only cheap answer, and listing it opens one
    descriptor of its own, which is why this counts rather than estimates.
    """
    try:
        return len(os.listdir('/proc/self/fd'))
    except OSError:              # no procfs: Windows, or a stripped container
        return None


def shadowed_imports(modules=WATCHED_IMPORTS):
    """Watched modules that came from neither the virtualenv nor the system.

    Returns a list of (name, path). The virtualenv here is deliberately
    built with --system-site-packages, so Debian's own
    /usr/lib/python3/dist-packages is a legitimate source and must not be
    reported - that is the difference between this check being useful and
    it crying wolf on every boot. What is left over is per-user
    site-packages, ~/.local, which takes precedence over a virtualenv's own
    copy of a package and is where a stray install can quietly replace a
    dependency. Outside a virtualenv there is nothing to compare against,
    so the check says nothing rather than guessing.
    """
    if sys.prefix == sys.base_prefix:
        return []

    expected = (os.path.realpath(sys.prefix) + os.sep,
                os.path.realpath(sys.base_prefix) + os.sep)
    found = []
    for name in modules:
        module = sys.modules.get(name)
        path = getattr(module, '__file__', None) if module else None
        if path and not os.path.realpath(path).startswith(expected):
            found.append((name, path))
    return found


def report_shadowed_imports(modules=WATCHED_IMPORTS):
    """Log anything loaded from an unexpected place. Returns what it found."""
    found = shadowed_imports(modules)
    for name, path in found:
        log.warning("%s was loaded from %s - neither this virtualenv nor the "
                    "system Python. A per-user install (~/.local) takes "
                    "precedence over both, so the dashboard is running "
                    "against a package it was not tested with.", name, path)
    return found


def _watch(limit, on_fatal):
    warn_at = int(limit * WARN_FRACTION)
    fatal_at = int(limit * FATAL_FRACTION)
    warned = False

    while True:
        time.sleep(CHECK_INTERVAL)
        count = open_descriptors()
        if count is None:
            return

        if count >= fatal_at:
            log.critical("%d of %d file descriptors in use. Something is "
                         "leaking them and the next connection will fail, so "
                         "exiting for systemd to restart a clean process.",
                         count, limit)
            on_fatal()
            return

        if count >= warn_at and not warned:
            # Once per rise, not once a minute: a warning that repeats
            # forever is one nobody reads.
            log.warning("%d of %d file descriptors in use - climbing", count, limit)
            warned = True
        elif count < warn_at:
            warned = False


def _die():
    # os._exit, not sys.exit: this runs on a worker thread, where SystemExit
    # would end only the thread and leave the wedged process running. Flush
    # first or the explanation never reaches the journal.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass
    os._exit(1)


def start_descriptor_watchdog(on_fatal=_die):
    """Watch the descriptor table on a daemon thread. Returns it, or None.

    Returns None where there is nothing to watch - no procfs, or no soft
    limit to measure against - so the caller can log that plainly instead
    of believing it is protected.
    """
    limit = descriptor_limit()
    if limit is None or open_descriptors() is None:
        return None

    thread = threading.Thread(target=_watch, args=(limit, on_fatal),
                              name='fd-watchdog', daemon=True)
    thread.start()
    log.info("Descriptor watchdog running: warn at %d, restart at %d of %d",
             int(limit * WARN_FRACTION), int(limit * FATAL_FRACTION), limit)
    return thread
