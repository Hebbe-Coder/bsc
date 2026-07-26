from pathlib import Path


def test_authorized_studio_launcher_keeps_the_key_server_side():
    script = (Path("scripts") / "start_authorized_studio.ps1").read_text(
        encoding="utf-8"
    )

    assert "BSC_LOCAL_API_KEY" in script
    assert "BSC_VITE_API_PROXY_TARGET" in script
    assert "BSC_LOCAL_API_KEY is missing" in script
    assert "ConvertTo-Json -Compress" in script
    assert "localApiKey" not in script.split("ConvertTo-Json -Compress", 1)[1]
