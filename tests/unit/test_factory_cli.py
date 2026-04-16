import json

from apps.factory_cli.main import build_status, main, resolve_project_dir


def test_resolve_project_dir_defaults_to_current_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    assert resolve_project_dir(None) == tmp_path.resolve()


def test_build_status_marks_factory_cli_placeholder(tmp_path):
    status = build_status(tmp_path)

    assert status["mode"] == "factory"
    assert status["entry"] == "yunxi_cli"
    assert status["implementation_state"] == "placeholder"
    assert status["daily_channel"] == "feishu"


def test_status_command_outputs_json(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)

    assert main(["--status"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["project_dir"] == str(tmp_path.resolve())

