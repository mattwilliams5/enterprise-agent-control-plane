#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SHA="$(git rev-parse HEAD)"
GIT_DIR="$(git rev-parse --absolute-git-dir)"
OUT="$GIT_DIR/storeguard-build/one-trigger/$SHA"

# Require the build definition to exist in Git.
for file in Dockerfile requirements.txt vault.crt; do
  git cat-file -e \
    "HEAD:deployments/storeguard/one-trigger/$file" \
    || {
      echo "STOP: $file is not committed"
      exit 1
    }
done

# Reject recognizable private-key or environment files.
if git ls-tree -r --name-only HEAD -- \
    applications policy identity registry \
  | grep -E '(^|/)(\.env(\.|$)|id_rsa$)|\.(pem|key|p12|pfx|ed25519)$'; then
  echo "STOP: Potential private credentials in tracked build inputs"
  exit 1
fi

if [ -e "$OUT" ]; then
  echo "STOP: Build context already exists: $OUT"
  exit 1
fi

mkdir -p "$OUT"

# Export only committed Git source.
git archive HEAD -- \
  applications \
  policy \
  identity \
  registry \
  deployments/storeguard/one-trigger \
  | tar -xf - -C "$OUT"

BUILD="$OUT/deployments/storeguard/one-trigger"

cp "$BUILD/Dockerfile" "$OUT/Dockerfile"
cp "$BUILD/requirements.txt" "$OUT/requirements.txt"
cp "$BUILD/vault.crt" "$OUT/vault.crt"

openssl x509 -in "$OUT/vault.crt" -noout >/dev/null

printf '%s\n' "$SHA" > "$OUT/BUILD_SOURCE_COMMIT"

echo "PASS: Build context assembled from committed Git source"
echo "Source commit: $SHA"
echo "Build context: $OUT"
echo "NOTE: No cloud build or deployment performed"
