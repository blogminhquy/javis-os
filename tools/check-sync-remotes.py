"""Validate fork identity without printing credentials from Git remote URLs."""
import subprocess
from urllib.parse import urlsplit


def matches_repository(url, repository):
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname == "github.com"
            and parsed.port in (None, 443)
            and parsed.path in (f"/{repository}", f"/{repository}.git")
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        return False


def main():
    for remote, repository in (
        ("origin", "kk311/javis-os"),
        ("upstream", "blogminhquy/javis-os"),
    ):
        result = subprocess.run(
            ["git", "remote", "get-url", remote], capture_output=True, text=True
        )
        if result.returncode or not matches_repository(result.stdout.strip(), repository):
            raise SystemExit(f"Unexpected {remote} repository; synchronization stopped.")


if __name__ == "__main__":
    main()
