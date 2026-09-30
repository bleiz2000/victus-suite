#!/usr/bin/env bash
# fan-access-probe.sh — HP Victus 16-r0xxx (board 8BBE), hp_wmi/hwmon access probe
#
# Phase A: read-only inventory (works unprivileged)
# Phase B: controlled write test (needs root)
#
# SAFETY:
#   * everything is restored on EXIT/INT/TERM via trap
#   * PWM is only ever raised (toward cooling), never lowered
#   * AUTO (pwm*_enable=2) is the recovery state
#   * no direct EC writes, no ACPI/WMI calls from userspace, no project code touched
set -uo pipefail

RESTORE=0
log()  { printf '\n[%s] %s\n' "$(date +%T)" "$*"; }
hr()   { printf -- '---------------------------------------------------------------\n'; }

find_hp_hwmon() {
    local d name
    for d in /sys/class/hwmon/hwmon*; do
        [ -r "$d/name" ] || continue
        name=$(cat "$d/name" 2>/dev/null)
        if [ "$name" = "hp" ] && [ -e "$d/pwm1" ]; then
            printf '%s\n' "$d"
            return 0
        fi
    done
    return 1
}

restore_auto() {
    [ "$RESTORE" -eq 1 ] || return 0
    local H="$1"
    if [ "$(cat "$H/pwm1_enable" 2>/dev/null)" != "2" ]; then
        log "RESTORE: forcing pwm1_enable=2 (AUTO)"
        printf '2\n' > "$H/pwm1_enable" 2>/dev/null || echo "  !! restore FAILED"
    fi
}

# ---------------------------------------------------------------- Phase A
log "PHASE A — read-only inventory"
hr

echo "kernel:   $(uname -r)"
echo "product:  $(cat /sys/class/dmi/id/product_name 2>/dev/null)"
echo "board:    $(cat /sys/class/dmi/id/board_name 2>/dev/null)"
echo "bios:     $(cat /sys/class/dmi/id/bios_version 2>/dev/null)"
echo "module:   $(grep -E '^hp_wmi ' /proc/modules || echo 'hp_wmi not loaded')"
echo
echo "kernel log:"
dmesg 2>/dev/null | grep -i 'hp_wmi' | tail -5 || echo "  (dmesg not readable)"

H=$(find_hp_hwmon) || { echo "!! hp hwmon not found"; exit 1; }
echo
echo "hwmon node: $H  (driver: $(basename "$(readlink -f "$H/device/driver" 2>/dev/null)"))"
echo
echo "  attrs: $(ls "$H" | tr '\n' ' ')"
echo
printf '  %-16s %s\n' "fan1_input (CPU)" "$(cat "$H/fan1_input")"
printf '  %-16s %s\n' "fan2_input (GPU)" "$(cat "$H/fan2_input")"
printf '  %-16s %s\n' "pwm1"             "$(cat "$H/pwm1")"
printf '  %-16s %s\n' "pwm1_enable"      "$(cat "$H/pwm1_enable")"
printf '  %-16s %s\n' "pwm2"             "$(cat "$H/pwm2")"
printf '  %-16s %s\n' "pwm2_enable"      "$(cat "$H/pwm2_enable" 2>/dev/null || echo '<absent>')"
echo
echo "  perms:"
ls -l "$H"/pwm* "$H"/fan* | sed 's/^/    /'

echo
echo "  temps:"
for t in /sys/class/hwmon/hwmon*; do
    [ -r "$t/name" ] || continue
    n=$(cat "$t/name")
    for f in "$t"/temp*_input; do
        [ -e "$f" ] || continue
        lab=""
        [ -r "${f%_input}_label" ] && lab=" ($(cat "${f%_input}_label"))"
        v=$(( $(cat "$f") / 1000 ))
        case "$n" in acpitz|coretemp|nvme) printf '    %-10s %-16s %s °C%s\n' "$n" "$(basename "$f")" "$v" "$lab";; esac
    done
done
nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader 2>/dev/null | sed 's/^/    nvidia     gpu_temp            /;s/$/ °C/'

echo
echo "  platform_profile:"
PP=""
for cand in /sys/class/platform-profile/*/profile; do
    [ -e "$cand" ] && { PP="$cand"; break; }
done
echo "    choices : $(cat "$(dirname "$PP")/choices" 2>/dev/null)"
echo "    profile : $(cat "$PP" 2>/dev/null)"

echo
echo "  other paths:"
echo "    /sys/kernel/debug/ec/ec0/io : $(stat -c '%A %U:%G' /sys/kernel/debug/ec/ec0/io 2>/dev/null || echo 'not visible to this user (needs root+debugfs)')"
echo "    ec_sys write_support        : $(cat /sys/module/ec_sys/parameters/write_support 2>/dev/null || echo '?')"
echo "    acpi-ec driver              : present ($([ -d /sys/bus/platform/drivers/acpi-ec ] && echo yes || echo no))"
echo "    cooling devices             : $(ls -d /sys/class/thermal/cooling_device* 2>/dev/null | wc -l) (Fan/Processor/intel_powerclamp)"

# ---------------------------------------------------------------- Phase B
log "PHASE B — controlled write test"
hr

if [ "$(id -u)" -ne 0 ]; then
    echo "not root -> skipping write test."
    echo "re-run as:  sudo $0"
    exit 0
fi

P1_SAVE=$(cat "$H/pwm1")
P2_SAVE=$(cat "$H/pwm2")
E_SAVE=$(cat "$H/pwm1_enable")
F1_SAVE=$(cat "$H/fan1_input")
F2_SAVE=$(cat "$H/fan2_input")
log "saved state: pwm1=$P1_SAVE pwm2=$P2_SAVE enable=$E_SAVE rpm=$F1_SAVE/$F2_SAVE"

RESTORE=1
trap 'restore_auto "$H"; echo; log "trap: AUTO re-asserted, done"' EXIT
trap 'exit 130' INT TERM

# B1: write while in AUTO must be rejected (-EINVAL) -> proves the mode guard
log "B1: write pwm1 while enable=$E_SAVE (expect FAIL)"
out=$({ printf '200\n' > "$H/pwm1"; } 2>&1) && echo "  UNEXPECTED: write accepted" || echo "  rejected as expected: ${out:-<errno not surfaced>}"
echo "  enable now: $(cat "$H/pwm1_enable"), pwm1 now: $(cat "$H/pwm1")"

# B2: idempotent enable write -> proves plain writability
log "B2: idempotent pwm1_enable=$E_SAVE (expect OK)"
if printf '%s\n' "$E_SAVE" > "$H/pwm1_enable" 2>&1; then
    echo "  OK, sysfs is writable as root"
else
    echo "  FAILED"
fi

# B3: enter MANUAL — driver snapshots current RPM, so fans must NOT jump
log "B3: pwm1_enable=1 (MANUAL) — expect rpm unchanged"
if ! printf '1\n' > "$H/pwm1_enable" 2>&1; then
    echo "  !! cannot enter MANUAL; aborting write test"; RESTORE=0; exit 1
fi
sleep 2
echo "  enable=$(cat "$H/pwm1_enable") pwm1=$(cat "$H/pwm1") pwm2=$(cat "$H/pwm2") rpm=$(cat "$H/fan1_input")/$(cat "$H/fan2_input")"
M_RPM1=$(cat "$H/fan1_input"); M_RPM2=$(cat "$H/fan2_input")
echo "  delta vs saved: $(( M_RPM1 - F1_SAVE )) / $(( M_RPM2 - F2_SAVE )) RPM (want 0)"

# B4: raise PWM only (toward cooling), staggered by 10 s between fans
NEW1=$(( P1_SAVE + 40 )); [ "$NEW1" -gt 255 ] && NEW1=255
NEW2=$(( P2_SAVE + 40 )); [ "$NEW2" -gt 255 ] && NEW2=255

log "B4: pwm1 $P1_SAVE -> $NEW1 (CPU fan up)"
printf '%s\n' "$NEW1" > "$H/pwm1" && echo "  write OK, readback=$(cat "$H/pwm1")"
sleep 12
echo "  cpu fan now: $(cat "$H/fan1_input") RPM (was $M_RPM1)"

log "B4b: pwm2 $P2_SAVE -> $NEW2 (GPU fan up) [after 10 s stagger]"
printf '%s\n' "$NEW2" > "$H/pwm2" && echo "  write OK, readback=$(cat "$H/pwm2")"
sleep 8
echo "  gpu fan now: $(cat "$H/fan2_input") RPM (was $M_RPM2)"
echo "  cpu fan now: $(cat "$H/fan1_input") RPM"
echo "  pkg temp   : $(( $(cat /sys/class/hwmon/hwmon*/temp1_input 2>/dev/null | head -1) / 1000 )) °C"

log "B5: restore AUTO (pwm1_enable=2)"
printf '2\n' > "$H/pwm1_enable" && echo "  write OK"
RESTORE=0
sleep 5
echo "  enable=$(cat "$H/pwm1_enable") pwm1=$(cat "$H/pwm1") pwm2=$(cat "$H/pwm2")"
echo "  rpm=$(cat "$H/fan1_input")/$(cat "$H/fan2_input")  (saved: $F1_SAVE/$F2_SAVE)"

log "B6: kernel messages after the test"
dmesg 2>/dev/null | grep -iE 'hp_wmi|keep-alive' | tail -10 || echo "  (dmesg not readable)"

log "PROBE FINISHED — state restored"
