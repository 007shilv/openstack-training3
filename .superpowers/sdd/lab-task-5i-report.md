# Lab Task 5I report: manual Horizon deployment

Baseline Swift PASS commit: `9a66c6edb36e088d50f4f18921d6f8ea8c1550d4`.

## Gates and controller change

- The two-node read-only gate confirmed controller `.151` and compute `.150`; all prior API probes were reachable, Cinder and Swift services were active/enabled, `/dev/sdb` remained the `cinder-volumes` PV, and `/dev/sdc` remained mounted XFS `swift-data`.
- Before installation, `openstack-dashboard` and `python3-horizon` were absent and no dashboard configuration existed. The controller installed `openstack-dashboard-23.1.0` and `python3-horizon-23.1.0` only from `openstack-local` with no unsafe DNF options.
- Package default `local_settings` and Apache dashboard configuration were backed up in a restrictive task-5i controller backup directory before editing. An initial shell-variable quoting error made no backup or configuration change; the backup was then completed before the effective settings were edited.
- The effective settings use controller Keystone v3, multidomain, Default domain, the verified existing `member` role, `/dashboard/` webroot/login/logout/redirect paths, identity/image/volume API versions 3/2/3, Asia/Shanghai, and controller memcached-backed cache sessions. `ALLOWED_HOSTS` is limited to explicit lab host/IP values. The package-generated Django secret was neither changed, displayed, hashed, nor recorded.
- The package-provided Apache WSGI mapping for `/dashboard` was retained. `httpd -t` and `manage.py check` passed; Apache was enabled and restarted.

## Lightweight acceptance

- Apache is active and enabled; configuration test is valid.
- `/dashboard/` returns HTTP 302 to the dashboard login route. The login route returns HTTP 200 and includes form, username, password, and CSRF markers.
- Interactive browser automation was unavailable. No login cookie, password, token, session export, or screenshot was created. The remaining manual-browser acceptance is: visit `http://controller/dashboard/`, authenticate with the existing administrator account, confirm Overview loads, choose Logout, and close the browser tab without exporting browser data.

## Final scope and teaching notes

- Final read-only validation confirmed existing APIs remain reachable and compute disk states remain `/dev/sdb` = `cinder-volumes`, `/dev/sdc` = mounted XFS `swift-data`.
- Horizon is the sole newly deployed component. No disk/network/storage-object operations, Cinder/Swift reconfiguration, snapshot creation/restoration, or copied-script execution occurred.
- The manual record and snapshots contain placeholders only; no secret, password, token, cookie, session, runtime identifier, or screenshot is tracked.
