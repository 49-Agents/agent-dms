import argparse
import asyncio
import json
import sys

from .errors import DomainError, fail
from .service import Service
from .storage import ProcessLock, Store, initialize


def parser():
    root = argparse.ArgumentParser(prog="agent-dms")
    root.add_argument("--version", action="version", version="agent-dms 0.1.0")
    subs = root.add_subparsers(dest="command", required=True)
    init = subs.add_parser("init", help="Create private project state")
    init.add_argument("--project-root", required=True)
    init.add_argument("--data-dir")
    serve = subs.add_parser("serve", help="One authenticated project HTTP daemon")
    serve.add_argument("--data-dir", required=True)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--allow-remote", action="store_true")
    serve.add_argument("--allowed-host", action="append")
    serve.add_argument("--allowed-origin", action="append", default=[])
    agent = subs.add_parser("agent", help="Local operator identity administration")
    agent.add_argument("--data-dir", required=True)
    actions = agent.add_subparsers(dest="action", required=True)
    add = actions.add_parser("add")
    add.add_argument("name")
    add.add_argument("--provider")
    add.add_argument("--model")
    actions.add_parser("list")
    for name in ("revoke", "rotate-token"):
        action = actions.add_parser(name)
        action.add_argument("agent_id")
    config = subs.add_parser("config", help="Print scoped examples; never edit client configuration")
    config.add_argument("--data-dir", required=True)
    config.add_argument("--client", choices=["codex", "claude", "generic"], required=True)
    config.add_argument("--agent", required=True)
    config.add_argument("--transport", choices=["http", "stdio"], required=True)
    config.add_argument("--url", default="http://127.0.0.1:8765/mcp")
    config.add_argument("--token-file", help="Private file path for a stdio example; token is never read or printed")
    doctor = subs.add_parser("doctor")
    doctor.add_argument("--data-dir", required=True)
    backup = subs.add_parser("backup")
    backup.add_argument("--data-dir", required=True)
    backup.add_argument("--out", required=True)
    restore = subs.add_parser("restore")
    restore.add_argument("--snapshot", required=True)
    restore.add_argument("--data-dir", required=True)
    stdio = subs.add_parser("stdio", help="Forward official SDK stdio to the HTTP daemon")
    stdio.add_argument("--url", required=True)
    stdio.add_argument("--token-file", required=True)
    watch = subs.add_parser("watch", help="Optional existing-client watcher; or receipts/resolve")
    watch.add_argument("watch_action", nargs="?", choices=["receipts", "resolve"])
    watch.add_argument("--ledger", required=True)
    watch.add_argument("--url")
    watch.add_argument("--token-file")
    watch.add_argument("--session-id")
    watch.add_argument("--sink", choices=["stdout", "codex"], default="stdout")
    watch.add_argument("--thread")
    watch.add_argument("--workspace")
    watch.add_argument("--receipt")
    resolutions = watch.add_mutually_exclusive_group()
    resolutions.add_argument("--delivered", action="store_true")
    resolutions.add_argument("--retry", action="store_true")
    watch.add_argument("--reason")
    return root


def execute(args):
    if args.command == "init":
        return initialize(args.project_root, args.data_dir).model_dump()
    if args.command == "restore":
        from .operations import restore
        return restore(args.snapshot, args.data_dir)
    if args.command == "stdio":
        from .stdio_bridge import bridge
        asyncio.run(bridge(args.url, args.token_file))
        return None
    if args.command == "watch":
        from .notification_receipts import ReceiptLedger
        from .watch import watch
        if args.watch_action:
            with ReceiptLedger(args.ledger) as ledger:
                if args.watch_action == "receipts":
                    return ledger.list()
                if not args.receipt or not args.reason or not (args.delivered or args.retry):
                    fail("VALIDATION_ERROR", "Resolve needs --receipt, --reason and exactly one of --delivered/--retry")
                return ledger.resolve(args.receipt, args.delivered, args.reason)
        if not args.url or not args.token_file or not args.session_id:
            fail("VALIDATION_ERROR", "Watcher needs --url, --token-file and --session-id")
        if args.sink == "codex" and (not args.thread or not args.workspace):
            fail("VALIDATION_ERROR", "Codex sink needs --thread and --workspace")
        asyncio.run(watch(args.url, args.token_file, args.session_id, args.ledger, args.sink, args.thread, args.workspace))
        return None
    store = Store(args.data_dir)
    if args.command == "serve":
        import uvicorn
        from .mcp_server import configure_safe_logging, create_app, validate_bind
        validate_bind(args.host, args.allow_remote, args.allowed_host)
        if not 1 <= args.port <= 65535:
            fail("VALIDATION_ERROR", "Port must be 1–65535")
        bind_host = f"[{args.host}]" if ":" in args.host else args.host
        hosts = args.allowed_host or [f"{bind_host}:{args.port}", f"127.0.0.1:{args.port}", f"localhost:{args.port}", f"[::1]:{args.port}"]
        configure_safe_logging()
        with ProcessLock(store.data_dir / "serve.lock"):
            app = create_app(store, hosts=hosts, origins=args.allowed_origin, lock=False)
            uvicorn.run(app, host=args.host, port=args.port, workers=1, proxy_headers=False, access_log=False, log_config=None)
        return None
    if args.command == "agent":
        service = Service(store)
        if args.action == "add":
            return service.add_agent(args.name, args.provider, args.model)
        if args.action == "list":
            return service.operator_list()
        if args.action == "revoke":
            return service.revoke(args.agent_id)
        return service.rotate_token(args.agent_id)
    if args.command == "doctor":
        from .operations import doctor
        return doctor(store)
    if args.command == "backup":
        from .operations import backup
        return backup(store, args.out)
    if args.command == "config":
        from .operations import client_config
        if args.agent not in {r["id"] for r in Service(store).operator_list()}:
            fail("NOT_FOUND", "Agent not found")
        if args.transport == "stdio" and not args.token_file:
            fail("VALIDATION_ERROR", "Stdio example requires the selected --token-file")
        return client_config(args.client, args.transport, args.agent, args.url, args.token_file)


def main(argv=None):
    try:
        args = parser().parse_args(argv)
        result = execute(args)
        if result is not None:
            print(result if isinstance(result, str) else json.dumps(result, ensure_ascii=False))
    except DomainError as exc:
        print(json.dumps(exc.as_dict()), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception:
        print("Command failed; check local configuration and permissions", file=sys.stderr)
        return 1
    return 0
