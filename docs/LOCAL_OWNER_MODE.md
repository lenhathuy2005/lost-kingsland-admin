# Local Owner Mode

For the local Windows Admin console, set:

```env
ADMIN_HOST=127.0.0.1
ADMIN_WRITE_ENABLED=true
ADMIN_LOCAL_OWNER_MODE=true
ADMIN_OWNER_NAME=Viet
ADMIN_ALLOW_REMOTE_NO_AUTH=false
```

The browser is automatically treated as the `OWNER` account and does not prompt for `ADMIN_TOKEN` or actor confirmation. Mutations still write to `ops.audit_logs` using `Viet` as the actor.

Safety: Local Owner Mode is effective only when the Admin server binds to loopback (`127.0.0.1`, `localhost`, or `::1`) unless `ADMIN_ALLOW_REMOTE_NO_AUTH=true` is explicitly set. Do not enable remote no-auth mode on a VPS or public network.

A tunnel or reverse proxy can expose a loopback-bound server to remote users. Before enabling either, set `ADMIN_LOCAL_OWNER_MODE=false` and configure a private `ADMIN_TOKEN`. The default configuration keeps Local Owner Mode off.
