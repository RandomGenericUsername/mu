# Rust image: pinned Rust toolchain + embedded targets + probe-rs + ST OpenOCD fork.
# Pinned: base digest, Rust 1.99.0 via rustup, probe-rs v0.32.0 (sha256-verified),
# OpenOCD fork SHA c8d973b built from source.
# Toolchain tarballs below are x86_64-only, so the image platform is pinned too.
FROM --platform=linux/amd64 debian:bookworm-slim@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587

ARG RUST_TOOLCHAIN=1.99.0
ARG RUSTUP_INIT_URL=https://static.rust-lang.org/rustup/dist/x86_64-unknown-linux-gnu/rustup-init
# Observed 2026-10-09; re-verify at build against published sidecar (rustup-init.sha256).
ARG RUSTUP_INIT_SHA256=dda7234360b7f578ca8b0ddcb80145646fa61a67c1720a5abc7051b35c9fcb71
ARG PROBE_RS_VERSION=0.32.0
ARG PROBE_RS_SHA256=c2ccc46049e52a5d403ef212078cd637ecda55b662708327960558f83e851ff5
ARG PROBE_RS_URL=https://github.com/probe-rs/probe-rs/releases/download/v0.32.0/probe-rs-tools-x86_64-unknown-linux-gnu.tar.xz
ARG FLIP_LINK_VERSION=0.1.12
ARG OPENOCD_REPO=https://github.com/STMicroelectronics/OpenOCD.git
ARG OPENOCD_SHA=c8d973bdad9a6fddb51459eda109b3b95d23b57a

LABEL org.mu.rust.toolchain="1.99.0" \
      org.mu.probe-rs.version="v0.32.0" \
      org.mu.probe-rs.sha256="c2ccc46049e52a5d403ef212078cd637ecda55b662708327960558f83e851ff5" \
      org.mu.flip-link.version="0.1.12" \
      org.mu.openocd.repo="https://github.com/STMicroelectronics/OpenOCD.git" \
      org.mu.openocd.sha="c8d973bdad9a6fddb51459eda109b3b95d23b57a" \
      org.mu.base="debian:bookworm-slim@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587"

ENV DEBIAN_FRONTEND=noninteractive \
    RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH=/usr/local/cargo/bin:/usr/local/bin:${PATH}

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl xz-utils \
        build-essential git autoconf automake libtool pkg-config make \
        libusb-1.0-0-dev libhidapi-dev libudev-dev pkgconf libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# rustup: download + verify against published sidecar AND recorded pin, then
# install pinned Rust toolchain + both thumbv7em targets + thumbv6m (M0+).
RUN curl -fsSL -o /tmp/rustup-init "${RUSTUP_INIT_URL}" \
    && curl -fsSL -o /tmp/rustup-init.sha256 "${RUSTUP_INIT_URL}.sha256" \
    && grep -q "${RUSTUP_INIT_SHA256}" /tmp/rustup-init.sha256 \
    && cd /tmp && sha256sum -c rustup-init.sha256 \
    && chmod +x /tmp/rustup-init \
    && /tmp/rustup-init -y --profile minimal --default-toolchain "${RUST_TOOLCHAIN}" \
    && rm /tmp/rustup-init /tmp/rustup-init.sha256 \
    && rustup target add thumbv7em-none-eabihf thumbv7em-none-eabi thumbv6m-none-eabi --toolchain "${RUST_TOOLCHAIN}" \
    && rustc --version && rustup target list --installed --toolchain "${RUST_TOOLCHAIN}"

# probe-rs prebuilt tools: download + sha256 verify + install to /usr/local/bin.
RUN curl -fsSL -o /tmp/probe-rs.tar.xz "${PROBE_RS_URL}" \
    && echo "${PROBE_RS_SHA256}  /tmp/probe-rs.tar.xz" | sha256sum -c - \
    && tar -xf /tmp/probe-rs.tar.xz -C /usr/local/bin --strip-components=1 --wildcards '*/probe-rs' '*/cargo-embed' '*/cargo-flash' \
    && rm /tmp/probe-rs.tar.xz \
    && probe-rs --version

# flip-link (pinned) for Cortex-M Rust linking.
RUN cargo install --locked --version "${FLIP_LINK_VERSION}" flip-link \
    && ls "${CARGO_HOME}/bin" | grep -x flip-link

# ST OpenOCD fork from source at pinned SHA.
RUN git clone "${OPENOCD_REPO}" /tmp/openocd \
    && git -C /tmp/openocd checkout --detach "${OPENOCD_SHA}" \
    && git -C /tmp/openocd rev-parse HEAD \
    && cd /tmp/openocd && ./bootstrap && ./configure --prefix=/usr/local \
    && make -j"$(nproc)" && make install && cd / && rm -rf /tmp/openocd \
    && openocd --version | head -2

# Engine runtime: the shim execs `python3 -m engine` from the read-only repo
# mount, so images need an interpreter + the engine's single dependency.
# pyyaml pinned to uv.lock (6.0.3); trailing layer preserves toolchain cache.
ARG PYYAML_VERSION=6.0.3
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --break-system-packages "pyyaml==${PYYAML_VERSION}" \
    && python3 -c "import yaml; assert yaml.__version__ == '${PYYAML_VERSION}', yaml.__version__"

# bug-017: login shells (VS Code tasks run `bash -l`) source /etc/profile, whose
# base image resets PATH and drops the toolchain (Error 127). /etc/profile
# sources profile.d last, so re-export the image PATH there. Last layer keeps the
# Rust/probe-rs/OpenOCD build cache intact (bug-020).
RUN printf 'export PATH="%s"\n' "$PATH" > /etc/profile.d/00-mu-path.sh

CMD ["rustc", "--version"]
