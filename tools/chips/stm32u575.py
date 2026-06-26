#!/usr/bin/env python3
"""
chips/stm32u575.py -- STM32U575ZI chip module for OpenDatasheet Tier 1.

Structure (offsets, fields, resets) from the CMSIS-SVD (STM32U575.svd);
provenance from RM0456 Rev 6. Access fixes for status/clear registers that the SVD
cannot express (W1C, read-only).

SVD register naming convention (observed):
  * Most peripherals: registers carry a short prefix matching the generic IP block
    name, NOT the instance name. e.g. SPI1 -> SPI_CR1, ADC1 -> ADC_ISR,
    RCC -> RCC_CR. These bare names match the sections.json keys directly.
  * TIM1: prefixed with TIM1_  (TIM1_CR1), which the rename strips.
  * GPIO: prefixed with GPIO_ (not GPIOA_), so requires a curated rename.
  * GPDMA/LPDMA: prefixed with GPDMA_/LPDMA_ with channel number (GPDMA_C0TR1),
    so requires a curated rename + keyfn that replaces C0 -> Cx.
  * Some peripherals (TIM2, TIM6, I2C, ...) use bare names (CR1, CR2).
  * Derived peripherals (e.g. TIM8 derived from TIM1) inherit TIM1_* names,
    not TIM8_* names, so need curated specs to resolve.
  * SEC_ TrustZone aliases derive from their base, inheriting the same register
    names, so they can be included as emit instances in curated specs.
"""
import re

# --- chip descriptor -----------------------------------------------------------
ID = "stm32u575"
SVD_FILE = "stm32u575.svd"
SECTIONS_FILE = "stm32u575.sections.json"
OUT = "data/stm32u575zi.json"
EMIT_ALL = True

# Drop the TrustZone secure-world aliases: the U5 SVD exposes every peripheral a
# second time as SEC_<name> with identical registers (just the secure address
# space). They carry no extra information, so we emit one canonical instance per
# peripheral and skip the SEC_ duplicates (halves the part size).
SKIP_PREFIXES = ("SEC_",)

DOC_RM = "RM0456"
RM_REV = "6"

PART = {
    "mpn": "STM32U575ZI",
    "manufacturer": "STMicroelectronics",
    "family": "STM32U5",
    "revision": "rev-X",
    "lifecycle": "active",
    "packages": ["LQFP144"],
}

DOCUMENTS = [
    {"id": "RM0456", "kind": "reference-manual", "rev": "6",
     "url": "https://www.st.com/resource/en/reference_manual/rm0456-stm32u5-series-armbased-32bit-mcus-stmicroelectronics.pdf"},
    {"id": "DS13737", "kind": "datasheet", "rev": "10",
     "url": "https://www.st.com/resource/en/datasheet/stm32u575zi.pdf"},
]

# --- auto-mode provenance helpers ----------------------------------------------
# AUTO_PREFIX_OVERRIDE: per.startswith(k) match, first match wins.
# Default for uncovered peripherals: strip-trailing-digits (SPI1 -> SPI).
AUTO_PREFIX_OVERRIDE = {
    # ADC12 common: strip-digits gives ADC, but RM uses ADC12_ prefix
    "ADC12":        "ADC12",
    # GPIO: register names are GPIO_MODER (not GPIOA_MODER); handled below via
    # curated spec. Override kept for any auto fallback paths.
    "GPIO":         "GPIOx",
    # OTG_FS: no trailing digits, RM TOC uses OTG_ prefix
    "OTG_FS":       "OTG",
    # ICache: SVD mixed-case, RM uses ICACHE_ (all-caps)
    "ICache":       "ICACHE",
    # TIM1-TIM17: strip gives TIM, RM uses TIMx_
    "TIM":          "TIMx",
    # GTZC1 MPCBB: GTZC1_MPCBB1/2/3 strip to GTZC1_MPCBB; RM uses GTZC1_MPCBBz_
    "GTZC1_MPCBB":  "GTZC1_MPCBBz",
    # GTZC2_MPCBB4: strip removes the 4 which is part of the name
    "GTZC2_MPCBB4": "GTZC2_MPCBB4",
    # UART4/5: strip gives UART, but RM documents under USART chapter
    "UART":         "USART",
    # LPUART: stays LPUART (sections use LPUART_ prefix) - no change needed
    # SEC_ TrustZone aliases: inherit register names from the base peripheral.
    # The RM documents secure and non-secure registers in the same sections.
    "SEC_ADC12":        "ADC12",
    "SEC_ADC":          "ADC",
    "SEC_ADF":          "ADF",
    "SEC_AES":          "AES",
    "SEC_COMP":         "COMP",
    "SEC_CORDIC":       "CORDIC",
    "SEC_CRC":          "CRC",
    "SEC_CRS":          "CRS",
    "SEC_DAC":          "DAC",
    "SEC_DCACHE":       "DCACHE",
    "SEC_DCMI":         "DCMI",
    "SEC_DLYBOS":       "DLYBOS",
    "SEC_DLYBSD":       "DLYBSD",
    "SEC_DMA2D":        "DMA2D",
    "SEC_EXTI":         "EXTI",
    "SEC_FDCAN1_RAM":   "FDCAN1_RAM",
    "SEC_FDCAN":        "FDCAN",
    "SEC_FLASH":        "FLASH",
    "SEC_FMAC":         "FMAC",
    "SEC_FMC":          "FMC",
    "SEC_GPDMA":        "GPDMA",
    "SEC_GPIO":         "GPIOx",
    "SEC_GTZC1_MPCBB":  "GTZC1_MPCBBz",
    "SEC_GTZC2_MPCBB4": "GTZC2_MPCBB4",
    "SEC_GTZC1_TZIC":   "GTZC1_TZIC",
    "SEC_GTZC1_TZSC":   "GTZC1_TZSC",
    "SEC_GTZC2_TZIC":   "GTZC2_TZIC",
    "SEC_GTZC2_TZSC":   "GTZC2_TZSC",
    "SEC_HASH":         "HASH",
    "SEC_I2C":          "I2C",
    "SEC_ICache":       "ICACHE",
    "SEC_IWDG":         "IWDG",
    "SEC_LPDMA":        "LPDMA",
    "SEC_LPGPIO":       "LPGPIO",
    "SEC_LPTIM":        "LPTIM",
    "SEC_LPUART":       "LPUART",
    "SEC_MDF":          "MDF",
    "SEC_OCTOSPI1":     "OCTOSPI",
    "SEC_OCTOSPI2":     "OCTOSPI",
    "SEC_OCTOSPIM":     "OCTOSPIM",
    "SEC_OPAMP":        "OPAMP",
    "SEC_OTFDEC":       "OTFDEC",
    "SEC_OTG_FS":       "OTG",
    "SEC_PKA":          "PKA",
    "SEC_PSSI":         "PSSI",
    "SEC_PWR":          "PWR",
    "SEC_RAMCFG":       "RAMCFG",
    "SEC_RCC":          "RCC",
    "SEC_RNG":          "RNG",
    "SEC_RTC":          "RTC",
    "SEC_SAI":          "SAI",
    "SEC_SDMMC":        "SDMMC",
    "SEC_SPI":          "SPI",
    "SEC_SYSCFG":       "SYSCFG",
    "SEC_TAMP":         "TAMP",
    "SEC_TIM":          "TIMx",
    "SEC_TSC":          "TSC",
    "SEC_UART":         "USART",
    "SEC_UCPD":         "UCPD",
    "SEC_USART":        "USART",
    "SEC_VREFBUF":      "VREFBUF",
    "SEC_WWDG":         "WWDG",
}

# CHAPTER_FALLBACK: last-resort coarse citation when per-register TOC lookup
# fails. Matched by label.startswith(k); order matters - more specific first.
# Chapter numbers from RM0456 TOC (observed from sections.json section prefixes).
CHAPTER_FALLBACK = {
    # GTZC: MPCBB registers have shortened names (MPCBB1_CR not GTZC1_MPCBB1_CR)
    #       and TZSC registers have shortened names (TZSC_CR not GTZC1_TZSC_CR).
    "GTZC":       "5",
    "SEC_GTZC":   "5",
    # HASH: result/context registers (HR*, HRA*, CSR*) not individually in TOC
    "HASH":       "51",
    "SEC_HASH":   "51",
    # FLASH: block-based registers (SEC1BBRx) not individually in TOC
    "FLASH":      "7",
    "SEC_FLASH":  "7",
    # OTFDEC: NONCER/KEYR registers not individually in TOC
    "OTFDEC":     "52",
    "SEC_OTFDEC": "52",
    # DBGMCU: not in RM TOC
    "DBGMCU":     "75",
    # FMC: not in RM TOC
    "FMC":        "32",
    "SEC_FMC":    "32",
    # DMA2D: OCOLR alternates and CLUT array registers
    "DMA2D":      "19",
    "SEC_DMA2D":  "19",
    # EXTI: EXTICRm uses 'm' placeholder not generated by default keyfn
    "EXTI":       "23",
    "SEC_EXTI":   "23",
    # TIM: alternateRegister views (_ALTERNATE1, _Output, _Input) and
    #      TIM8/SEC_TIM1 which derive from TIM1 and inherit TIM1_* names.
    # Specific entries before the catch-all so they match first.
    "TIM15":      "56",
    "TIM16":      "56",
    "TIM17":      "56",
    "TIM":        "54",
    "SEC_TIM15":  "56",
    "SEC_TIM16":  "56",
    "SEC_TIM17":  "56",
    "SEC_TIM":    "54",
    # LPTIM: DIER/ICR/ISR only in sections as LPTIMx_DIER/ICR/ISR (with x);
    #        base 'LPTIM' (from strip-digits) can't generate that key.
    "LPTIM":      "58",
    "SEC_LPTIM":  "58",
    # USART/UART: _enabled/_disabled alternateRegister views not in sections
    "USART":      "66",
    "UART":       "66",
    "LPUART":     "66",
    "SEC_USART":  "66",
    "SEC_UART":   "66",
    "SEC_LPUART": "66",
    # SDMMC: RESPxR name has trailing R not generated by keyfn substitution
    "SDMMC":      "31",
    "SEC_SDMMC":  "31",
    # OTG_FS: GRXSTSR_DEVICE/HOST alternateRegister views
    "OTG_FS":     "72",
    "SEC_OTG_FS": "72",
    # ADC4: special low-power ADC registers (CHSELRMOD0/1, PWR)
    "ADC4":       "34",
    "SEC_ADC4":   "34",
    # OCTOSPIM: PnCR uses 'n' placeholder, keyfn only tries 'x' and 'y'
    "OCTOSPIM":   "29",
    "SEC_OCTOSPIM": "29",
    # RTC/TAMP: PRIVCR not individually in TOC
    "RTC":        "63",
    "TAMP":       "64",
    "SEC_RTC":    "63",
    "SEC_TAMP":   "64",
    # DCB: ARM Debug Control Block, not documented in RM0456
    "DCB":        "75",
    # GPIO: catch remaining registers not in sections (SECCFGR/PRIVCFGR)
    "GPIO":       "13",
    "SEC_GPIO":   "13",
    "LPGPIO":     "14",
    "SEC_LPGPIO": "14",
}

# --- RM0456 Rev 6-verified access fixes ----------------------------------------
# The SVD cannot express W1C/w0c/rc; these are mis-typed as read-write.
# Keyed by family = peripheral name with trailing digits stripped.
#
# Only UNIFORM access registers are blanket-fixed here. Registers where
# rm_inspect showed MIXED access (e.g. ADC_ISR, FDCAN_IR, I2C_ISR) are left
# with the SVD's per-field access rather than applying a wrong blanket value.
ACCESS_FIX = {
    # WWDG_SR: rc_w0 UNIFORM - rm_inspect page 2584 confirms single field EWIF
    "WWDG": {"SR": "w0c"},
    # RTC_SR: r (read-only) UNIFORM - rm_inspect page 2632; cleared via RTC_SCR
    "RTC":  {"SR": "read-only"},
    # EXTI RPR1/FPR1: all active bits (RPIFx/FPIFx) are rc_w1 per RM register
    # table (the 'rw' in the mixed scan comes from adjacent SWIER register text
    # on the same PDF page, not from RPR1/FPR1 fields themselves).
    "EXTI": {"RPR1": "w1c", "FPR1": "w1c"},
}

# Write-1-to-clear register patterns (applied to auto peripherals).
CLEAR_SUFFIX = "ICR"
CLEAR_NAMES  = {"SCR", "IFCR", "FCR", "CLRFR"}

# --- helpers for curated specs -------------------------------------------------
def _gpdma_keyfn(prefix):
    """Return a section_keyfn that maps GPDMA/LPDMA channel-register bare names
    (e.g. 'C0TR1' after stripping 'GPDMA_') to RM-section-key candidates like
    'GPDMA_CxTR1'. The 'Cx' placeholder replaces only the leading channel index
    (C0, C1, ...) so the register-type index (TR1, BR1, etc.) is preserved."""
    def fn(bare):
        cx_bare = re.sub(r"^C\d+", "Cx", bare)  # C0TR1 -> CxTR1, MISR -> MISR
        return [f"{prefix}_{cx_bare}", f"{prefix}_{bare}"]
    return fn


# --- curated peripheral specs --------------------------------------------------
# GPIO: SVD names registers GPIO_MODER (not GPIOA_MODER), so the default auto
# rename (strips GPIOA_) leaves the bare name as GPIO_MODER which can't be
# resolved to the section key GPIOx_MODER.
GPIO = {
    "svd_name": "GPIOA",
    "description": "General-purpose I/Os",
    # Strip GPIO_ prefix to get bare name: GPIO_MODER -> MODER
    "rename": lambda n: n[len("GPIO_"):] if n.startswith("GPIO_") else n,
    "section_keyfn": lambda b: f"GPIOx_{b}",
    "_clear_pattern": True,
    "emit": [
        {"name": "GPIOA"}, {"name": "GPIOB"}, {"name": "GPIOC"},
        {"name": "GPIOD"}, {"name": "GPIOE"}, {"name": "GPIOF"},
        {"name": "GPIOG"}, {"name": "GPIOH"}, {"name": "GPIOI"},
        {"name": "SEC_GPIOA"}, {"name": "SEC_GPIOB"}, {"name": "SEC_GPIOC"},
        {"name": "SEC_GPIOD"}, {"name": "SEC_GPIOE"}, {"name": "SEC_GPIOF"},
        {"name": "SEC_GPIOG"}, {"name": "SEC_GPIOH"}, {"name": "SEC_GPIOI"},
    ],
}

# GPDMA1: SVD names registers GPDMA_C0TR1 etc. Auto rename strips 'GPDMA1_'
# but the names start with 'GPDMA_' so they're not stripped. Curated rename
# strips 'GPDMA_' and keyfn replaces leading channel index with Cx placeholder.
GPDMA = {
    "svd_name": "GPDMA1",
    "description": "General-purpose DMA controller",
    "rename": lambda n: n[len("GPDMA_"):] if n.startswith("GPDMA_") else n,
    "section_keyfn": _gpdma_keyfn("GPDMA"),
    "_clear_pattern": True,
    "emit": [
        {"name": "GPDMA1"},
        {"name": "SEC_GPDMA1"},
    ],
}

# LPDMA1: same naming pattern as GPDMA1 but with LPDMA_ prefix.
LPDMA = {
    "svd_name": "LPDMA1",
    "description": "Low-power DMA controller",
    "rename": lambda n: n[len("LPDMA_"):] if n.startswith("LPDMA_") else n,
    "section_keyfn": _gpdma_keyfn("LPDMA"),
    "_clear_pattern": True,
    "emit": [
        {"name": "LPDMA1"},
        {"name": "SEC_LPDMA1"},
    ],
}

# Advanced-control timers TIM1 and TIM8: TIM8 is derived from TIM1 in the SVD,
# so it inherits TIM1_* register names (TIM1_CR1, TIM1_CR2, ...).  The auto
# rename for 'TIM8' tries to strip 'TIM8_' but names start with 'TIM1_', so
# nothing gets stripped. Curated spec strips 'TIM1_' for both instances.
# SEC_TIM1 has the same problem (derived from TIM1, inherits TIM1_* names).
ADV_TIM = {
    "svd_name": "TIM1",
    "description": "Advanced-control timer",
    # Strip TIM1_ prefix: TIM1_CR1 -> CR1
    "rename": lambda n: n[len("TIM1_"):] if n.startswith("TIM1_") else n,
    "section_keyfn": lambda b: f"TIMx_{b}",
    "_clear_pattern": True,
    "emit": [
        {"name": "TIM1"},
        {"name": "TIM8"},
        {"name": "SEC_TIM1"},
        {"name": "SEC_TIM8"},
    ],
}

PERIPHERALS = [GPIO, GPDMA, LPDMA, ADV_TIM]

# --- hand-authored peripherals not in SVD ---------------------------------------
EXTRA_PERIPHERALS = []

# --- Tier 2 (not implemented) ---------------------------------------------------
ELECTRICAL = []
LIMITS      = {}
TIERS       = [1]
