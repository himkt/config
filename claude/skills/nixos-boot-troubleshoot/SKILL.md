---
name: nixos-boot-troubleshoot
description: >
  Systematic investigation of NixOS boot failures (crash after reboot, kernel panic,
  black screen after update, system won't boot). Guides through journal log analysis,
  generation comparison, and fix proposal. Use when a user reports their NixOS system
  fails to boot or crashes after reboot but works with nixos-rebuild switch.
---

# NixOS Boot Failure Troubleshooting

Use this procedure when the user reports any of:
- NixOS crashes after reboot
- Boot failure
- Kernel panic
- Black screen after update
- NixOS won't boot
- System works with `nixos-rebuild switch` but crashes on reboot

> **Key insight**: `nixos-rebuild switch` does **not** change the running kernel. A kernel regression is invisible after `switch` because the old kernel is still running. The regression only manifests after a full reboot when the new kernel loads. This makes kernel regressions particularly confusing to diagnose.

## Procedure

Follow these 7 steps in order.

### Step 1: Gather Context

Ask the user:
- When did the problem start? (after a specific `nixos-rebuild switch`? after an update?)
- What is the failure symptom? (black screen, kernel panic, hangs at boot, display manager crash)
- Can they currently access the system? (booted from an older generation? on the broken boot?)

### Step 2: Check System Generations

Run:

```bash
sudo nixos-rebuild list-generations
```

Identify:
- The currently active generation
- Recent generations and their timestamps
- Which generation likely introduced the failure (correlate with the time the user reported the failure starting)
- Compare kernel versions between generations if visible in the output

### Step 3: Analyze Previous Boot Logs

Run these commands sequentially to inspect the failed boot:

1. **Critical errors** — kernel crashes and critical service failures from the previous boot:
   ```bash
   journalctl -b -1 --priority=crit
   ```

2. **Kernel log** — full kernel messages including driver stack traces:
   ```bash
   journalctl -b -1 -k
   ```

3. **Failed services** — currently failed services (useful if on the broken boot):
   ```bash
   systemctl --failed
   ```

Interpret the output using these patterns:

| Log Pattern | Likely Cause |
|-------------|-------------|
| Stack trace mentioning `xe`, `i915`, `amdgpu`, `nvidia` | GPU driver regression |
| `systemd-cryptsetup` errors, LUKS-related messages | LUKS decryption failure |
| `gdm`, `sddm`, `lightdm` crash/restart loops | Display manager crash |
| Kernel oops/panic with module name | Kernel module regression |
| No journal entries for `-b -1` at all | initrd failure (system never reached journald) |

### Step 4: Compare with Current Boot

If the system is currently running (booted from an older generation or the issue is intermittent):

1. Check the current kernel version:
   ```bash
   uname -r
   ```

2. Inspect the current boot's kernel log:
   ```bash
   journalctl -b 0 -k
   ```

Compare the `-b 0` output with the `-b -1` output from Step 3 to identify:
- Kernel version differences
- Driver modules loaded vs failed
- Hardware initialization differences

### Step 5: Compare Generations

When a working and broken generation are identified:

1. **Compare system closure differences** — this shows package version differences between generations including kernel version changes:
   ```bash
   nix store diff-closures /nix/var/nix/profiles/system-WORKING-link /nix/var/nix/profiles/system-BROKEN-link
   ```
   Replace `WORKING` and `BROKEN` with the actual generation numbers.

2. **Discover the NixOS configuration** dynamically — do not hardcode paths:
   - Use Glob to find `flake.nix` in the repo root
   - Use Grep to search for `nixosConfigurations` to find the configuration entry point
   - Trace imports to find files that set boot and display options

3. **Check specific configuration areas** based on the cause identified in Steps 3-4. Use Grep to search across the repo for:
   - For kernel issues: `boot.kernelPackages`, `boot.kernelModules`, `boot.extraModulePackages`
   - For display manager issues: `services.displayManager`, `services.xserver.displayManager`
   - For initrd issues: `boot.initrd`

### Step 6: Identify Root Cause

Synthesize findings from Steps 3-5 into a root cause diagnosis. Present to the user:
- **What failed**: the specific driver, service, or subsystem
- **Why it failed**: version change, configuration change, or upstream regression
- **Which generation / package change introduced the failure**

### Step 7: Propose Fix Options

Present fix options to the user **without auto-applying any changes**. Let the user decide which fix to apply.

| Cause | Fix Options |
|-------|------------|
| **Kernel regression** | 1. Pin `boot.kernelPackages` to a specific version (e.g., `pkgs.linuxPackages_latest`, `pkgs.linuxPackages_6_12`). 2. Use an older nixpkgs input that has the working kernel version. |
| **GPU driver regression** | 1. Pin kernel (same as above). 2. Blacklist the problematic module via `boot.blacklistedKernelModules`. 3. Switch to a different driver (e.g., `i915` instead of `xe`). |
| **Display manager crash** | 1. Switch display manager (e.g., GDM to SDDM). 2. Check and fix display manager configuration. 3. Disable and re-enable the service. |
| **initrd / LUKS failure** | 1. Ensure required kernel modules are in `boot.initrd.availableKernelModules`. 2. Check LUKS device UUIDs match actual disk layout. |
| **Quick mitigation** | Boot from a known-good generation via the systemd-boot menu (select older generation at boot) to restore functionality while investigating. |

For each fix, show the user:
- The specific Nix configuration change (code snippet)
- Where in their repo to apply it (discover the file dynamically using Grep)
- The command to apply: `sudo nixos-rebuild switch`
