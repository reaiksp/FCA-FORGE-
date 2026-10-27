import io
import time
import zipfile

from fastapi.testclient import TestClient
import numpy as np
import soundfile as sf

from studio.app import app
from studio.paths import DATA


def test_upload_prepare_review_and_persist_without_training():
    buffer = io.BytesIO()
    rate = 8000
    sf.write(buffer, .15 * np.sin(2 * np.pi * 200 * np.arange(rate * 4) / rate), rate, format="WAV")
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        uploaded = client.post("/api/uploads", files=[("files", ("中文录音.wav", buffer.getvalue(), "audio/wav"))])
        assert uploaded.status_code == 200
        file = uploaded.json()[0]["file"]
        response = client.post("/api/jobs/prepare", json={"name": "中文素材", "files": [file], "clip_seconds": 2})
        assert response.status_code == 200
        job_id = response.json()["id"]
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            state = client.get("/api/state").json()
            job = next(j for j in state["jobs"] if j["id"] == job_id)
            if job["status"] in ("succeeded", "failed"):
                break
            time.sleep(.1)
        assert job["status"] == "succeeded", job
        dataset = next(d for d in state["datasets"] if d["id"] == job_id)
        assert len(dataset["clips"]) == 2
        included = [dataset["clips"][0]["file"]]
        edited = client.patch(f"/api/datasets/{job_id}", json={"included": included}).json()
        assert [x["included"] for x in edited["clips"]] == [True, False]
        assert client.get('/api/files/' + included[0]).status_code == 200
    with TestClient(app) as restarted:
        assert any(d["id"] == job_id for d in restarted.get('/api/state').json()["datasets"])


def test_origin_path_limits_and_validation():
    with TestClient(app) as client:
        assert client.post('/api/jobs/prepare', json={}, headers={"Origin": "https://untrusted.example"}).status_code == 403
        assert client.get('/api/files/..%2F..%2Fpyproject.toml').status_code == 404
        assert client.post('/api/jobs/train', json={"name": "x", "dataset_id": "../../outside"}).status_code == 422
        assert client.post('/api/jobs/cover', json={"source": "x", "voice_id": "a" * 32, "pitch": 99}).status_code == 422


def test_model_import_export_does_not_load_pickle():
    with TestClient(app) as client:
        uploaded = client.post('/api/uploads', files=[('files', ('model.pth', b'not-an-executable-checkpoint', 'application/octet-stream'))]).json()[0]
        imported = client.post('/api/voices/import', json={"name": "Imported", "model": uploaded['file']})
        assert imported.status_code == 200
        exported = client.get(f"/api/voices/{imported.json()['id']}/export")
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            assert set(archive.namelist()) == {'voice.json', 'model.pth'}


def test_professional_endpoints_missing_logs_and_cursor_validation():
    from studio.paths import write_json
    import uuid
    job_id = uuid.uuid4().hex
    write_json(DATA / 'jobs' / job_id / 'job.json', {
        'id': job_id, 'kind': 'train', 'request': {'epochs': 10, 'name': 'Telemetry fixture'},
        'status': 'succeeded', 'stage': 'done', 'created': 1, 'attempt': 1, 'artifacts': [],
    })
    with TestClient(app) as client:
        assert client.get('/api/state').json()['version'] == '0.2.0'
        assert client.get(f'/api/jobs/{job_id}/metrics').json()['status'] == 'waiting'
        first = client.get(f'/api/jobs/{job_id}/console').json()
        assert first['text'] == '' and first['exists'] is False
        assert client.get(f'/api/jobs/{job_id}/log').json() == {'text': ''}
        assert client.get(f'/api/jobs/{job_id}/console?cursor=-1').status_code == 422
        assert client.get('/api/jobs/not-a-real-job/metrics').status_code == 404
        path = DATA / 'jobs' / job_id / 'worker.log'
        path.write_bytes('开始\n'.encode('utf-8'))
        second = client.get(f'/api/jobs/{job_id}/console?cursor=0').json()
        assert second['text'] == '开始\n'
        with path.open('ab') as stream:
            stream.write('下一步\n'.encode('utf-8'))
        third = client.get(f'/api/jobs/{job_id}/console?cursor={second["cursor"]}').json()
        assert third['text'] == '下一步\n'
        assert client.get('/professional.js').status_code == 200
