# Container images

One image per toolchain family. Every toolchain reference is pinned: base image
digest, toolchain version + source URL + checksum, OpenOCD fork SHA.

## Pins (recorded 2026-10-09)

| Item | Pin | Evidence |
|---|---|---|
| Base | `debian:bookworm-slim@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587` | `docker pull debian:bookworm-slim` + `docker inspect` |
| ARM GNU | 15.3.rel2, `.../packages/generic/gnu-toolchain/15.3.rel2/arm-gnu-toolchain-15.3.rel2-x86_64-arm-none-eabi.tar.xz`, sha256 `0662b2f0…7874e` | README.md on `releases/15.3.rel2` branch lists generic-packages URLs; `.sha256asc` fetched via curl (full hash in Dockerfiles) |
| ARM branch head | `releases/15.3.rel2 = 601782f` | `git ls-remote --heads https://gitlab.arm.com/tooling/gnu-toolchains-for-arm.git` |
| OpenOCD fork | `c8d973bdad9a6fddb51459eda109b3b95d23b57a` (= HEAD of `openocd-cubeide-r7`, tag `openocd-cubeide-v2.2.0`) | `git ls-remote https://github.com/STMicroelectronics/OpenOCD.git` |
| Rust | 1.99.0 (`b940084d7 2026-09-28`) | `pkg.rust` version in `https://static.rust-lang.org/dist/channel-rust-stable.toml` |
| probe-rs | v0.32.0, `probe-rs-tools-x86_64-unknown-linux-gnu.tar.xz`, sha256 `c2ccc460…851ff5` | release asset `.sha256` fetched via curl |
| flip-link | 0.1.12 | `cargo install --locked --version 0.1.12` |
| rustup-init | sha256 `dda72343…c9fcb71` observed 2026-10-09 | `rustup-init.sha256` sidecar; Dockerfile verifies sidecar + recorded pin |

## Build

```sh
docker build --platform linux/amd64 -f images/cpp.Dockerfile  -t ghcr.io/randomgenericusername/lang-cpp:15.3.rel2 images/
docker build --platform linux/amd64 -f images/rust.Dockerfile -t ghcr.io/randomgenericusername/lang-rust:1.99.0 images/
docker inspect ghcr.io/randomgenericusername/lang-cpp:15.3.rel2  --format='{{.RepoDigests}}'
docker inspect ghcr.io/randomgenericusername/lang-rust:1.99.0    --format='{{.RepoDigests}}'
```
(Prefer `make images` / `make digests` — same commands, parameterized.)

Record the resulting digests here after each build (base-image updates change
them; re-record, do not silently float).

ESP-IDF (req-030, external pinned images):
- C/C++: `espressif/idf:v6.1 @ sha256:81893c71bb5e570088901f21def8684c25cd2a9020281bd01b843a7655edb18c`
- Rust: `espressif/idf-rust:esp32_1.95.0.0 @ sha256:1f90203f191cc94d7da1acf4da0e0e87aac128165115c1512f30668359f09dc6`
  (Rust 1.95 nightly, espflash 4.4.0, Xtensa GCC; `esp-idf-sys` downloads IDF v6.1)

Built digests (2026-10-09, `FROM --platform=linux/amd64`, Docker 29.8.2):
- cpp: `randomgenericusername/lang-cpp:15.3.rel2 @ sha256:27d29e05159fc71ddb6a2218de653ad401786cd81163cfcba86948642fa3a50d` (2.02GB, amd64).
- rust: `randomgenericusername/lang-rust:1.99.0 @ sha256:49e8cc060999644690541da88b20af3b5ad21c62d91d02da9af604348e0f0e2d` (amd64). Smoke: rustc 1.99.0 (b940084d7), probe-rs 0.32.0, thumbv7em (both) + thumbv6m targets, OpenOCD c8d973bda.
  Smoke: `rustc 1.99.0 (b940084d7)`, `thumbv7em-none-eabi`, `thumbv7em-none-eabihf`,
  `thumbv6m-none-eabi`, `probe-rs 0.32.0`, flip-link in cargo bin,
  OpenOCD `0.12.0+dev-00664-gc8d973bda`.

Note: `FromPlatformFlagConstDisallowed` lint warning on `FROM
--platform=linux/amd64` is intentional (x86_64-only toolchain tarballs) — keep.

## Pin audit

```sh
rg -i "latest|:stable" images/*.Dockerfile   # must print nothing (exit 1)
```

## CubeCLT — EXCLUDED by decision (vanilla wins); optional host tool

**Decided 2026-10-16 in `tickets/req-027-cubeclt-verdict/ticket.md`. Images ship
vanilla ARM GNU from the public gitlab host (no login, branch-pinned).** The
exclusion is a **practical** decision, *not* a legal prohibition.

1. **Redistribution is permitted, but conditional (SLA0048).** ST's licence
   allows binary redistribution provided you: reproduce the copyright,
   conditions of use and disclaimer **in capital type** in the distribution
   docs (clause 2); use it **solely** with ST processing units (clause 4); do
   **not** subject CubeCLT to Open Source Terms (clause 5); and note that a
   non-conforming redistribution is **void** (clause 11).
   Evidence: <https://www.st.com/resource/en/license/SLA0048_STM32CubeCLT.pdf>
   (st.com is unreachable from this net — read through a reader proxy, one
   hop; curl → HTTP `000` / error 92).
2. **It breaks the no-login reproducible build.** The installer requires
   *manual* licence acceptance and the download is MyST/email-gated with 24h
   links — incompatible with the pinned public fetch the images rely on.
3. **It adds no needed capability.** Its GCC (14.3) is *older* than the pinned
   vanilla 15.3.rel2 (`images/cpp.Dockerfile:7`); CubeCLT does **not** ship
   OpenOCD (the ST OpenOCD fork is still required); SVDs already come from
   modm-io (Apache-2.0, pinned). The only real gap — ST-LINK firmware update —
   is already a documented CubeProgrammer-GUI step
   (`docs/flash-stm32-linux.md:89`).

**If you ever bake CubeCLT into a public image**, you owe clause 2 (capital-type
reproduction in the image docs) and must honour clauses 4, 5 and 11.
Verify: `rg -n "CubeCLT|ARM_GCC_VERSION|OPENOCD_SHA" images/cpp.Dockerfile` →
no CubeCLT dependency; vanilla 15.3.rel2 + OpenOCD fork `c8d973b`.

**Optional host-side auxiliary:** CubeCLT may be installed on a *host* as a
diagnostics / ST-LINK-firmware tool. That is an end-user local install, not a
redistribution of our images, so it does not disturb the image terms.

## OPENs carried from spike-003

- [x] ARM 15.x checksums on new gitlab host — CLOSED: `.sha256asc` sidecar
      reachable via generic-packages API, hash recorded above.
- [ ] ARM sidebar T&Cs on new host — still OPEN (EULA.txt exists in branch;
      redistribution terms not reviewed).
- [x] CubeCLT version + SLA redistribution terms + download URL — RESOLVED
      2026-10-16 (req-027): CubeCLT **1.22.0**; SLA0048 permits redistribution
      *with conditions* (clauses 2/4/5/11 — capital-type notice, ST silicon
      only, not Open Source Terms, non-conforming = void);
      <https://www.st.com/resource/en/license/SLA0048_STM32CubeCLT.pdf>.
      Download is MyST/email-gated (24h links) — no stable public URL by
      design. Verdict: excluded from images (practical, not legal), optional
      as a host-side tool.

## Troubleshooting

- `mkdir /host_mnt/...: operation not permitted` on `-v` mounts: the checkout
  or project lives outside Docker Desktop's shared paths (Settings → Resources
  → File Sharing). Move the project under a shared path (e.g. `/tmp`) or add
  the parent dir. Verified 2026-10-13: `/tmp` shared, `~/Desktop` unshared on
  the dev machine.
- Fresh `create`d C projects need the CMSIS submodule (spike-002 vendoring,
  not yet wired into `create`): until then, builds fail on the missing
  `vendor/.../startup_*.s` — same documented interim as the e2e harness,
  which injects freestanding stubs.
