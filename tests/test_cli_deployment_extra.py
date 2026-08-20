from portable_runtime.api.cli import run_cli


def test_cli_more_commands(tmp_path):
    db = tmp_path / "more.db"
    # provider list
    assert run_cli(["--state", str(db), "provider", "list"]) == 0
    # work submit with capability
    assert run_cli(["--state", str(db), "work", "submit", "--title","t2","--capability","text.echo"]) == 0
    # get work id
    from portable_runtime.core.runtime import Runtime
    from portable_runtime.stores.sqlite import SQLiteStateStore
    runtime = Runtime(store=SQLiteStateStore(db))
    works = runtime.list_work()
    assert works
    wid = works[0].id
    runtime.store.close()
    # work show
    assert run_cli(["--state", str(db), "work", "show", wid]) == 0
    # work run
    assert run_cli(["--state", str(db), "work", "run", wid, "--capability","text.echo"]) == 0
    # work cancel
    assert run_cli(["--state", str(db), "work", "cancel", wid]) == 0
    # knowledge list/show (empty)
    assert run_cli(["--state", str(db), "knowledge", "list"]) == 0
    # state export json
    exp = tmp_path / "exp.json"
    assert run_cli(["--state", str(db), "state", "export", str(exp)]) == 0
    assert exp.exists()
    # state import
    db2 = tmp_path / "more2.db"
    assert run_cli(["--state", str(db2), "state", "import", str(exp)]) == 0
    # bundle export (tar.zst)
    bundle = tmp_path / "bundle.tar.zst"
    assert run_cli(["--state", str(db), "state", "export", str(bundle)]) == 0
    # bundle import
    db3 = tmp_path / "more3.db"
    assert run_cli(["--state", str(db3), "state", "import", str(bundle)]) == 0
    # plugin list
    assert run_cli(["--state", str(db), "plugin", "list"]) == 0
    # trigger list
    assert run_cli(["--state", str(db), "trigger", "list"]) == 0
    # workflow list
    assert run_cli(["--state", str(db), "workflow", "list"]) == 0
    # provider health
    assert run_cli(["--state", str(db), "provider", "health"]) in (0,1,2)

def test_cli_error_paths(tmp_path):
    db = tmp_path / "err.db"
    # work submit without title should error (SystemExit)
    try:
        run_cli(["--state", str(db), "work", "submit"])
        assert False
    except SystemExit:
        pass
    # plugin validate without path should error
    try:
        run_cli(["--state", str(db), "plugin", "validate"])
        assert False
    except SystemExit:
        pass

def test_deployment_local(tmp_path):
    from portable_runtime.deployment.local import create_local_runtime
    rt = create_local_runtime(tmp_path / "local.db", tmp_path / "artifacts")
    assert rt is not None
    w = rt.create_work(title="local-test")
    assert w.id
    rt.store.close()
