#!/usr/bin/env bash
# build_double.sh -- PC-only double-precision build of the Phase 1 runner (Phase 4 item 1). Usage: build_double.sh <out_dir>
# Copies the UNMODIFIED firmware/common/circuits.hpp (checked by sha256) beside double/qsim.hpp so that the circuit source text is the
# firmware's, evaluated in double. Nothing under firmware/ is written.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
out="${1:?usage: build_double.sh <out_dir>}"
mkdir -p "$out"
cp "$here/../../firmware/common/circuits.hpp" "$out/circuits.hpp"
cp "$here/double/qsim.hpp" "$out/qsim.hpp"
cp "$here/main_double.cpp" "$out/main_double.cpp"
src_sha=$(shasum -a 256 "$here/../../firmware/common/circuits.hpp" | cut -d' ' -f1)
cpy_sha=$(shasum -a 256 "$out/circuits.hpp" | cut -d' ' -f1)
[ "$src_sha" = "$cpy_sha" ] || { echo "circuits.hpp copy differs from firmware"; exit 1; }
g++ -O2 -std=c++11 -Wall -Wextra -o "$out/phase1_validate_double" "$out/main_double.cpp"
echo "built $out/phase1_validate_double (circuits.hpp sha256 $src_sha, flags -O2 -std=c++11)"
