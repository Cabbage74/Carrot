from carrot import sandbox


def test_build_bwrap_argv_blocks_network_by_default():
    argv = sandbox.build_bwrap_argv("echo hi", "/workspace", allow_network=False)
    assert "--unshare-net" in argv
    assert argv[-3:] == ["sh", "-c", "echo hi"]


def test_build_bwrap_argv_allows_network_when_requested():
    argv = sandbox.build_bwrap_argv("curl example.com", "/workspace", allow_network=True)
    assert "--unshare-net" not in argv


def test_build_bwrap_argv_binds_workspace_read_write():
    argv = sandbox.build_bwrap_argv("echo hi", "/workspace", allow_network=False)
    bind_index = argv.index("--bind")
    assert argv[bind_index + 1 : bind_index + 3] == ["/workspace", "/workspace"]


def test_looks_like_network_failure_detects_common_markers():
    assert sandbox.looks_like_network_failure("curl: (6) Could not resolve host: example.com")
    assert sandbox.looks_like_network_failure("connect: Network is unreachable")
    assert not sandbox.looks_like_network_failure("ls: cannot access 'x': No such file")
