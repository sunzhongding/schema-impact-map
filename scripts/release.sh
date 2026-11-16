#!/usr/bin/env bash
# Release helper for schema-impact-map.
#
#   scripts/release.sh --check      # validate the release, change nothing (default)
#   scripts/release.sh --tag        # run tests, tag v<version>, push the tag
#   scripts/release.sh --release    # --tag, then open the GitHub release
#
# The version is read from src/schema_impact_map/__init__.py so the package and
# the tag cannot drift apart. Pushing the tag publishes nothing: the publish
# workflow only runs when a GitHub release is published.
#
# Environment:
#   PYTHON        interpreter for tests and JSON (default: .venv/bin/python, then python3)
#   GITHUB_TOKEN  optional; used to create the release when the gh CLI is absent
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

usage() {
  awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "${BASH_SOURCE[0]}"
}

MODE="check"
for arg in "$@"; do
  case "$arg" in
    --check) MODE="check" ;;
    --tag) MODE="tag" ;;
    --release) MODE="release" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $arg (try --help)" >&2; exit 2 ;;
  esac
done

say() { printf '%s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

command -v git >/dev/null || die "git is not installed"

PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  if [ -x "$ROOT/.venv/bin/python" ]; then PYTHON="$ROOT/.venv/bin/python"; else PYTHON="python3"; fi
fi
command -v "$PYTHON" >/dev/null || die "$PYTHON is not available (set PYTHON=...)"

VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' src/schema_impact_map/__init__.py)"
[ -n "$VERSION" ] || die "cannot read __version__ from src/schema_impact_map/__init__.py"
TAG="v$VERSION"

# --- checks -----------------------------------------------------------------
[ "$(git rev-parse --is-inside-work-tree 2>/dev/null)" = "true" ] || die "not a git repository"

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
[ "$BRANCH" = "main" ] || die "release from main (current branch: $BRANCH)"

if [ -n "$(git status --porcelain)" ]; then
  git status --short >&2
  die "working tree is not clean; commit or stash first"
fi

git fetch --quiet --tags origin main
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse origin/main)"
[ "$LOCAL" = "$REMOTE" ] || die "local main ($LOCAL) is not origin/main ($REMOTE); pull or push first"

if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  die "tag $TAG already exists locally"
fi
if git ls-remote --exit-code --tags origin "refs/tags/$TAG" >/dev/null 2>&1; then
  die "tag $TAG already exists on origin"
fi

NOTES="$(awk -v header="## $VERSION" '
  $0 == header { capture = 1; next }
  capture && /^## / { exit }
  capture { print }
' CHANGELOG.md)"
printf '%s' "$NOTES" | grep -q . || die "CHANGELOG.md has no '## $VERSION' section"

SLUG="$(git remote get-url origin | awk -F'[:/]' '{print $(NF-1)"/"$NF}' | sed 's/\.git$//')"
say "release: $TAG"
say "commit:  $(git log -1 --format='%h %s')"
say "repo:    $SLUG"
say "notes:   $(printf '%s\n' "$NOTES" | grep -c .) non-empty lines from CHANGELOG.md"

if [ "$MODE" = "check" ]; then
  say ""
  say "--check passed; nothing was changed."
  say "next: scripts/release.sh --tag   (then --release once PyPI is configured)"
  exit 0
fi

# --- tests ------------------------------------------------------------------
"$PYTHON" -c "import pytest" >/dev/null 2>&1 \
  || die "$PYTHON has no pytest; run: $PYTHON -m pip install -e \".[dev]\""
say ""
say "running tests with $PYTHON"
"$PYTHON" -m pytest -q

# --- tag --------------------------------------------------------------------
git tag -a "$TAG" -m "schema-impact-map $VERSION"
git push origin "$TAG"
say ""
say "pushed $TAG (commit $(git rev-parse "$TAG^{commit}" | cut -c1-7))"

if [ "$MODE" = "tag" ]; then
  say ""
  say "nothing published yet: publish.yml runs on a published GitHub release."
  say "next: scripts/release.sh --release"
  exit 0
fi

# --- GitHub release ---------------------------------------------------------
RELEASE_TITLE="schema-impact-map $VERSION"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
{
  printf '## What changed\n\n%s\n\n' "$NOTES"
  printf '## Try it\n\n```bash\nuv tool install "schema-impact-map[mcp]"\nschema-impact-map demo\nopen site/index.html\n```\n\n'
  printf 'Full changelog: https://github.com/%s/blob/main/CHANGELOG.md\n' "$SLUG"
} >"$TMP"

if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  gh release create "$TAG" --title "$RELEASE_TITLE" --notes-file "$TMP"
  say "release created; the publish workflow is triggered"
  exit 0
fi

if [ -n "${GITHUB_TOKEN:-}" ]; then
  PAYLOAD="$("$PYTHON" - "$TAG" "$RELEASE_TITLE" "$TMP" <<'PY'
import json, pathlib, sys
tag, title, path = sys.argv[1:4]
print(json.dumps({
    "tag_name": tag,
    "name": title,
    "body": pathlib.Path(path).read_text(),
    "draft": False,
    "prerelease": False,
}))
PY
)"
  RESPONSE="$(curl -sS -X POST \
    -H "Authorization: Bearer $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/$SLUG/releases" \
    --data "$PAYLOAD")"
  case "$RESPONSE" in
    *'"html_url"'*)
      say "release created: $(printf '%s' "$RESPONSE" | "$PYTHON" -c 'import json,sys; print(json.load(sys.stdin)["html_url"])')"
      ;;
    *)
      die "GitHub API said: $RESPONSE"
      ;;
  esac
  exit 0
fi

say ""
say "tag pushed, but there is no gh CLI and no GITHUB_TOKEN, so the release is still missing."
say "do one of:"
say "  1. install gh (brew install gh; gh auth login) and rerun: scripts/release.sh --release"
say "  2. open https://github.com/$SLUG/releases/new?tag=$TAG and publish"
say "  3. export GITHUB_TOKEN=... and rerun: scripts/release.sh --release"
say ""
say "only a published release triggers .github/workflows/publish.yml (PyPI)."
