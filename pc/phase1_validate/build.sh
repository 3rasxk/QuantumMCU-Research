#!/usr/bin/env bash
# build.sh — คอมไพล์ phase1_validate ด้วยแฟล็กที่บันทึกไว้ใช้ล็อกในรายงาน
# ใช้ -O2 (ระดับ optimize มาตรฐานที่จะใช้เทียบกับ MCU build ใน Phase 2)
set -euo pipefail
cd "$(dirname "$0")"
CXXFLAGS="-O2 -std=c++11 -Wall -Wextra"
g++ $CXXFLAGS -o phase1_validate main.cpp
echo "built phase1_validate with flags: $CXXFLAGS"
