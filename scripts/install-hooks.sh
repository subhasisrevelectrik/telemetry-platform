#!/bin/bash
# Install git pre-commit hook that scans staged files for secrets.
# Run once after cloning: bash scripts/install-hooks.sh

set -e

HOOK_PATH=".git/hooks/pre-commit"

mkdir -p .git/hooks

cat > "$HOOK_PATH" << 'HOOK'
#!/bin/bash
# Pre-commit secret scanner — installed by scripts/install-hooks.sh

echo "Scanning staged files for secrets..."

STAGED=$(git diff --cached --diff-filter=ACM -U0)

# AWS Access Key ID pattern
if echo "$STAGED" | grep -qE "AKIA[0-9A-Z]{16}"; then
    echo ""
    echo "ERROR: AWS Access Key ID detected in staged changes!"
    echo "Remove the key and use 'aws login' or environment variables instead."
    exit 1
fi

# AWS Secret Access Key / generic secret assignments
if echo "$STAGED" | grep -qiE "(aws_secret_access_key|aws_secret_key)\s*[=:]\s*['\"]?[A-Za-z0-9/+=]{20,}"; then
    echo ""
    echo "ERROR: AWS Secret Access Key detected in staged changes!"
    echo "Remove the secret and use 'aws login' or environment variables instead."
    exit 1
fi

# Generic hardcoded secret patterns (high-confidence only)
if echo "$STAGED" | grep -qiE "password\s*=\s*['\"][^'\"]{8,}['\"]"; then
    echo ""
    echo "WARNING: Possible hardcoded password detected in staged changes."
    echo "If this is a test fixture with a placeholder value, you can proceed."
    echo "Otherwise, remove it and use environment variables."
    read -p "Proceed with commit? (y/N): " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        exit 1
    fi
fi

echo "Secret scan passed. Proceeding with commit."
HOOK

chmod +x "$HOOK_PATH"
echo "Pre-commit hook installed at $HOOK_PATH"
echo "It will scan staged files for AWS keys and secrets before every commit."
