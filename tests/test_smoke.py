def test_import_portable_runtime():
    import portable_runtime
    assert portable_runtime.__version__ == "0.1.0"

def test_import_core():
    from portable_runtime.core.runtime import Runtime
    assert Runtime is not None
