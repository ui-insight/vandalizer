"""setup.sh checks the site address links use, on every deploy path.

Support ticket (vandalizer-dev): calendar (.ics) links went to
http://localhost:5173. backend/.env.example ships that value and only a fresh
production setup asked for the address, so existing installs never fixed it.
These run the real check_site_url from setup.sh: piped (as auto-update/cron
runs it) and in a pseudo-terminal (as an operator runs it).
"""

import os
import pty
import re
import select
import subprocess
from pathlib import Path

import pytest

SETUP = Path(__file__).resolve().parents[2] / "setup.sh"
FUNCS = ("_url_is_local", "check_site_url", "prompt", "set_env")


def _script(env_file: Path) -> str:
    text = SETUP.read_text()
    bodies = []
    for name in FUNCS:
        match = re.search(rf"^{re.escape(name)}\(\) \{{\n.*?^\}}\n", text, re.S | re.M)
        assert match, f"{name} not found in setup.sh"
        bodies.append(match.group(0))
    return "\n".join([
        f'ENV_FILE="{env_file}"',
        "SYM_WARN= SYM_CHECK= SYM_CROSS= SYM_ARROW= YELLOW= RED= BOLD= DIM= RESET=",
        *bodies,
        "SITE_URL_CHANGED=false",
        "check_site_url",
        'echo "CHANGED=$SITE_URL_CHANGED"',
    ])


def _env(tmp_path, text):
    env_file = tmp_path / ".env"
    env_file.write_text(text)
    return env_file


def _piped(env_file):
    return subprocess.run(["bash", "-c", _script(env_file)], stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=10).stdout


def _terminal(env_file, *answers):
    """Run in a pty so [[ -t 0 ]] is true; send each answer when prompted."""
    main, child = pty.openpty()
    proc = subprocess.Popen(["bash", "-c", _script(env_file)], stdin=child, stdout=child, stderr=child)
    os.close(child)
    out, pending = b"", list(answers)
    while True:
        ready, _, _ = select.select([main], [], [], 5)
        if not ready:
            break
        try:
            chunk = os.read(main, 4096)
        except OSError:
            break
        if not chunk:
            break
        out += chunk
        if pending and out.rstrip().endswith(b":"):
            os.write(main, (pending.pop(0) + "\n").encode())
    proc.wait(timeout=10)
    os.close(main)
    return out.decode(errors="replace")


LOCAL = "FRONTEND_URL=http://localhost:5173\n"
SITE = "https://vandalizer-dev.insight.uidaho.edu"


def test_cron_runs_warn_and_change_nothing(tmp_path):
    env_file = _env(tmp_path, LOCAL)
    out = _piped(env_file)
    assert "WARNING: FRONTEND_URL is http://localhost:5173" in out
    assert env_file.read_text() == LOCAL


@pytest.mark.parametrize("text", [
    f"FRONTEND_URL={SITE}\n",
    f"FRONTEND_URL=http://localhost:5173\nVANDALIZER_BASE_URL={SITE}\n",
    "FRONTEND_URL=http://localhost:5173\nSITE_URL_LOCAL_OK=true\n",
])
def test_a_real_address_or_a_recorded_local_choice_is_left_alone(tmp_path, text):
    env_file = _env(tmp_path, text)
    assert _terminal(env_file).strip().endswith("CHANGED=false")
    assert env_file.read_text() == text


def test_the_template_placeholder_does_not_count_as_an_address(tmp_path):
    env_file = _env(tmp_path, LOCAL + "VANDALIZER_BASE_URL=https://your-domain.com\n")
    assert "WARNING: FRONTEND_URL" in _piped(env_file)


def test_an_operator_sets_the_address(tmp_path):
    env_file = _env(tmp_path, LOCAL + "ENVIRONMENT=development\n")
    out = _terminal(env_file, "localhost:8080", SITE + "/")
    assert "with no path" in out  # the bad answer was refused and asked again
    assert "CHANGED=true" in out
    assert env_file.read_text() == f"FRONTEND_URL={SITE}\nENVIRONMENT=development\n"


def test_a_blank_answer_keeps_localhost_and_is_not_asked_again(tmp_path):
    env_file = _env(tmp_path, LOCAL)
    out = _terminal(env_file, "")
    assert "CHANGED=false" in out
    assert env_file.read_text() == LOCAL + "SITE_URL_LOCAL_OK=true\n"
    assert _terminal(env_file).strip().endswith("CHANGED=false")


def test_every_deploy_path_runs_the_check():
    text = SETUP.read_text()
    redeploy = re.search(r"^do_redeploy\(\) \{\n.*?^\}\n", text, re.S | re.M).group(0)
    assert redeploy.index("check_site_url") < redeploy.index("--force-recreate --no-deps api")
    repair = re.search(r"^repair\(\) \{\n.*?^\}\n", text, re.S | re.M).group(0)
    assert "check_site_url" in repair
    configure = re.search(r"^configure_env\(\) \{\n.*?^\}\n", text, re.S | re.M).group(0)
    assert "check_site_url" in configure
    assert '"http://localhost" FRONTEND_URL' not in configure
