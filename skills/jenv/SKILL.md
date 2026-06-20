---
name: jenv
description: >
  Use and verify jenv (the Java environment manager, like rbenv/pyenv but for the JDK)
  on this machine. Reach for this skill whenever Java or Maven version selection is in
  play: checking or switching the active JDK, pinning a version for a new or existing
  project, reading or writing a .java-version file, diagnosing a "wrong Java version" or
  JAVA_HOME problem, or confirming that Maven (mvn) actually runs under the intended JDK.
  Trigger even when the user never says the word "jenv" — phrases like "why is mvn using
  Java 17", "set this project to Java 21", "which JDK is active here", "java -version
  looks wrong", or "make sure the build uses the right Java" all belong here, because on
  this machine Java and Maven versions are managed exclusively by jenv. Also use it when
  jenv itself needs setting up — installing jenv on a new machine, wiring it into the
  shell, registering a JDK, or enabling its maven/export plugins. Prefer this skill over
  installing or switching JDKs by any other means.
---

# jenv

jenv selects which installed JDK is active per shell, per directory, or globally. It does
**not** download JDKs — it manages already-installed ones (Homebrew, SDKMAN, manual). The
golden rule: change the active Java through jenv, never by editing PATH or JAVA_HOME by
hand, so the machine stays in one consistent, reproducible state.

## Check jenv is installed first

Before relying on any jenv command, confirm it's actually present **and initialized in the
shell** — on a new machine it may be missing, or installed but not wired in (so `java`
isn't shimmed and version switching silently does nothing). Check, in order:

- `command jenv --version` — does the jenv binary exist at all? (`command` bypasses the
  shell function so this works even before init.)
- `jenv version` — if this errors with "command not found", jenv isn't initialized in this
  shell even if the binary is installed.
- `jenv which java` — should resolve under `~/.jenv/...`. If `which java` instead points at
  `/usr/bin/java` or a Homebrew path directly, the shims aren't active.

If jenv is missing or not initialized, set it up before doing anything else — don't fall
back to editing PATH/JAVA_HOME by hand, since that's exactly the inconsistency jenv exists
to prevent.

### Installing jenv (macOS / Homebrew)

1. Install the binary: `brew install jenv`
2. Wire it into the shell. For zsh add to `~/.zshrc` (bash: `~/.bash_profile`):
   - `export PATH="$HOME/.jenv/bin:$PATH"`
   - `eval "$(jenv init -)"`

   The `eval` line is the important one: it installs the shims and the `jenv` shell
   function. Without it `java` won't follow jenv's selection no matter what you set.
3. Start a new shell (or `source ~/.zshrc`) so init takes effect, then re-run the checks
   above.

jenv does **not** download JDKs — it only manages ones already on disk. Install at least
one (e.g. `brew install openjdk@21`) and register it so jenv can see it:
`jenv add /opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home`, then
`jenv rehash`. `jenv versions` should now list it.

### Enable the plugins jenv needs

Two plugins make jenv behave the way build tools expect. Enable them once — they print
shell code that `jenv` `eval`s, so run them in an interactive shell, then restart it:

- `jenv enable-plugin export` — keeps `JAVA_HOME` in sync with the active version. Maven,
  Gradle, IDEs, and many scripts read `JAVA_HOME` rather than the `java` shim, so without
  this they can silently use a different JDK than the one jenv selected.
- `jenv enable-plugin maven` — wraps `mvn` so it always runs under jenv's chosen JDK. This
  is what makes the `mvn -version` check below actually mean something.

Confirm both are active with `ls ~/.jenv/plugins` (enabled plugins are symlinks there).
`jenv doctor` then sanity-checks the whole installation — shims, `JAVA_HOME` export, and
plugin wiring — and is the best first stop when anything looks off.

## How version resolution works

jenv picks a version from the first source that applies, most specific first:

1. **Shell** — `JENV_VERSION` env var, set by `jenv shell <v>`. Lasts for the current
   shell session only.
2. **Local** — a `.java-version` file in the current directory or any parent. This is the
   per-project pin and the one that travels in git. Set with `jenv local <v>`.
3. **Global** — `~/.jenv/version`. The machine-wide default. Set with `jenv global <v>`.

`jenv version` always tells you both the active version *and which source it came from*,
which is the fastest way to understand surprising behavior (e.g. a stray `.java-version`
in a parent directory).

## Inspecting the current state

Run these to understand what's active before changing anything:

- `jenv version` — active version and where it's set from (shell / local / global).
- `jenv versions` — every version jenv knows about; the active one is marked with `*`.
- `jenv which java` — the real path the `java` shim resolves to right now.
- `java -version` — the JDK that actually runs (prints to stderr).

## Setting a version

- **New or existing project, pin it:** `jenv local 21` — writes/updates `.java-version`
  in the current directory. Commit this file so the project's Java version is explicit and
  shared. This is the default move when scaffolding a new Java/Maven project.
- **Machine default:** `jenv global 21`.
- **Just this shell, temporarily:** `jenv shell 21`.

Use the short alias (`21`) when you want "latest installed 21.x"; use a full version
(`21.0.10`) to pin exactly. `jenv versions` shows which aliases exist.

If a JDK is installed but jenv doesn't list it, register it:
`jenv add /path/to/jdk/Contents/Home` (macOS Homebrew JDKs live under
`/opt/homebrew/opt/openjdk@21/...` or `/Library/Java/JavaVirtualMachines/...`).

## Verifying — the part that actually matters

Setting a version is easy; the failure mode is *thinking* you set it while a build tool
quietly uses a different JDK. Verify both layers:

**1. Java itself.** Confirm the shim and the runtime agree:

- `jenv which java` should point under `~/.jenv/versions/<active>/...`
- `java -version` should report the version you expect

**2. Maven.** This only tells the truth if the jenv **maven plugin** is enabled (see
"Enable the plugins jenv needs" above). The plugin makes `mvn` honor jenv's selection by
running it under the chosen JDK. Confirm it's on with `ls ~/.jenv/plugins` — `maven`
should be listed. If it isn't, enable it (`jenv enable-plugin maven`, then `jenv rehash`
and restart the shell) before trusting `mvn -version`.

Then the ground-truth check:

- `mvn -version` — read the **`Java version:`** line. It must match `java -version`. If
  Maven reports a different JDK than jenv's active version, the plugin isn't taking effect
  (not enabled, shell not reloaded, or `JAVA_HOME` is being forced elsewhere).

A quick combined check is bundled as `scripts/verify-jenv.sh` — it prints the active jenv
version, the resolved Java, and Maven's JDK, and flags a mismatch. Run it with
`bash scripts/verify-jenv.sh` from the skill directory, or point it at a project dir as
the first argument.

## Troubleshooting

- **`jenv: command not found` in a script / non-interactive shell.** jenv is a shell
  function loaded from your profile, not a binary on PATH for every shell. The real binary
  is reachable as `command jenv` for plain subcommands, but the shell-mutating ones
  (`enable-plugin`, `shell`, `rehash`) need the function, i.e. an interactive/login shell.
- **`mvn` uses the wrong Java.** Almost always the maven plugin isn't active in the current
  shell. Enable it (above), `jenv rehash`, open a new shell, re-check `mvn -version`. Also
  check that no `JAVA_HOME` is hard-set in `~/.zshrc`/`~/.bashrc` overriding jenv.
- **A version you installed isn't listed.** `jenv add <jdk-home>`, then `jenv rehash`.
- **General health check.** `jenv doctor` reports whether the jenv shims, JAVA_HOME export,
  and plugins are wired correctly — start here when behavior is confusing.

## Why this matters

Java projects break in subtle ways when the compile-time and run-time JDKs disagree, or
when CI uses a different version than the developer's machine. jenv plus a committed
`.java-version` makes the intended version explicit and reproducible; verifying through
`mvn -version` (not just `java -version`) closes the gap where the build tool silently
disagrees with the shell.
