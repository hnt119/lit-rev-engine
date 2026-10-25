from pathlib import Path
import os
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def test_image_pins_runtime_and_builds_production_without_models():
    docker = (ROOT / "Dockerfile").read_text()
    assert docker.count("@sha256:") == 3
    assert "--frozen-lockfile" in docker and "pnpm build" in docker
    assert "pnpm prune --prod" in docker
    assert 'ENTRYPOINT ["python", "scripts/run_hosted.py"]' in docker
    assert "USER 10001:10001" in docker
    assert "next dev" not in docker and "huggingface" not in docker
    assert "COPY . " not in docker
    requirements = (ROOT / "requirements-hosted.txt").read_text()
    assert "streamlit==" not in requirements and "torch==" not in requirements


def test_context_is_allowlisted_and_no_private_trees_are_reincluded():
    rules = [line.strip() for line in (ROOT / ".dockerignore").read_text().splitlines() if line.strip() and not line.startswith("#")]
    assert rules[0] == "**"
    allowed = [line[1:] for line in rules if line.startswith("!")]
    assert not any(line.startswith((".git", ".env", ".mvp", "data/", "reports/", "workflow/", "tests/")) for line in allowed)
    assert {line for line in allowed if line.startswith('docs/')} == {'docs/', 'docs/local_preview_distribution_terms.md'}
    public = [line for line in allowed if line.startswith("examples/mvp/offline_microbiome_30_v1/")]
    assert public and all("*" not in line for line in public)
    assert "examples/mvp/offline_microbiome_30_v1/manifest.json" in allowed
    assert "examples/mvp/offline_microbiome_30_v1/README.md" in allowed
    assert "apps/streamlit/theme/tokens.css" in allowed
    assert "**/.env*" in rules and "**/*.sqlite*" in rules


def test_git_excludes_private_runtime_canaries(tmp_path):
    # A separate repository prevents developer/global excludes hiding a gap.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True, env=env)
    (tmp_path / ".gitignore").write_text((ROOT / ".gitignore").read_text())
    paths = [
        ".env.hosted.local", "src/mvp/admission.key", "src/mvp/tls.pem",
        "src/mvp/tls.crt", "src/mvp/tls.cer", "src/mvp/tls.p12", "src/mvp/tls.pfx",
        "src/mvp/research.sqlite3", "src/mvp/research.sqlite3-wal",
        "src/mvp/research.db", "src/mvp/research.db-shm",
        "src/mvp/backup.tar", "src/mvp/backup.tar.gz", "src/mvp/backup.tgz",
        "src/mvp/backup.bak", "backups/snapshot.json", "private-exports/review.csv",
        "browser-state/session.json", "model-cache/weights.json", ".hosted-state/session.json",
        "src/mvp/.cache/huggingface/hub/model.safetensors",
        "src/mvp/.huggingface/token", "src/mvp/model.gguf", "src/mvp/model.pt",
        "src/mvp/model.pth", "apps/web/lib/browser-state.json",
        "apps/web/lib/storage-state.json", "apps/web/lib/cookies.json",
        "apps/web/lib/private-cookie-jar.txt",
    ]
    for relative in paths:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("public synthetic canary\n")
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin"], cwd=tmp_path,
        input="\n".join(paths) + "\n", text=True, capture_output=True, env=env, check=True,
    )
    assert set(result.stdout.splitlines()) == set(paths)


def test_license_page_build_input_and_runtime_terms_are_explicitly_packaged():
    docker = (ROOT / 'Dockerfile').read_text()
    assert docker.index('COPY LICENSE /app/LICENSE') < docker.index('RUN pnpm build')
    assert 'COPY LICENSE THIRD_PARTY_NOTICES.md ./' in docker
    assert 'COPY docs/local_preview_distribution_terms.md ./DISTRIBUTION_TERMS.md' in docker
    rules = (ROOT / '.dockerignore').read_text().splitlines()
    for path in ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'docs/local_preview_distribution_terms.md'):
        assert (ROOT / path).is_file() and '!' + path in rules
