#!/usr/bin/env bash
# Verify that jenv, the Java runtime, and Maven all agree on the JDK version.
# Usage: bash verify-jenv.sh [project-dir]
#   project-dir: optional directory to check (defaults to current dir), so you can
#   verify a project's .java-version pin without cd-ing into it first.
set -u

DIR="${1:-$PWD}"
cd "$DIR" || { echo "verify-jenv: cannot cd to $DIR" >&2; exit 2; }

echo "Directory: $DIR"

# jenv's shell function may be absent in this non-interactive shell, so resolve the binary
# directly (Homebrew puts it on PATH; git installs put it under ~/.jenv/bin).
JENV_BIN=""
if command -v jenv >/dev/null 2>&1; then JENV_BIN="$(command -v jenv)"; fi
[ -z "$JENV_BIN" ] && [ -x "$HOME/.jenv/bin/jenv" ] && JENV_BIN="$HOME/.jenv/bin/jenv"

if [ -n "$JENV_BIN" ]; then
  echo "jenv: found ($JENV_BIN)"
  echo "jenv version: $("$JENV_BIN" version 2>&1)"
  echo "jenv which java: $("$JENV_BIN" which java 2>&1)"
  if [ -e "$HOME/.jenv/plugins/maven" ]; then
    echo "jenv maven plugin: enabled"
  else
    echo "jenv maven plugin: NOT enabled -> jenv enable-plugin maven; jenv rehash; restart shell"
  fi
else
  echo "jenv: NOT installed on this machine."
  echo "  Install (macOS):    brew install jenv"
  echo "  Wire into ~/.zshrc:  export PATH=\"\$HOME/.jenv/bin:\$PATH\"   and   eval \"\$(jenv init -)\""
  echo "  Restart shell, then: jenv enable-plugin export; jenv enable-plugin maven; jenv rehash"
  echo "  jenv manages installed JDKs only -> e.g. brew install openjdk@21, then jenv add <jdk-home>"
  echo "  (Skipping java/mvn comparison until jenv is set up.)"
fi

# Active JDK. java -version prints to stderr; capture the first line.
JAVA_LINE="$(java -version 2>&1 | head -1)"
echo "java -version: ${JAVA_LINE:-<java not found>}"
# Pull e.g. 21.0.10 out of: openjdk version "21.0.10" ...
JAVA_VER="$(printf '%s' "$JAVA_LINE" | sed -n 's/.*version "\([0-9][0-9.]*\).*/\1/p')"

# Maven's JDK — only meaningful when the jenv maven plugin is enabled.
if command -v mvn >/dev/null 2>&1; then
  MVN_JAVA_LINE="$(mvn -version 2>/dev/null | grep -i '^Java version:')"
  echo "mvn ${MVN_JAVA_LINE:-<no Java version line>}"
  MVN_VER="$(printf '%s' "$MVN_JAVA_LINE" | sed -n 's/.*[Jj]ava version: *\([0-9][0-9.]*\).*/\1/p')"
else
  echo "mvn: not found (skipping Maven check)"
  MVN_VER=""
fi

echo "---"
if [ -n "$JAVA_VER" ] && [ -n "$MVN_VER" ]; then
  if [ "$JAVA_VER" = "$MVN_VER" ]; then
    echo "OK: java ($JAVA_VER) and mvn ($MVN_VER) agree."
  else
    echo "MISMATCH: java is $JAVA_VER but mvn uses $MVN_VER."
    echo "  -> Enable the jenv maven plugin: jenv enable-plugin maven; jenv rehash; restart shell."
    echo "  -> Also check JAVA_HOME isn't hard-set in your shell rc."
    exit 1
  fi
else
  echo "NOTE: could not compare (missing java or mvn version)."
fi
