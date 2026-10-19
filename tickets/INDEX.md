# Ticket index

> Counting rule: completeness checks cover item files (`tickets/<id>-<slug>/ticket.md`) only.
> `tickets/_template/` (and any `tickets/_fixtures/`) are excluded from INDEX completeness counting.
> Entry format: link — title | `status` | execution links. Epics add `done/total children done`, done-when, and one nested line per child. Bugs add severity. Spikes add timebox state.

## Epics

- [epic-001-universal-framework](./epic-001-universal-framework/epic.md) — Universal MCU dev framework | `done` | 31/31 children done | done-when: V1 matrix (3 packs x 3 langs, OpenOCD) completes create-build-flash-run from clean machines per pack proof rituals | exec: bmad brief+spec+spine
  - [bug-001-xor-probe-selectors](./bug-001-xor-probe-selectors/ticket.md) — XOR rejects probe selectors combined with --mcu-config | `done`
  - [bug-002-rust-panic-abort](./bug-002-rust-panic-abort/ticket.md) — Rendered Rust projects fail to compile (unwinding panics) | `done`
  - [req-001-product-brief](./req-001-product-brief/ticket.md) — Product brief for universal MCU dev framework | `done`
  - [req-002-distill-spec](./req-002-distill-spec/ticket.md) — Distill spec from finalized brief | `done`
  - [req-003-engine-core](./req-003-engine-core/ticket.md) — Engine core + model validation | `done`
  - [req-004-pack-schema](./req-004-pack-schema/ticket.md) — Pack frame schema + 3 STM32 packs | `done`
  - [req-005-cli-verbs](./req-005-cli-verbs/ticket.md) — Thin CLI verbs + shim | `done`
  - [req-006-probe-adapters](./req-006-probe-adapters/ticket.md) — Probe adapters OpenOCD (+ probe-rs second) | `done`
  - [req-007-container-images](./req-007-container-images/ticket.md) — Container images per toolchain + caches | `done`
  - [req-008-template-generation](./req-008-template-generation/ticket.md) — Project template generation from packs | `done`
  - [req-009-e2e-build-proof](./req-009-e2e-build-proof/ticket.md) — End-to-end build proof in images | `done`
  - [req-010-flash-log-streaming](./req-010-flash-log-streaming/ticket.md) — Streamed flash/debug tool output (+ --verbose) | `done`
  - [req-011-submodule-vendoring](./req-011-submodule-vendoring/ticket.md) — Vendor CMSIS submodules into created projects | `done`
  - [req-012-openocd-probe-wiring](./req-012-openocd-probe-wiring/ticket.md) — OpenOCD config paths + USB probe binding so stm flash programs | `done`
  - [req-014-mcu-example](./req-014-mcu-example/ticket.md) — Per-MCU example: generated blink (F411RE implemented, others stub) | `done`
  - [req-015-h755-example](./req-015-h755-example/ticket.md) — H755 blink example (LD2/PE1, family-correct registers, primary core) | `done`
  - [req-016-vscode-integration](./req-016-vscode-integration/ticket.md) — Generated .vscode/ for the container-attached debug flow (C/C++ first) | `done`
  - [req-017-svd-registers](./req-017-svd-registers/ticket.md) — Per-core SVD fetch -> Cortex-Debug peripheral register view | `done`
  - [req-018-detach-resume](./req-018-detach-resume/ticket.md) — Keep firmware running after debug: resume-on-detach config | `done`
  - [req-019-dev-probe](./req-019-dev-probe/ticket.md) — mu dev accepts probe selectors (dev container gets the probe) | `done`
  - [req-020-probe-autodetect](./req-020-probe-autodetect/ticket.md) — Auto-detect a single attached probe (no --vid/--pid needed) | `done`
  - [spike-001-openocd-targets](./spike-001-openocd-targets/ticket.md) — Per-pack OpenOCD target verification | `done`
  - [spike-002-cpp-deps](./spike-002-cpp-deps/ticket.md) — C/C++ dependency mechanism | `done`
  - [spike-003-toolchain-recon](./spike-003-toolchain-recon/ticket.md) — 2026 toolchain recon | `done`
  - [spike-004-config-headers](./spike-004-config-headers/ticket.md) — Per-project config-header flow (lwipopts.h-style) | `done`
  - [task-001-adopt-split-decompose](./task-001-adopt-split-decompose/ticket.md) — Adopt spine, validate, decompose epic | `done`
  - [task-002-wire-create-renderer](./task-002-wire-create-renderer/ticket.md) — Wire create renderer | `done`
  - [task-003-container-argv-fix](./task-003-container-argv-fix/ticket.md) — Container argv invokes build tool, not stm | `done`
  - [task-004-narrow-mounts](./task-004-narrow-mounts/ticket.md) — Narrow container mounts to engine + packs | `done`
  - [task-005-probe-default-proof-precheck](./task-005-probe-default-proof-precheck/ticket.md) — Pack-default probe, proof wiring, image pre-check | `done`
  - [task-006-backend-settings](./task-006-backend-settings/ticket.md) — Per-backend pack settings (probe chip strings etc.) | `done`

- [epic-002-post-v1](./epic-002-post-v1/epic.md) — Post-V1 roadmap | `proposed` | 3/5 children done | done-when: every post-V1 track shipped or declined | exec: BMAD advisory
  - [req-024-dep-integration](./req-024-dep-integration/ticket.md) — C/C++ dependency integration (Conan 2 / CPM) | `proposed`
  - [req-025-windows-lane](./req-025-windows-lane/ticket.md) — Windows native lane | `proposed`
  - [req-026-wl55-cm0p-bringup](./req-026-wl55-cm0p-bringup/ticket.md) — WL55JC CM0+ dual-core bring-up | `done`
  - [req-027-cubeclt-verdict](./req-027-cubeclt-verdict/ticket.md) — STM32CubeCLT verdict | `done`
  - [req-028-rust-dual-core](./req-028-rust-dual-core/ticket.md) — Rust dual-core parity: plan-driven template families | `done` | openspec: req-028-rust-dual-core

## Requirements

(covered under epic-001 above; standalone entries appear here only for items without a parent epic)

- [req-021-arch-separation](./req-021-arch-separation/ticket.md) — Architecture separation: pack-declared build stack + split probe ports | `done` | bmad-advisory, spine AD-8 amended + AD-11…AD-17; pre-ESP32 refactor gate; follow-ups ticketed
- [req-022-esp32-family](./req-022-esp32-family/ticket.md) — ESP32 family support (first non-STM32 device) | `done` | bmad-advisory | 4/4 children done | post-V1 generality proof; live proof ops-024
- [req-023-ad15-refinement](./req-023-ad15-refinement/ticket.md) — Reconcile AD-15 with the R5 verify implementation | `done` | bmad-advisory | spine wording fix, lint clean
- [req-024-dep-integration](./req-024-dep-integration/ticket.md) — C/C++ dependency integration (Conan 2 / CPM) | `proposed` | bmad-advisory, parent epic-002 | post-V1 (spike-002); Conan ecosystem measured empty
- [req-025-windows-lane](./req-025-windows-lane/ticket.md) — Windows native lane | `proposed` | bmad-advisory, parent epic-002 | deferred, not designed out
- [req-026-wl55-cm0p-bringup](./req-026-wl55-cm0p-bringup/ticket.md) — WL55JC CM0+ dual-core bring-up | `done` | bmad-advisory, parent epic-002 | CM0+ boots+runs (counter 0x2000C01C advances); `make debug-m0plus` attach path; bug-027 stays open
- [req-027-cubeclt-verdict](./req-027-cubeclt-verdict/ticket.md) — STM32CubeCLT verdict | `done` | bmad-advisory, parent epic-002 | VERDICT: exclude from images, optional host tool (SLA0048 permitted-with-conditions)

## Bugs

- [bug-001-xor-probe-selectors](./bug-001-xor-probe-selectors/ticket.md) — XOR rejects probe selectors combined with --mcu-config | `done` | S1, INDIVIDUAL_FLAGS narrowed
- [bug-002-rust-panic-abort](./bug-002-rust-panic-abort/ticket.md) — Rendered Rust projects fail to compile | `done` | S1, panic=abort, ARM ELFs proven
- [bug-003-openocd-config-path-prefix](./bug-003-openocd-config-path-prefix/ticket.md) — OpenOCD adapter renders unprefixed config paths (Can't find stlink.cfg) | `done` | S1, openspec: req-012
- [bug-004-probe-usb-passthrough](./bug-004-probe-usb-passthrough/ticket.md) — stm flash container receives serial tty, not the ST-Link USB device | `done` | S1, openspec: req-012
- [bug-005-relative-path-vendor](./bug-005-relative-path-vendor/ticket.md) — create fails with a relative project dir (git -C doubles the path) | `done` | S1
- [bug-006-multi-piece-flash](./bug-006-multi-piece-flash/ticket.md) — Multi-piece flash drops pieces / exits non-zero (dual-core) | `done` | S1
- [bug-007-verbose-forward](./bug-007-verbose-forward/ticket.md) — --verbose ignored in auto mode (no log file) | `done` | S2
- [bug-008-wl55-memory](./bug-008-wl55-memory/ticket.md) — WL55JC pack memory map wrong (RAM 128K vs real 64K) -> HardFault | `done` | S1
- [bug-009-detach-targets](./bug-009-detach-targets/ticket.md) — resume-on-detach cfg breaks the H7 server (undefined _TARGETNAME) | `done` | S1
- [bug-010-build-probe-gate](./bug-010-build-probe-gate/ticket.md) — mu build broken: probe auto-detect forwards --device to build | `done` | S1
- [bug-011-h7-single-step](./bug-011-h7-single-step/ticket.md) — OpenOCD never single-steps the H755 (PC frozen): mask interrupts during step | `done` | S1, consumes spike-005
- [bug-012-vscode-maskisr-gate](./bug-012-vscode-maskisr-gate/ticket.md) — Generated launch.json emits cortex_m maskisr for non-Cortex-M packs | `done` | S3, gates bug-011
- [bug-013-dual-core-debug](./bug-013-dual-core-debug/ticket.md) — Generated M4 launch config attaches to the M7 core (no per-core targeting) | `done` | S2, per-core targetProcessor + chained dual-core config
- [bug-014-dual-core-ram](./bug-014-dual-core-ram/ticket.md) — Dual-core packs link both cores into one RAM region (same _estack) -> M7 hard-faults | `done` | S1, per-core memory regions
- [bug-015-blink-rate](./bug-015-blink-rate/ticket.md) — Generated blink runs ~29 Hz (delay formula 3x off) — LED looks steady, not blinking | `done` | S2
- [bug-016-hla-maskisr-gate](./bug-016-hla-maskisr-gate/ticket.md) — HLA targets (stlink.cfg) reject `cortex_m maskisr` -> F411 debug launch fails | `done` | S1
- [bug-017-login-shell-path](./bug-017-login-shell-path/ticket.md) — Image /etc/profile resets PATH -> login shells (VS Code tasks) lose the toolchain (Error 127) | `done` | S2, needs image rebuild
- [bug-018-usb-bus-binding](./bug-018-usb-bus-binding/ticket.md) — Containers bind a USB node number -> a replug breaks them (GDB Server Quit Unexpectedly) | `done` | S2, whole-bus mount + serial selection
- [bug-019-cli-test-isolation](./bug-019-cli-test-isolation/ticket.md) — CLI tests depend on the host USB bus (fail when more than one probe is attached) | `done` | S3
- [bug-020-dockerfile-layer-order](./bug-020-dockerfile-layer-order/ticket.md) — bug-017's profile.d RUN sits before the toolchain layers -> every image rebuild is a full rebuild | `done` | S3
- [bug-021-wl55-dual-core](./bug-021-wl55-dual-core/ticket.md) — WL55JC dual-core: HLA hides the CM0+, both cores share flash, M0+ arch wrong, CPU2 never released | `done` | S2, M4 verified; CM0+ -> spike-006
- [bug-022-mount-preflight](./bug-022-mount-preflight/ticket.md) — Unshared Docker mount paths fail with raw daemon error (no preflight, no hint) | `done` | S3, probe + tee fallback, 276/276 tests, live repro proven
- [bug-023-sibling-attach](./bug-023-sibling-attach/ticket.md) — WL55JC: released sibling can't be launched, primary's reset hides it, flash order boots it into an unflashed image | `done` | S2, M4+CM0+ run; compound sequence fragile
- [bug-024-no-reset-for-released-siblings](./bug-024-no-reset-for-released-siblings/ticket.md) — cortex-debug launch fails on a released-sibling pack: 'monitor reset halt' errors (Protocol error with Rcmd) | `done` | S1, attach-only for cpu2_boot packs
- [bug-025-rust-build-target](./bug-025-rust-build-target/ticket.md) — mu build for Rust omits --target: compiles for the host and fails to link | `done` | S1, render .cargo/config.toml + README fix; 355 tests
- [bug-026-linker-init-array](./bug-026-linker-init-array/ticket.md) — Generated linker script drops .init_array, so the sibling-release constructor is discarded (WL55 CM0+ never runs) | `done` | S1, init_array/fini_array + PROVIDE_HIDDEN symbols; release ctor back in the ELF; 357 tests
- [bug-029-cm0p-released-not-running](./bug-029-cm0p-released-not-running/ticket.md) — CM0+ is released (C2BOOT=0x8000) but still does not run — sibling counter stays 0 | `rejected` | measurement error: probed 0x2000C000 (completed.1); real counter 0x2000C01C advances — bug-026 fix is complete
- [bug-030-m0plus-attach-path](./bug-030-m0plus-attach-path/ticket.md) — WL55JC flash path never creates stm32wlx.cpu1; no generated way to attach the M0+ after make flash | `done` | S2, generated `make debug-m0plus` (attach-only, no reset); pc in M0+ main loop verified on HW
- [bug-031-cpu2boot-masks-bug027](./bug-031-cpu2boot-masks-bug027/ticket.md) — probe/cpu2-boot.cfg writes C2BOOT on examine-end, masking bug-027 and invalidating sibling-release measurements | `done` | S3, cfg removed from the render path; C2BOOT now tracks the running CM0+ exactly (6/10)
- [bug-032-cpp-sibling-boot-check](./bug-032-cpp-sibling-boot-check/ticket.md) — C++ WL55 `flash-M0+` prints a false `DID NOT BOOT` (sibling not released yet) | `triage` | S3, sibling boot check must be omitted; Rust family already does
- [bug-027-intermittent-reset-boot](./bug-027-intermittent-reset-boot/ticket.md) — M4 app starts only ~2/6 times after an OpenOCD reset (sits in ROM at 0x1fff2cc0) | `done` | S2, debugger-reset-only (physical 20/20); verify-and-retry fix: flash reliability 5/10 -> 20/20
- [bug-028-cpu2boot-cfg-premise](./bug-028-cpu2boot-cfg-premise/ticket.md) — cpu2-boot.cfg asserts a false premise (CPU2 clears C2BOOT) and clobbers PWR_CR4 | `done` | S3, masked `mmw` + correct C2BOOT premise; 357 tests, no hw re-flash needed

## Ops tasks

- [ops-007-make-commands](./ops-007-make-commands/ticket.md) — Make commands for fresh-clone rebuild | `done` | exec: direct
- [ops-008-closeouts-fallback-docs](./ops-008-closeouts-fallback-docs/ticket.md) — Spike close-outs, linker fallback removal, user README | `done`
- [ops-009-install-cli](./ops-009-install-cli/ticket.md) — Installable stm CLI (make install / uninstall) | `done`
- [ops-010-rename-cli-mu](./ops-010-rename-cli-mu/ticket.md) — Rename CLI command stm -> mu (device-agnostic) | `done`
- [ops-011-full-rename-mu](./ops-011-full-rename-mu/ticket.md) — Full rename to mu (repo, package, paths, image namespace) | `done`
- [ops-012-create-path-flag](./ops-012-create-path-flag/ticket.md) — create: rename output flag to --path | `done`
- [ops-013-create-git-init](./ops-013-create-git-init/ticket.md) — create: git-init a fresh project dir before vendoring | `done`
- [ops-014-sparse-vendor](./ops-014-sparse-vendor/ticket.md) — Vendoring: partial+sparse clone (create in seconds, not minutes) | `done`
- [ops-015-organized-tree](./ops-015-organized-tree/ticket.md) — Organize generated project tree (probe/ + build/<core>/) | `done`
- [ops-016-project-gitignore](./ops-016-project-gitignore/ticket.md) — Generated projects ship a .gitignore (build/, .mu/) | `done`
- [ops-017-wl55-example](./ops-017-wl55-example/ticket.md) — WL55JC blink example (LD1/PB15) | `done`
- [ops-018-sibling-core-example](./ops-018-sibling-core-example/ticket.md) — Sibling-core example: debuggable counter loop instead of a wfi stub | `done`
- [ops-019-vscode-debug-docs](./ops-019-vscode-debug-docs/ticket.md) — Document the VS Code debug flow (docs/vscode-debug.md) | `done`
- [ops-020-clean-test-doc](./ops-020-clean-test-doc/ticket.md) — Document the clean from-zero test (docs/vscode-debug.md §9) | `done`
- [ops-021-project-readme](./ops-021-project-readme/ticket.md) — Generated project README.md (each project documents its own flow) | `done`
- [ops-022-f5-prelaunch](./ops-022-f5-prelaunch/ticket.md) — F5 = build + flash + debug (preLaunchTask in the generated launch configs) | `done`
- [ops-023-e2e-matrix](./ops-023-e2e-matrix/ticket.md) — Record the full e2e matrix (10 cells, both families) | `done` | 10/10 green, evidence recorded
- [ops-024-esp32-live-proof](./ops-024-esp32-live-proof/ticket.md) — Record the live ESP32-CAM proof: containerized flash + boot log | `done` | 3/3 pieces, boot log + app output captured
- [ops-025-monitor-port-note](./ops-025-monitor-port-note/ticket.md) — Document that a running monitor owns the serial port | `done` | README + test
- [ops-026-esp32-wrapup](./ops-026-esp32-wrapup/ticket.md) — ESP32-CAM wrap-up: final state + prune merged branches | `done` | req-022 §Final state; origin pruned
- [ops-027-wl55-clean-run](./ops-027-wl55-clean-run/ticket.md) — WL55JC clean-from-zero flash/run ritual + CM0+ scope | `done` | M4 LED proven (ODR readback); CM0+ = limitation (spike-006)
- [ops-028-flash-run-evidence](./ops-028-flash-run-evidence/ticket.md) — Record a flash-run evidence artifact for the V1 packs | `done` | docs/flash-run-evidence.md (3 packs)
- [ops-029-epic-closeout](./ops-029-epic-closeout/ticket.md) — epic-001 closeout: reconcile children, rollup checklist, flip to done | `done` | 31/31 children, epic-001 done
- [ops-030-image-distribution](./ops-030-image-distribution/ticket.md) — Confirm image distribution for a clean machine (registry push state) | `done` | images pushed to ghcr (auth-required); login or `make images`
- [ops-031-req022-closeout](./ops-031-req022-closeout/ticket.md) — Close req-022 (ESP32 family) and mark spike-007 consumed | `done` | drift close-out
- [ops-032-rust-spec-wording](./ops-032-rust-spec-wording/ticket.md) — Amend the spec success signal for the Rust build-parity decision | `done` | spec §Success signal + CAP-3 + device-matrix:3 amended (dated); spike-008 reconciled
- [ops-033-warnings-policy](./ops-033-warnings-policy/ticket.md) — Formalize the compiler-warnings policy | `done` | warn-only confirmed; policy in docs/warnings-policy.md; HANDOFF thread closed
- [ops-034-registry-visibility](./ops-034-registry-visibility/ticket.md) — Decide GHCR image package visibility (public vs auth-required) | `done` | decided: keep PRIVATE; docs already match (auth-required)
- [ops-035-triage-findings](./ops-035-triage-findings/ticket.md) — Triage the two dispatched investigations; file the resulting bugs/verdict | `done` | filed bug-026/027/028 + req-027 verdict
- [ops-036-close-bug026-file-bug029](./ops-036-close-bug026-file-bug029/ticket.md) — Close bug-026 (verified + merged); file the residual as bug-029 | `done` | bug-026 verified on a fresh project; residual filed
- [ops-037-bug029-reject-file-new-bugs](./ops-037-bug029-reject-file-new-bugs/ticket.md) — Reject bug-029 (measurement error); record the spike-006 correction; file bug-030/031 | `done` | CM0+ runs at 0x2000C01C; bug-026 fix complete
- [ops-038-close-bug030-031-026](./ops-038-close-bug030-031-026/ticket.md) — Close bug-030/bug-031/req-026 (fixes merged + verified); recount epic-002 | `done` | 360 tests; `make debug-m0plus` verified on HW
- [ops-039-fix-index-epic001-line](./ops-039-fix-index-epic001-line/ticket.md) — Repair INDEX corruption (epic-001 line, req-026 nested status, task-005/006 mangle) | `done` | board consistent: 0 missing, 0 mismatches
- [ops-040-index-guard-test](./ops-040-index-guard-test/ticket.md) — Guard the ticket board: assert INDEX lists every ticket and its status matches | `done` | make test enforces the board
- [ops-041-h755-rust-live](./ops-041-h755-rust-live/ticket.md) — H755ZI-Q Rust dual-core live proof (create → build → flash → run) | `done` | 399 tests; H755 live proof + sleeping-target flash fix

## Spikes

- [spike-005-h755-single-step](./spike-005-h755-single-step/ticket.md) — H755 single-step doesn't advance (stlink-dap) | `consumed` | boxed 3h — cause found (interrupts during step); fixed in bug-011
- [spike-006-wl55-cm0p-bringup](./spike-006-wl55-cm0p-bringup/ticket.md) — WL55JC CM0+ bring-up: C2BOOT doesn't persist and the CM0+ double-faults | `reported` | boxed 4h — M4 works; CM0+ needs security/RAM investigation
- [spike-007-esp32-cam](./spike-007-esp32-cam/ticket.md) — First non-STM32 board: what does an ESP32-CAM pack require? | `consumed` | boxed 4h — verdict: extend (blocks/backends/image), new-kind template family + verify cell; IDF mandatory, JTAG out. 2026-10-16: synced to main (`1eb9407`, 276 tests); IDF pinned `v6.1` (amd64+arm64, digest); owner-bench UART proven live (esptool → ESP32-D0WD rev1.0, 4MB flash, MAC 30:83:98:57:5f:c4) — Q1 closed
- [spike-008-rust-flash-run](./spike-008-rust-flash-run/ticket.md) — Rust live flash/run: is it a V1 gate, and does probe-rs flash F411RE/H755? | `reported` | boxed 3h — probe-rs flashes+verifies+runs both boards; **decision: Rust = build-parity for V1** (no LED/wfi proof); bug-025 fixed (mu build --target)

## Tasks

- [task-002-wire-create-renderer](./task-002-wire-create-renderer/ticket.md) — Wire create renderer | `done` | exec: direct | parent epic-001 | 159/159 tests, create renders F411RE c project, flags-only exits 2
- [task-003-container-argv-fix](./task-003-container-argv-fix/ticket.md) — Container argv invokes build tool, not stm | `done` | 184/184 tests, live ELF proof
- [task-004-narrow-mounts](./task-004-narrow-mounts/ticket.md) — Narrow container mounts to engine + packs | `done` | 184/184 tests, live ELF re-proof
- [task-005-probe-default-proof-precheck](./task-005-probe-default-proof-precheck/ticket.md) — Pack-default probe, proof wiring, image pre-check | `done` | 191/191 tests
- [task-006-backend-settings](./task-006-backend-settings/ticket.md) — Per-backend pack settings (probe chip strings etc.) | `done` | 195/195 tests, chips verified
- [task-007-split-probe-port](./task-007-split-probe-port/ticket.md) — R1: split the probe port into FlashPort + DebugPort | `done` | parent req-021 | 278/278 tests, argv unchanged, renderer untouched
- [task-008-validator-relocation](./task-008-validator-relocation/ticket.md) — R2: family block validators → packs/, (family, block) keys | `done` | parent req-021 | 285/285 tests, AD-13 acceptance proven (new family, zero core diff)
- [task-009-stack-axis](./task-009-stack-axis/ticket.md) — R3: pack-declared stacks map + toolchain registry | `done` | parent req-021 | 295/295 tests; stack (not --lang) selects image + build command
- [task-010-artifact-gating](./task-010-artifact-gating/ticket.md) — R4: gate artifact emission on model facts; probe ids from the family | `done` | parent req-021 | 300/300 tests, STM32 tree byte-identical, no hardcoded probe VID
- [task-011-verify-axis](./task-011-verify-axis/ticket.md) — R5: verify matrix dispatches by stack; shared build-evidence envelope | `done` | parent req-021 | 305/305 tests, 9 cells resolve via the registry
- [task-012-operational-envelope](./task-012-operational-envelope/ticket.md) — R6: name the operational envelope as one owned contract | `done` | parent req-021 | 309/309 tests, no scattered literal, ownership proven | ← refactor gate complete
- [task-013-esp32-pack](./task-013-esp32-pack/ticket.md) — E1: packs/esp32cam.yaml + esp32 family validators | `done` | parent req-022 | 319/319 tests, pack loads, ZERO core diffs
- [task-014-esptool-backend](./task-014-esptool-backend/ticket.md) — E2: esptool probe backend (FlashPort only) + UART binding | `done` | parent req-022 | 329/329 tests, argv verified; containerized tty passthrough still open
- [task-015-idf-template](./task-015-idf-template/ticket.md) — E3: idf-cmake template family | `done` | parent req-022 | 335/335 tests, idf.py build green in the pinned image (triple produced)
- [task-016-idf-verify-cell](./task-016-idf-verify-cell/ticket.md) — E4: build_idf_cell in the verify harness | `done` | parent req-022 | 338/338 tests, esp32cam cell GREEN in the harness
- [task-017-uart-tty-binding](./task-017-uart-tty-binding/ticket.md) — T17: bind UART probes to their tty (containerized serial flash) | `done` | parent req-022 | 345/345 tests, tty forwarded; live container flash proven (ops-024)
- [task-018-esp32-vscode](./task-018-esp32-vscode/ticket.md) — ESP32 VS Code flow: build / flash / monitor | `done` | parent req-022 | 347/347 tests, no launch.json, tasks only
- [task-019-dev-detach](./task-019-dev-detach/ticket.md) — mu dev --detach: attachable long-running dev container | `done` | parent req-022 | 354/354 tests, readiness-waited, env in every shell
- [task-020-esp32-blink-log](./task-020-esp32-blink-log/ticket.md) — ESP32 example logs every blink (monitor was quiet after boot) | `done` | parent req-022 | 355/355 tests, live counter
- [task-021-monitor-no-reset](./task-021-monitor-no-reset/ticket.md) — ESP32 Monitor task reset the chip through the ROM (aborted vs a running app) | `done` | parent req-022 | 355/355 tests, --no-reset + named port
- [task-022-split-flash-monitor](./task-022-split-flash-monitor/ticket.md) — Drop the combined Build+Flash+Monitor task (it leaves the port held) | `done` | parent req-022 | 355/355 tests, monitor is its own task

## Done (links only, newest last)

(none)
