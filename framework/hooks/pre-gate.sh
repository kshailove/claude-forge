#!/bin/bash
# hooks/pre-gate.sh
# Validates that a stage produced a real artifact before presenting to human for review.

set -e

PROJECT=$1
STAGE=$2
ARTIFACT_PATH=$3

if [ -z "$PROJECT" ] || [ -z "$STAGE" ] || [ -z "$ARTIFACT_PATH" ]; then
  echo "Usage: pre-gate.sh <project> <stage> <artifact-path>"
  exit 1
fi

echo "🔍 Pre-gate validation: $STAGE"

# Check artifact exists
if [ ! -f "$ARTIFACT_PATH" ]; then
  echo "❌ Gate blocked: artifact not found at $ARTIFACT_PATH"
  echo "   Stage '$STAGE' must produce this file before the gate can open."
  exit 1
fi

# Check artifact is not empty
if [ ! -s "$ARTIFACT_PATH" ]; then
  echo "❌ Gate blocked: artifact is empty at $ARTIFACT_PATH"
  exit 1
fi

# Check artifact meets minimum length (avoid stub outputs)
WORD_COUNT=$(wc -w < "$ARTIFACT_PATH")
MIN_WORDS=100

if [ "$WORD_COUNT" -lt "$MIN_WORDS" ]; then
  echo "⚠️  Warning: artifact seems very short ($WORD_COUNT words). Expected at least $MIN_WORDS."
  echo "   Proceeding anyway — human reviewer should assess quality."
fi

echo "  ✅ Artifact validated: $ARTIFACT_PATH ($WORD_COUNT words)"
echo "  Opening for human review..."
