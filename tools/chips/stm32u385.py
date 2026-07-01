#!/usr/bin/env python3
"""
chips/stm32u385.py -- STM32U385RG chip module (RM0487 Rev 3).

Tier 1: full SVD auto-mode with register-map provenance from the RM0487 TOC.
Tier 2 pending.  Build with: python3 tools/build.py stm32u385
"""
import re

# --- chip descriptor (read by build.py) -----------------------------------------
ID = "stm32u385"
SVD_FILE = "stm32u385.svd"                  # in tools/chips/
SECTIONS_FILE = "stm32u385.sections.json"   # in tools/chips/, from make_sections.py
OUT = "data/stm32u385rg.json"               # relative to the project root
EMIT_ALL = True                             # emit every SVD peripheral (auto-mode)

DOC_RM = "RM0487"
RM_REV = "3"

PART = {
    "mpn": "STM32U385RG",
    "manufacturer": "STMicroelectronics",
    "family": "STM32U3",
    "revision": "rev-X",
    "lifecycle": "active",
    "packages": ["LQFP64"],
}

DOCUMENTS = [
    {"id": "RM0487", "kind": "reference-manual", "rev": "3",
     "url": "https://www.st.com/resource/en/reference_manual/rm0487-stm32u3-series-armbased-32bit-mcus-stmicroelectronics.pdf"},
    {"id": "DS14830", "kind": "datasheet", "rev": "3",
     "url": "https://www.st.com/resource/en/datasheet/stm32u385rg.pdf"},
]

# No curated specs yet -- auto-mode covers the whole chip.
PERIPHERALS = []
EXTRA_PERIPHERALS = []

# --- TrustZone: drop SEC_* secure-world aliases (identical register maps) --------
SKIP_PREFIXES = ("SEC_",)

# --- Auto-mode provenance helpers -----------------------------------------------
# Keyed by SVD peripheral name prefix -> RM TOC section prefix.
# Default: strip trailing digits (SPI1 -> SPI). Override where RM uses a
# different placeholder.
AUTO_PREFIX_OVERRIDE = {
    "GPIO":         "GPIOx",       # RM keys: GPIOx_MODER, GPIOx_IDR, ...
    "TIM":          "TIMx",        # RM keys: TIMx_CR1, TIMx_SR, ... (all timers)
    "LPTIM":        "LPTIMx",      # RM keys: LPTIMx_CR, LPTIMx_CFGR, ...
    "ExTI":         "EXTI",        # SVD spells it mixed-case; RM uses EXTI_*
    # GTZC1_MPCBB* has a trailing digit that the default stripper removes (-> GTZC1_MPCBB)
    # but RM keys include the instance digit: GTZC1_MPCBB1_CR, GTZC1_MPCBB2_CR.
    "GTZC1_MPCBB1": "GTZC1_MPCBB1",
    "GTZC1_MPCBB2": "GTZC1_MPCBB2",
}

# Chapter-level fallback for peripherals with no per-register TOC entries.
CHAPTER_FALLBACK = {
    "DBGMCU":  "53",   # Debug MCU -- no register-level TOC in RM0487
    "USBSRAM": "35",   # USB packet SRAM buffer -- part of the USB chapter
}

# RM0487-verified access for status/clear registers the SVD mis-types.
# Keyed by family = peripheral name with trailing digits stripped.
ACCESS_FIX = {
    "ADC":  {"ISR": "w1c"},         # rc_w1 -- cleared in place (no separate clear reg)
    "EXTI": {"RPR1": "w1c", "FPR1": "w1c"},   # rising/falling pending regs, rc_w1
    "WWDG": {"SR": "w0c"},          # EWIF is rc_w0
}

# Auto-mode clear-register naming rules (applied to every auto peripheral).
# Registers whose bare name ends with this suffix are all-w1c:
CLEAR_SUFFIX = "ICR"                # I2C_ICR, LPTIM_ICR, CRS_ICR, AES_ICR, ...
# Registers whose bare name exactly matches one of these are all-w1c:
CLEAR_NAMES = {"SCR", "IFCR"}      # TAMP_SCR, (future SPI IFCR if present)

# Tier 2 (electrical/limits) -- not yet curated for this part.
LIMITS = {}
ELECTRICAL = []
TIERS = [1]
