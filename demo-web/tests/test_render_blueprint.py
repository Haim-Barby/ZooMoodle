from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_render_blueprint_is_a_free_python_web_service():
    text = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "name: zoomoodle" in text
    assert "runtime: python" in text
    assert "plan: free" in text
    assert "rootDir: demo-web" in text
    assert "buildCommand: pip install -r requirements.txt" in text
    assert 'startCommand: python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers 1' in text
    assert "healthCheckPath: /api/health" in text
    assert "autoDeploy: true" in text
    assert "autoDeployTrigger: commit" in text
    assert "branch: main" in text
    assert "generateValue: true" in text
    assert text.count("generateValue: true") >= 2
    assert "ZOOMODLE_MASTER_SECRET" in text
    assert "ZOOMODLE_LECTURER_KEY" in text
    assert "ZOOMODLE_CAMPUS_RANGES" in text
    assert "192.114.48.0/21,192.114.56.0/23" in text
    assert 'value: "*"' not in text and "value: '*'" not in text
    assert "FORWARDED_ALLOW_IPS" in text
    assert 'value: "127.0.0.1"' in text
    assert "databases:" not in text
    assert "disk:" not in text
    version = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    assert version == "3.12.8"
    assert "3.12.8" in text
